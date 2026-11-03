"""Direct Discord bot client for Aftermath customer support and GhostTrail recovery.

This process connects to Discord using the existing bot token. Do not run another
Gateway client with the same token at the same time.
"""
from __future__ import annotations

import asyncio
import json
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
STATUS_PATTERN = re.compile(r"\bSTATUS\s+([A-Za-z0-9_-]{24,100})\b", re.IGNORECASE)
CONFIRM_PATTERN = re.compile(r"\bCONFIRM\s+([A-Za-z0-9_-]{24,100})\b", re.IGNORECASE)


def parse_command(body: str) -> tuple[str, str] | None:
    status = STATUS_PATTERN.search(body or "")
    if status:
        return "status", status.group(1)
    confirmation = CONFIRM_PATTERN.search(body or "")
    if confirmation:
        return "confirm", confirmation.group(1)
    case = CASE_PATTERN.search(body or "")
    if case:
        return "case", case.group(1)
    return None

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
        f"I've reviewed the prepared recovery case for order `{order_reference}`.",
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
        f"**Proposed next step:** {action_description}",
        "",
        "Nothing will be changed until you explicitly confirm. "
        f"To proceed with this proposed demo recovery, reply `CONFIRM {case_code}`.",
        "_Demo only: no carrier is contacted and no physical parcel is moved._",
    ])
    return "\n".join(lines)


def handle_case(case_code: str) -> str:
    case = aftermath_request(
        "/api/discord/recovery/handoffs/inspect",
        {"case_code": case_code},
    )
    return format_case_reply(case, case_code)



def handle_status(case_code: str) -> str:
    status = aftermath_request(
        "/api/discord/recovery/handoffs/status",
        {"case_code": case_code},
    )
    recovery = status.get("recovery_status") or "not_started"
    lines = [
        "## Recovery status",
        f"• Incident: **{status.get('incident_status') or 'unknown'}**",
        f"• Plan: **{status.get('plan_status') or 'unknown'}**",
        f"• Approval: **{status.get('approval_status') or 'unknown'}**",
        f"• Payment: **{status.get('payment_status') or 'unknown'}**",
        f"• Shipment: **{status.get('shipment_status') or 'unknown'}**",
        f"• Recovery action: **{recovery}**",
    ]
    if recovery == "completed":
        lines.append("The action is already recorded. Repeating CONFIRM will not create a duplicate.")
    elif recovery in {"not_started", "failed"}:
        lines.append(f"Review with CASE {case_code} before deciding whether a retry is safe.")
    if status.get("consumed"):
        lines.append("This handoff has been consumed.")
    lines.append("_Demo only: no carrier API or physical parcel is involved._")
    return "\n".join(lines)


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


def handle_support_message(message: str, channel_id: str, event_id: str | None = None) -> str:
    result = aftermath_request(
        "/api/support/cases",
        {
            "message": message[:5000],
            "room_id": channel_id,
            "source_event_id": str(event_id) if event_id is not None else None,
        },
    )
    return result.get(
        "reply",
        "Thanks for reporting this. I've saved your message so we can look into it.",
    )


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
        if message.channel.id != channel_id or message.guild is None:
            return

        if message.author.bot:
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
                elif kind == "status":
                    reply = await asyncio.to_thread(handle_status, code)
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
