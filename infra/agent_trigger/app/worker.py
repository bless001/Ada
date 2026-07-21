import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import redis

from .agent_bridge import run_coding_agent_placeholder, should_agent_start
from .openproject_client import OpenProjectClient
from .retry_policy import calculate_retry_delay_seconds, classify_exception
from .settings import settings
from .storage import EventStore


@dataclass(frozen=True)
class ProcessResult:
    requeue_after_seconds: int | None = None


def extract_link_title(resource: dict, name: str) -> str | None:
    link = resource.get("_links", {}).get(name, {})
    if isinstance(link, dict):
        return link.get("title")
    return None


def extract_description_raw(work_package: dict) -> str | None:
    description = work_package.get("description")
    if isinstance(description, dict):
        return description.get("raw")
    return None


def process_event(event_id: str, store: EventStore | None = None) -> ProcessResult:
    store = store or EventStore(settings.DATABASE_URL)
    lease = store.claim_event(
        event_id,
        lease_owner=settings.WORKER_ID,
        lease_seconds=settings.WORKER_LEASE_SECONDS,
    )
    if lease is None:
        print(f"[worker] Event is not claimable or already complete: {event_id}", flush=True)
        return ProcessResult()

    event = store.get_event(event_id)
    if not event:
        print(f"[worker] Event not found: {event_id}", flush=True)
        return ProcessResult()

    try:
        wp_id = event.get("external_work_package_id")
        if not wp_id:
            print(f"[worker] No work package ID in event {event_id}. Marking processed.", flush=True)
            store.mark_processed(event_id)
            return ProcessResult()

        token = settings.openproject_api_token
        if not token:
            raise RuntimeError("OpenProject API token missing. Provisioning did not create token file.")

        client = OpenProjectClient(
            base_url=settings.OPENPROJECT_BASE_URL,
            api_token=token,
            host_header=settings.OPENPROJECT_API_HOST_HEADER,
        )

        work_package = client.get_work_package(wp_id)
        activities = client.list_work_package_activities(wp_id)

        status_name = extract_link_title(work_package, "status")
        type_name = extract_link_title(work_package, "type")
        project_name = extract_link_title(work_package, "project")

        store.insert_context_snapshot(
            external_work_package_id=wp_id,
            subject=work_package.get("subject"),
            status_name=status_name,
            type_name=type_name,
            project_name=project_name,
            description_raw=extract_description_raw(work_package),
            work_package_payload=work_package,
            activities_payload=activities,
        )

        print(
            f"[worker] Synced work package {wp_id}: "
            f"{work_package.get('subject')} [{status_name}]",
            flush=True,
        )

        if should_agent_start(status_name, settings.agent_trigger_statuses):
            result = run_coding_agent_placeholder(
                event=event,
                work_package=work_package,
                activities=activities,
            )

            try:
                client.add_comment(
                    work_package,
                    "🤖 Coding agent was triggered.\n\n" + result,
                )
            except Exception as exc:
                print(f"[worker] Could not post comment back to OpenProject: {exc}", flush=True)

            print(f"[worker] Agent triggered for work package {wp_id}.", flush=True)
        else:
            print("[worker] Status is not agent-triggering. Context synced only.", flush=True)

        store.mark_processed(event_id)
        return ProcessResult()

    except Exception as exc:
        decision = classify_exception(exc)
        should_retry = decision.retryable and lease.attempt_count < settings.WORKER_MAX_EVENT_ATTEMPTS

        if should_retry:
            delay_seconds = calculate_retry_delay_seconds(
                lease.attempt_count,
                base_seconds=settings.WORKER_RETRY_BASE_SECONDS,
                max_seconds=settings.WORKER_RETRY_MAX_SECONDS,
            )
            retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
            store.mark_retrying(
                event_id,
                error_message=str(exc),
                retry_at=retry_at,
                retry_category=decision.category,
            )
            print(
                f"[worker] Scheduled retry for event {event_id} in {delay_seconds}s "
                f"after {decision.category}.",
                flush=True,
            )
            return ProcessResult(requeue_after_seconds=delay_seconds)

        store.mark_dead_letter(
            event_id,
            error_message=str(exc),
            retry_category=decision.category,
            retryable=decision.retryable,
        )
        print(
            f"[worker] Event {event_id} moved to dead_letter after attempt "
            f"{lease.attempt_count}: {exc}",
            flush=True,
        )
        traceback.print_exc()
        return ProcessResult()


def enqueue_recoverable_jobs(
    store: EventStore,
    redis_client: redis.Redis,
    *,
    limit: int = 50,
) -> int:
    event_ids = store.list_recoverable_event_ids(limit=limit)
    for event_id in event_ids:
        redis_client.lpush(settings.REDIS_QUEUE, event_id)
    return len(event_ids)


def main() -> None:
    redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    store = EventStore(settings.DATABASE_URL)
    print(f"[worker] Listening on queue: {settings.REDIS_QUEUE}", flush=True)

    while True:
        try:
            enqueue_recoverable_jobs(store, redis_client)
            item = redis_client.brpop(settings.REDIS_QUEUE, timeout=5)
            if not item:
                continue

            _, event_id = item
            print(f"[worker] Processing event {event_id}", flush=True)
            process_event(event_id, store=store)

        except KeyboardInterrupt:
            print("[worker] Stopping.", flush=True)
            sys.exit(0)

        except Exception as exc:
            print(f"[worker] Error: {exc}", flush=True)
            traceback.print_exc()
            time.sleep(2)


if __name__ == "__main__":
    main()
