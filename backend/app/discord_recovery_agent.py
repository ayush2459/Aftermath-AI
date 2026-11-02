"""Switch WebSocket client for unified Aftermath customer support.

Switch owns the Discord Gateway connection. This client consumes addressed
room events, routes GhostTrail recovery commands, and records other support
reports through the Aftermath support intake API.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

import websockets

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("aftermath.discord_recovery_agent")

API_BASE = os.getenv("AFTERMATH_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
AGENT_SECRET = os.getenv("DISCORD_RECOVERY_AGENT_KEY", "").strip()
SWITCH_BASE = os.getenv("SWITCH_BRIDGE_BASE_URL", "").rstrip("/")
SWITCH_AGENT_ID = os.getenv("SWITCH_AGENT_ID", "").strip()
SWITCH_AGENT_KEY = os.getenv("SWITCH_AGENT_API_KEY", "").strip()
SWITCH_ROOM_ID = os.getenv("SWITCH_ROOM_ID", "").strip()
CONNECTION_ID = os.getenv("SWITCH_CONNECTION_ID", str(uuid.uuid4()))
MAX_RECONNECT_SECONDS = 30

CASE_PATTERN = re.compile(r"\bCASE\s+([A-Za-z0-9_-]{24,100})\b", re.IGNORECASE)
CONFIRM_PATTERN = re.compile(r"\bCONFIRM\s+([A-Za-z0-9_-]{24,100})\b", re.IGNORECASE)


def _json_request(url: str, payload: dict, headers: dict, timeout: int = 15) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:1000]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed: {exc.reason}") from exc


def aftermath_request(path: str, payload: dict) -> dict:
    if not AGENT_SECRET:
        raise RuntimeError("DISCORD_RECOVERY_AGENT_KEY is not configured.")
    return _json_request(
        f"{API_BASE}{path}",
        payload,
        {"X-Aftermath-Agent-Key": AGENT_SECRET},
    )


def switch_post(room_id: str, content: str) -> dict:
    return _json_request(
        f"{SWITCH_BASE}/agents/{SWITCH_AGENT_ID}/message",
        {"room_id": room_id, "content": content},
        {"Authorization": f"Bearer {SWITCH_AGENT_KEY}"},
    )


def parse_command(body: str) -> tuple[str, str] | None:
    confirmation = CONFIRM_PATTERN.search(body or "")
    if confirmation:
        return "confirm", confirmation.group(1)
    case = CASE_PATTERN.search(body or "")
    if case:
        return "case", case.group(1)
    return None


def handle_case(case_code: str) -> str:
    case = aftermath_request(
        "/api/discord/recovery/handoffs/inspect",
        {"case_code": case_code},
    )
    plan = case.get("plan") or {}
    actions = plan.get("actions") or []
    eligible = next(
        (item for item in actions if item.get("action_type") == "reconcile_shipment_with_carrier"),
        None,
    )
    action_description = (eligible or {}).get("description") or "Restore the simulated shipment record."
    return (
        "I've found your shipment details. Your payment was recorded, but the shipment setup did not finish. "
        f"GhostTrail's approved next step is: {action_description}\n\n"
        "This is a demonstration only; no real carrier or parcel is involved. "
        f"If you'd like to continue, reply CONFIRM {case_code}."
    )


def handle_confirmation(case_code: str) -> str:
    result = aftermath_request(
        "/api/discord/recovery/handoffs/execute",
        {"case_code": case_code, "confirmation": "CONFIRM RECOVERY"},
    )
    verification = result.get("verification") or {}
    if (
        verification.get("order_status") != "restored"
        or verification.get("shipment_status") != "created"
        or verification.get("incident_status") != "resolved"
    ):
        raise RuntimeError("Recovery state verification did not match the expected result.")
    customer_url = result.get("customer_url")
    if not customer_url:
        raise RuntimeError("The corrected shipment page was not returned.")
    return (
        "Your shipment issue has been resolved in the Aftermath demonstration. "
        "Your previous order details are still available here:\n"
        f"{customer_url}\n\n"
        "Please note: this demonstration does not contact a real carrier or move a parcel."
    )


def handle_support_message(message: str, room_id: str, event_id: str | None = None) -> str:
    result = aftermath_request(
        "/api/support/cases",
        {
            "message": message[:5000],
            "room_id": room_id,
            "source_event_id": str(event_id) if event_id is not None else None,
        },
    )
    return result.get(
        "reply",
        "Thanks for reporting this. I've saved your message so we can look into it.",
    )


async def process_message(room_id: str, payload: dict, event_id: str | None = None) -> bool:
    if not payload.get("addressed"):
        return True
    body = (payload.get("body") or "").strip()
    if not body:
        return True

    parsed = parse_command(body)
    try:
        if parsed:
            kind, code = parsed
            if kind == "case":
                reply = await asyncio.to_thread(handle_case, code)
            else:
                reply = await asyncio.to_thread(handle_confirmation, code)
        else:
            reply = await asyncio.to_thread(handle_support_message, body, room_id, event_id)
    except Exception:
        logger.exception("Could not process addressed Aftermath support message")
        reply = (
            "I'm sorry, but I couldn't complete that step safely. "
            "Your order has not been marked as restored. Please try again shortly or contact the support team."
        )

    try:
        await asyncio.to_thread(switch_post, room_id, reply)
        return True
    except Exception:
        logger.exception("Could not post the customer support reply to the Switch room")
        return False


def websocket_url() -> str:
    if not SWITCH_BASE:
        raise RuntimeError("SWITCH_BRIDGE_BASE_URL is required.")
    parsed = urlparse(SWITCH_BASE)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    query = {
        "connection_id": CONNECTION_ID,
        "scope": "single" if SWITCH_ROOM_ID else "all",
        "filter": "all",
        "start_from": "head",
    }
    if SWITCH_ROOM_ID:
        query["rooms"] = SWITCH_ROOM_ID
    path = f"/agents/{SWITCH_AGENT_ID}/connection/ws"
    return urlunparse((scheme, parsed.netloc, path, "", urlencode(query), ""))


async def run() -> None:
    missing = [
        name for name, value in (
            ("DISCORD_RECOVERY_AGENT_KEY", AGENT_SECRET),
            ("SWITCH_BRIDGE_BASE_URL", SWITCH_BASE),
            ("SWITCH_AGENT_ID", SWITCH_AGENT_ID),
            ("SWITCH_AGENT_API_KEY", SWITCH_AGENT_KEY),
        ) if not value
    ]
    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))

    delay = 2
    cursor: int | None = None
    generation: int | None = None
    while True:
        query_url = websocket_url()
        if cursor is not None or generation is not None:
            parsed = urlparse(query_url)
            from urllib.parse import parse_qsl
            params = dict(parse_qsl(parsed.query))
            if cursor is not None:
                params["start_from"] = str(cursor)
            if generation is not None:
                params["expected_generation"] = str(generation)
            query_url = urlunparse(parsed._replace(query=urlencode(params)))

        try:
            logger.info("Connecting to Switch agent bridge")
            async with websockets.connect(
                query_url,
                additional_headers={"Authorization": f"Bearer {SWITCH_AGENT_KEY}"},
                ping_interval=None,
                max_size=1_048_576,
                open_timeout=15,
            ) as socket:
                delay = 2
                event_queue: asyncio.Queue = asyncio.Queue()

                async def consume_events():
                    nonlocal cursor
                    while True:
                        sequence, room_id, event_payload = await event_queue.get()
                        try:
                            delivered = await process_message(room_id, event_payload, sequence)
                            if not delivered:
                                await socket.close(code=1011, reason="Reply delivery failed; replay event")
                                return
                            if isinstance(sequence, int):
                                cursor = max(cursor or 0, sequence)
                        finally:
                            event_queue.task_done()

                consumer = asyncio.create_task(consume_events())
                try:
                    async for raw in socket:
                        frame = json.loads(raw)
                        frame_type = frame.get("type")
                        if frame_type == "ping":
                            await socket.send(json.dumps({"type": "pong", "cursor": cursor or 0}))
                            continue
                        if frame_type == "connection_state":
                            generation = frame.get("generation")
                            cursor = frame.get("cursor", cursor or 0)
                            logger.info("Switch connection ready; rooms=%s cursor=%s", frame.get("rooms"), cursor)
                            continue
                        if frame_type == "refused":
                            raise RuntimeError(f"Switch refused connection: {frame}")
                        if frame.get("event") == "message":
                            data = frame.get("data") or {}
                            sequence = frame.get("id", data.get("sequence"))
                            event_payload = data.get("payload") or {}
                            room_id = data.get("room_id")
                            if room_id:
                                await event_queue.put((sequence, room_id, event_payload))
                        else:
                            sequence = (frame.get("data") or {}).get("sequence", frame.get("id"))
                            if isinstance(sequence, int):
                                cursor = max(cursor or 0, sequence)
                finally:
                    consumer.cancel()
                    await asyncio.gather(consumer, return_exceptions=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Switch connection ended; reconnecting")
            await asyncio.sleep(delay)
            delay = min(delay * 2, MAX_RECONNECT_SECONDS)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Unified Aftermath support agent stopped.")
