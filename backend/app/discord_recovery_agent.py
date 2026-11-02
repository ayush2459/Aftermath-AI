"""Switch WebSocket client for the Aftermath Discord recovery agent.

The Switch bot owns the Discord Gateway connection. This client only consumes
addressed Switch room events and posts replies through the Switch agent bridge.
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
            return json.loads(response.read().decode("utf-8"))
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
    diagnosis = case.get("diagnosis") or {}
    plan = case.get("plan") or {}
    actions = plan.get("actions") or []
    eligible = next(
        (item for item in actions if item.get("action_type") == "reconcile_shipment_with_carrier"),
        None,
    )
    summary = diagnosis.get("summary") or diagnosis.get("likely_cause") or case.get("incident_title", "Shipment failure")
    likely_cause = diagnosis.get("likely_cause") or "See GhostTrail's diagnosis."
    recommended = diagnosis.get("recommended_next_step") or "Review the approved recovery action."
    action_description = (eligible or {}).get("description") or "Restore the simulated shipment record."
    return (
        f"**GhostTrail recovery case verified**\n"
        f"Order: {case.get('order_id')}\n"
        f"Payment: **{case.get('payment_status')}** · Shipment: **{case.get('shipment_status')}**\n"
        f"Diagnosis: **{summary}**\n"
        f"Likely cause: {likely_cause}\n"
        f"GhostTrail recommendation: {recommended}\n"
        f"Approved action: {action_description}\n\n"
        f"This is a simulation. No real carrier or parcel will be contacted. "
        f"To authorize the simulated order restoration, reply: "
        f"@Aftermath Recovery CONFIRM {case_code}"
    )


def handle_confirmation(case_code: str) -> str:
    result = aftermath_request(
        "/api/discord/recovery/handoffs/execute",
        {"case_code": case_code, "confirmation": "CONFIRM RECOVERY"},
    )
    verification = result.get("verification") or {}
    return (
        f"**Aftermath AI recovery completed and verified**\n"
        f"Order: {result.get('order_id')}\n"
        f"Order status: **{verification.get('order_status', 'restored')}**\n"
        f"Shipment status: **{verification.get('shipment_status', 'created')}**\n"
        f"Incident status: **{verification.get('incident_status', 'resolved')}**\n"
        f"Simulated tracking reference: {verification.get('tracking_number', 'available on shipment page')}\n\n"
        f"**Your corrected shipment page:** {result.get('customer_url')}\n\n"
        f"Simulation only: no real carrier API, parcel movement, delivery or inventory mutation occurred."
    )


async def process_message(room_id: str, payload: dict) -> None:
    if not payload.get("addressed"):
        return
    body = payload.get("body") or ""
    parsed = parse_command(body)
    if not parsed:
        if "aftermath recovery" in body.lower():
            await asyncio.to_thread(
                switch_post,
                room_id,
                "I can process a GhostTrail-approved simulated recovery. Send CASE <case_code> from your GhostTrail handoff, then review the diagnosis and explicitly confirm with CONFIRM <case_code>.",
            )
        return

    kind, code = parsed
    try:
        if kind == "case":
            reply = await asyncio.to_thread(handle_case, code)
        else:
            reply = await asyncio.to_thread(handle_confirmation, code)
    except Exception as exc:
        logger.exception("Could not process addressed recovery message")
        reply = f"I couldn't complete that recovery step: {str(exc)[:500]}. The order has not been reported as restored."
    await asyncio.to_thread(switch_post, room_id, reply)


def websocket_url() -> str:
    if not SWITCH_BASE:
        raise RuntimeError("SWITCH_BRIDGE_BASE_URL is required.")
    parsed = urlparse(SWITCH_BASE)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    query = {
        "connection_id": CONNECTION_ID,
        "scope": "all",
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
                        sequence = frame.get("id", (frame.get("data") or {}).get("sequence"))
                        if isinstance(sequence, int):
                            cursor = max(cursor or 0, sequence)
                        data = frame.get("data") or {}
                        event_payload = data.get("payload") or {}
                        room_id = data.get("room_id")
                        if room_id:
                            await process_message(room_id, event_payload)
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
        logger.info("Discord recovery agent stopped.")
