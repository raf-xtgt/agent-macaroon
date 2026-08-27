"""FastAPI router for F6 replay data: GET /audit/replay?chain_id=... returns the ordered
span timeline as JSON (queries Firestore server-side via audit/replay.py). Consumed by the
Next.js frontend (../../frontend/) — no login, no credential entry, single-tenant
(see agent-specification.md §8). This module never renders HTML; the UI lives in frontend/.
"""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from audit.replay import derive_verdict, get_chain_spans, hop_count
from audit.trace import subscribe_ws, unsubscribe_ws

router = APIRouter()


@router.websocket("/audit/live")
async def ws_live_spans(websocket: WebSocket) -> None:
    """WebSocket endpoint streaming audit spans in real time."""
    await websocket.accept()

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_span(span_doc: dict[str, Any]) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, span_doc)
        except Exception:  # noqa: BLE001, S110
            pass

    subscribe_ws(on_span)
    try:
        while True:
            span = await queue.get()
            serializable: dict[str, Any] = {}
            for k, v in span.items():
                if hasattr(v, "isoformat"):
                    serializable[k] = v.isoformat()
                else:
                    serializable[k] = v
            await websocket.send_json(serializable)
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001, S110
        pass
    finally:
        unsubscribe_ws(on_span)


@router.get("/audit/replay")
def get_replay(chain_id: str) -> dict[str, Any]:
    """Retrieve the full chronological span replay for a delegation chain.

    Args:
        chain_id: The UUID of the task delegation chain to replay.

    Returns:
        dict[str, Any]: Formatted audit timeline object containing provenance, verdict,
            hop count, and chronological span array.

    Raises:
        HTTPException: 404 if no spans are found for the requested chain_id.
    """
    spans = get_chain_spans(chain_id)
    if not spans:
        raise HTTPException(
            status_code=404, detail=f"no spans found for chain_id {chain_id}"
        )

    root_span = next((s for s in spans if s.parent_span_id is None), spans[0])
    human_subject_id = root_span.human_subject_id
    purpose = root_span.purpose
    started_at = spans[0].timestamp.isoformat()
    verdict = derive_verdict(spans)
    hops = hop_count(spans)

    serialized_spans = [
        {
            "span_id": s.span_id,
            "parent_span_id": s.parent_span_id,
            "agent_id": s.agent_id,
            "action_requested": s.action_requested,
            "decision": s.decision,
            "reason": s.reason,
            "timestamp": s.timestamp.isoformat(),
            "macaroon_identifier_hash": s.macaroon_identifier_hash,
        }
        for s in spans
    ]

    return {
        "chain_id": chain_id,
        "human_subject_id": human_subject_id,
        "purpose": purpose,
        "started_at": started_at,
        "hop_count": hops,
        "verdict": verdict,
        "spans": serialized_spans,
    }
