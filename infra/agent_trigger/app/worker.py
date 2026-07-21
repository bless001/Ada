import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import redis

from .core_client import CoreOrchestrationClient
from .retry_policy import calculate_retry_delay_seconds, classify_exception
from .settings import settings
from .storage import EventStore


@dataclass(frozen=True)
class ProcessResult:
    requeue_after_seconds: int | None = None
    core_result: dict[str, Any] | None = None


def process_event(
    event_id: str,
    store: EventStore | None = None,
    core_client: CoreOrchestrationClient | None = None,
) -> ProcessResult:
    store = store or EventStore(settings.DATABASE_URL)
    lease = store.claim_event(
        event_id,
        lease_owner=settings.WORKER_ID,
        lease_seconds=settings.WORKER_LEASE_SECONDS,
    )
    if lease is None:
        print(f"[worker] Event is not claimable or already complete: {event_id}", flush=True)
        return ProcessResult()

    try:
        client = core_client or CoreOrchestrationClient(
            base_url=settings.PLANNING_AGENT_CORE_URL,
            timeout_seconds=settings.PLANNING_AGENT_CORE_TIMEOUT_SECONDS,
        )
        core_result = client.orchestrate_event(event_id)
        store.mark_processed(event_id)
        print(
            f"[worker] Core orchestration complete for event {event_id}: "
            f"{core_result.get('action')}",
            flush=True,
        )
        return ProcessResult(core_result=core_result)

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
