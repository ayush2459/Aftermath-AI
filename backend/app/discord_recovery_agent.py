"""Direct Discord bot client for Aftermath customer support and GhostTrail recovery.

This process connects to Discord using the existing bot token. Do not run another
Gateway client with the same token at the same time.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import discord
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("aftermath.discord_recovery_agent")

API_BASE = os.getenv("AFTERMATH_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
AGENT_SECRET = os.getenv("DISCORD_RECOVERY_AGENT_KEY", "").strip()
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
RECOVERY_CHANNEL_ID = (
    os.getenv("DISCORD_RECOVERY_CHANNEL_ID", "").strip()
    or os.getenv("DISCORD_CHANNEL_ID", "").strip()
)

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


def _json_request(url: str, payload: dict, headers: dict, timeout: int = 15) -> dict:
    import json

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


def _first_text(data: dict, *keys: str, limit: int = 500) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:limit]
    return ""


def format_case_reply(case: dict, case_code: str) -> str:
    """Turn the persisted GhostTrail diagnosis into a concise customer-safe review."""
    diagnosis = case.get("diagnosis") or {}
    if isinstance(diagnosis, str):
        diagnosis = {"summary": diagnosis}
    if not isinstance(diagnosis, dict):
        diagnosis = {}

    plan = case.get("plan") or {}
    actions = plan.get("actions") or []
    eligible = next(
        (
            item for item in actions
            if isinstance(item, dict)
            and item.get("action_type") == "reconcile_shipment_with_carrier"
        ),
        None,
    )
    summary = _first_text(diagnosis, "summary", "diagnosis", "root_cause", "explanation")
    cause = _first_text(diagnosis, "root_cause", "cause")
    confidence = diagnosis.get("confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        confidence_text = f"{confidence:.0%}" if 0 <= confidence <= 1 else ""
    elif isinstance(confidence, str):
        confidence_text = confidence[:30]
    else:
        confidence_text = ""

    action_description = _first_text(
        eligible or {}, "description", "reason", limit=400
    ) or "Restore the failed shipment record in the Aftermath demo."
    order_id = str(case.get("order_id") or "")
    order_reference = order_id[:8] if order_id else "your order"

    lines = [
        "## GhostTrail investigation",
        f"I've reviewed the approved recovery case for order `{order_reference}`.",
        f"**What we found:** {summary or 'The payment is recorded, but shipment creation did not complete.'}",
    ]
    if cause and cause.casefold() != summary.casefold():
        lines.append(f"**Likely cause:** {cause}")
    if confidence_text:
        lines.append(f"**Diagnosis confidence:** {confidence_text}")
    lines.extend([
        f"**Current records:** payment `{case.get('payment_status') or 'unknown'}`, "
        f"shipment `{case.get('shipment_status') or 'unknown'}`, "
        f"order `{case.get('order_status') or 'unknown'}`.",
        f"**Approved next step:** {action_description}",
        "",
        "Nothing will be changed until you explicitly confirm. "
        f"To proceed with this approved demo recovery, reply `CONFIRM {case_code}`.",
        "_Demo only: no carrier is contacted and no physical parcel is moved._",
    ])
    return "\n".join(lines)


def handle_case(case_code: str) -> str:
    case = aftermath_request(
        "/api/discord/recovery/handoffs/inspect",
        {"case_code": case_code},
    )
    return format_case_reply(case, case_code)


def format_confirmation_reply(result: dict) -> str:
    verification = result.get("verification") or {}
    if (
        result.get("status") != "completed"
        or verification.get("order_status") != "restored"
        or verification.get("shipment_status") != "created"
        or verification.get("incident_status") != "resolved"
        or verification.get("carrier_code") != "AFTERMATH-DEMO"
    ):
        raise RuntimeError("Recovery state verification did not match the expected result.")

    customer_url = result.get("customer_url")
    parsed = urlparse(customer_url or "")
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise RuntimeError("The corrected shipment page URL was not valid.")
    tracking = verification.get("tracking_number")
    replay_note = " This was an idempotent replay; no duplicate recovery was created." if result.get("idempotent_replay") else ""
    lines = [
        "## Shipment recovery verified",
        "The approved recovery completed and the backend read the saved records back successfully.",
        "• Order: **restored**",
        "• Shipment: **created (simulated)**",
        "• Incident: **resolved**",
    ]
    if tracking:
        lines.append(f"• Demo tracking reference: `{str(tracking)[:80]}`")
    lines.extend([
        "",
        f"[Open your corrected shipment page]({customer_url})",
        "",
        "This is a demonstration recovery only. No carrier API was called and no real parcel was created or moved."
        + replay_note,
    ])
    return "\n".join(lines)


def handle_confirmation(case_code: str) -> str:
    result = aftermath_request(
        "/api/discord/recovery/handoffs/execute",
        {"case_code": case_code, "confirmation": "CONFIRM RECOVERY"},
    )
    return format_confirmation_reply(result)


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
            "I'm sorry, but I couldn't verify that recovery step. "
            "The shipment must not be treated as restored. Please try again shortly "
            "or contact the support team."
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


async def run() -> None:
    missing = [
        name for name, value in (
            ("DISCORD_BOT_TOKEN", BOT_TOKEN),
            ("DISCORD_RECOVERY_AGENT_KEY", AGENT_SECRET),
            ("DISCORD_RECOVERY_CHANNEL_ID (or DISCORD_CHANNEL_ID)", RECOVERY_CHANNEL_ID),
        ) if not value
    ]
    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))

    try:
        channel_id = int(RECOVERY_CHANNEL_ID)
    except ValueError as exc:
        raise RuntimeError("DISCORD_RECOVERY_CHANNEL_ID must be a numeric Discord channel ID.") from exc

    intents = discord.Intents.default()
    intents.guilds = True
    intents.messages = True
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        logger.info("Aftermath Recovery connected to Discord as %s", client.user)
        logger.info("Listening only in configured recovery channel %s", channel_id)

    @client.event
    async def on_message(message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        if message.channel.id != channel_id:
            return

        body = (message.content or "").strip()
        if not body:
            return

        parsed = parse_command(body)
        addressed = client.user in message.mentions if client.user else False
        if not parsed and not addressed:
            return

        try:
            if parsed:
                kind, code = parsed
                if kind == "case":
                    reply = await asyncio.to_thread(handle_case, code)
                else:
                    reply = await asyncio.to_thread(handle_confirmation, code)
            else:
                reply = await asyncio.to_thread(
                    handle_support_message,
                    body,
                    str(message.channel.id),
                    str(message.id),
                )
        except Exception:
            logger.exception("Could not process addressed Aftermath support message")
            reply = (
                "I'm sorry, but I couldn't verify that recovery step. "
                "The shipment must not be treated as restored. Please try again shortly "
                "or contact the support team."
            )

        try:
            await message.reply(reply, mention_author=False)
        except discord.HTTPException:
            logger.exception("Could not send the customer support reply to Discord")

    await client.start(BOT_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Aftermath Discord recovery agent stopped.")
