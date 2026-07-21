import json

import redis
from fastapi import FastAPI, HTTPException, Request

from .event_parser import normalize_openproject_event
from .settings import settings
from .signature import verify_hmac_sha256
from .storage import EventStore


app = FastAPI(title="Coding Agent OpenProject Webhook Receiver")

store = EventStore(settings.DATABASE_URL)
redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhooks/openproject")
async def receive_openproject_webhook(request: Request):
    raw_body = await request.body()

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    headers = {key.lower(): value for key, value in request.headers.items()}

    if settings.WEBHOOK_REQUIRE_SIGNATURE:
        received_signature = headers.get(settings.WEBHOOK_SIGNATURE_HEADER.lower())

        if not verify_hmac_sha256(
            raw_body=raw_body,
            secret=settings.WEBHOOK_SIGNATURE_SECRET,
            received_signature=received_signature,
        ):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    normalized = normalize_openproject_event(payload, headers)

    stored_event = store.insert_event(
        source_tool=normalized["source_tool"],
        event_type=normalized["event_type"],
        external_project_id=normalized["external_project_id"],
        external_work_package_id=normalized["external_work_package_id"],
        external_comment_id=normalized["external_comment_id"],
        idempotency_key=normalized["idempotency_key"],
        headers=headers,
        payload=payload,
    )

    if stored_event.created:
        redis_client.lpush(settings.REDIS_QUEUE, stored_event.event_id)

    return {
        "status": "accepted" if stored_event.created else "duplicate",
        "event_id": stored_event.event_id,
        "event_type": normalized["event_type"],
        "work_package_id": normalized["external_work_package_id"],
        "queued": stored_event.created,
    }
