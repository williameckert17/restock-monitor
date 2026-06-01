"""
Notification channels for restock alerts.

Active channels are controlled by the NOTIFY_CHANNELS environment variable,
a comma-separated list of channel names:

    NOTIFY_CHANNELS=discord,pushover
    NOTIFY_CHANNELS=discord,twilio,email
    NOTIFY_CHANNELS=discord,browser

Available channel names
  discord  — Discord webhook embed (DISCORD_WEBHOOK_URL)
  pushover — Pushover mobile push notification (PUSHOVER_APP_TOKEN + PUSHOVER_USER_KEY)
  twilio   — Twilio SMS (TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN + TWILIO_FROM + TWILIO_TO)
  email    — SMTP email (SMTP_HOST + SMTP_USER + SMTP_PASS + SMTP_FROM + ALERT_EMAIL)
  browser  — open the product URL in the default local browser

A channel listed in NOTIFY_CHANNELS but missing its credentials is silently
skipped with a warning — so you can enable a channel in config and fill in
the credentials later without crashing the monitor.
"""
import asyncio
import logging
import os
import smtplib
import webbrowser
from email.message import EmailMessage
from typing import Any, Callable, List, Optional

import httpx

from core.models import SiteConfig

log = logging.getLogger(__name__)

_PUSHOVER_API = "https://api.pushover.net/1/messages.json"
_DISCORD_GREEN = 0x00CC44

# Extra hooks called after every restock — used by the web dashboard for SSE.
_restock_hooks: List[Callable] = []


def register_restock_hook(fn: Callable) -> None:
    """Register a callable (sync or async) to be called on every restock alert."""
    _restock_hooks.append(fn)


def unregister_restock_hook(fn: Callable) -> None:
    try:
        _restock_hooks.remove(fn)
    except ValueError:
        pass


def _active_channels() -> set:
    raw = os.getenv("NOTIFY_CHANNELS", "discord")
    return {c.strip().lower() for c in raw.split(",") if c.strip()}


def _price_str(price: Optional[str]) -> str:
    return f" ({price})" if price else ""


# ── Public entry point ────────────────────────────────────────────────────────

async def notify(config: SiteConfig, price: Optional[str] = None) -> None:
    """Called exactly once per OUT_OF_STOCK → IN_STOCK transition."""
    log.info(
        "[%s] *** RESTOCK *** %s%s  →  %s",
        config.name,
        config.product_name,
        _price_str(price),
        config.url,
    )

    channels = _active_channels()
    tasks = []

    if "discord" in channels:
        tasks.append(_send_discord(config, price))
    if "pushover" in channels:
        tasks.append(_send_pushover(config, price))
    if "twilio" in channels:
        tasks.append(_send_twilio(config, price))
    if "email" in channels:
        tasks.append(asyncio.to_thread(_send_email, config, price))
    if "browser" in channels or os.getenv("OPEN_BROWSER", "0").lower() in ("1", "true", "yes"):
        webbrowser.open(config.url)

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for exc in results:
            if isinstance(exc, Exception):
                log.warning("Notification channel error: %s", exc)

    # Fire registered hooks (e.g. the web dashboard SSE publisher)
    for hook in list(_restock_hooks):
        try:
            result: Any = hook(config, price)
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:
            log.warning("Restock hook error: %s", exc)


# ── Discord ───────────────────────────────────────────────────────────────────

async def _send_discord(config: SiteConfig, price: Optional[str]) -> None:
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        log.warning("[%s] discord channel active but DISCORD_WEBHOOK_URL not set", config.name)
        return

    fields = [{"name": "Retailer", "value": config.name, "inline": True}]
    if price:
        fields.append({"name": "Price", "value": price, "inline": True})

    payload = {
        "embeds": [
            {
                "title": f"\U0001f514 Back in stock: {config.product_name}",
                "url": config.url,
                "color": _DISCORD_GREEN,
                "fields": fields,
                "footer": {"text": "restock-monitor"},
            }
        ]
    }

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(webhook_url, json=payload)
        r.raise_for_status()
    log.info("[%s] Discord alert sent", config.name)


# ── Pushover ──────────────────────────────────────────────────────────────────

async def _send_pushover(config: SiteConfig, price: Optional[str]) -> None:
    token = os.getenv("PUSHOVER_APP_TOKEN", "")
    user  = os.getenv("PUSHOVER_USER_KEY", "")
    if not token or not user:
        log.warning("[%s] pushover channel active but PUSHOVER_APP_TOKEN / PUSHOVER_USER_KEY not set", config.name)
        return

    price_note = f" — {price}" if price else ""
    payload = {
        "token":     token,
        "user":      user,
        "title":     f"Restock: {config.product_name}",
        "message":   f"{config.product_name}{price_note} is back in stock at {config.name}.",
        "url":       config.url,
        "url_title": f"Buy at {config.name}",
        # Priority 1 = high priority, bypasses quiet hours — appropriate for
        # time-sensitive restock alerts. Use 0 (normal) if you prefer quiet hours.
        "priority":  int(os.getenv("PUSHOVER_PRIORITY", "1")),
    }

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(_PUSHOVER_API, data=payload)
        r.raise_for_status()
    log.info("[%s] Pushover alert sent", config.name)


# ── Twilio SMS ────────────────────────────────────────────────────────────────

async def _send_twilio(config: SiteConfig, price: Optional[str]) -> None:
    sid   = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_ = os.getenv("TWILIO_FROM", "")
    to_raw = os.getenv("TWILIO_TO", "")
    if not all([sid, token, from_, to_raw]):
        log.warning(
            "[%s] twilio channel active but one or more of "
            "TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM / TWILIO_TO not set",
            config.name,
        )
        return

    # TWILIO_TO supports comma-separated numbers for multi-recipient alerts.
    recipients = [n.strip() for n in to_raw.split(",") if n.strip()]

    price_note = f" ({price})" if price else ""
    body = (
        f"RESTOCK: {config.product_name}{price_note}\n"
        f"{config.name}\n"
        f"{config.url}"
    )

    api_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    async with httpx.AsyncClient(timeout=10) as client:
        for to in recipients:
            try:
                r = await client.post(api_url, auth=(sid, token), data={"From": from_, "To": to, "Body": body})
                r.raise_for_status()
                log.info("[%s] Twilio SMS sent to %s", config.name, to)
            except Exception as exc:
                log.warning("[%s] Twilio SMS to %s failed: %s", config.name, to, exc)


# ── Email (SMTP) ──────────────────────────────────────────────────────────────

def _send_email(config: SiteConfig, price: Optional[str]) -> None:
    host = os.getenv("SMTP_HOST", "")
    if not host:
        log.warning("[%s] email channel active but SMTP_HOST not set", config.name)
        return

    price_line = f"Price    : {price}\n" if price else ""

    msg = EmailMessage()
    msg["Subject"] = f"[Restock] {config.product_name} is IN STOCK at {config.name}"
    msg["From"]    = os.getenv("SMTP_FROM", "")
    msg["To"]      = os.getenv("ALERT_EMAIL", "")
    msg.set_content(
        f"{config.product_name} appears to be back in stock.\n\n"
        f"Retailer : {config.name}\n"
        f"{price_line}"
        f"URL      : {config.url}\n"
    )

    try:
        port = int(os.getenv("SMTP_PORT", "587"))
        with smtplib.SMTP(host, port) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASS", ""))
            smtp.send_message(msg)
        log.info("[%s] email alert sent to %s", config.name, os.getenv("ALERT_EMAIL"))
    except Exception as exc:
        log.warning("[%s] email alert failed: %s", config.name, exc)
