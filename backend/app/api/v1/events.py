import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_current_user
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.repositories.event_repository import EventRepository


router = APIRouter(prefix="/events", tags=["Events"])


@router.get("/stream")
async def stream_events(
    request: Request,
    current_user: User = Depends(get_current_user),
    last_event_id: int | None = Header(default=None, alias="Last-Event-ID"),
    after: int | None = Query(default=None, ge=0),
):
    cursor = max(last_event_id or 0, after or 0)

    async def generate():
        nonlocal cursor
        heartbeat_at = asyncio.get_running_loop().time()
        while not await request.is_disconnected():
            async with AsyncSessionLocal() as session:
                events = await EventRepository(session).list_after(
                    event_id=cursor,
                    user_id=current_user.id,
                    role=current_user.role,
                )
            for event in events:
                cursor = event.id
                data = {
                    "id": event.id,
                    "type": event.event_type,
                    "aggregate_type": event.aggregate_type,
                    "aggregate_id": event.aggregate_id,
                    "payload": event.payload,
                    "created_at": event.created_at.isoformat(),
                }
                yield f"id: {event.id}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

            now = asyncio.get_running_loop().time()
            if now - heartbeat_at >= 15:
                timestamp = datetime.now(timezone.utc).isoformat()
                yield f": heartbeat {timestamp}\n\n"
                heartbeat_at = now
            await asyncio.sleep(1)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
