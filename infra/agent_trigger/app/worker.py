import sys
import time
import traceback

import redis

from .agent_bridge import run_coding_agent_placeholder, should_agent_start
from .openproject_client import OpenProjectClient
from .settings import settings
from .storage import EventStore


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


def process_event(event_id: str) -> None:
    store = EventStore(settings.DATABASE_URL)
    event = store.get_event(event_id)

    if not event:
        print(f"[worker] Event not found: {event_id}", flush=True)
        return

    try:
        store.mark_processing(event_id)

        wp_id = event.get("external_work_package_id")
        if not wp_id:
            print(f"[worker] No work package ID in event {event_id}. Marking processed.", flush=True)
            store.mark_processed(event_id)
            return

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

    except Exception as exc:
        store.mark_failed(event_id, str(exc))
        raise


def main() -> None:
    redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    print(f"[worker] Listening on queue: {settings.REDIS_QUEUE}", flush=True)

    while True:
        try:
            item = redis_client.brpop(settings.REDIS_QUEUE, timeout=5)
            if not item:
                continue

            _, event_id = item
            print(f"[worker] Processing event {event_id}", flush=True)
            process_event(event_id)

        except KeyboardInterrupt:
            print("[worker] Stopping.", flush=True)
            sys.exit(0)

        except Exception as exc:
            print(f"[worker] Error: {exc}", flush=True)
            traceback.print_exc()
            time.sleep(2)


if __name__ == "__main__":
    main()
