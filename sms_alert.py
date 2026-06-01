"""
sms_alert.py — send a restock text to one or more phones via Twilio.

Setup (one time):
  1. pip install twilio
  2. Make a free Twilio account, get a sending number, and note your
     Account SID + Auth Token (twilio.com/console).
  3. Put your credentials in environment variables (recommended) OR
     paste them into the CONFIG block below.

US note: carriers require SMS senders to register (A2P 10DLC) before
texts flow reliably — Twilio walks you through it at signup. And only
text people who've agreed to get the alerts.
"""

import os
from twilio.rest import Client

# ---------------------------------------------------------------------------
# CONFIG — fill these in (or set them as environment variables of the same name)
# ---------------------------------------------------------------------------
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "your_account_sid_here")
TWILIO_AUTH_TOKEN  = os.environ.get("TWILIO_AUTH_TOKEN",  "your_auth_token_here")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM",        "+15551234567")  # your Twilio number

# Numbers to text. Add your buddies here. Use E.164 format: +1 then 10 digits.
# You can also set TWILIO_TO as a comma-separated list in .env and it will
# override this list at runtime.
RECIPIENTS = [
    "+15550000001",   # me
    # "+15550000002", # Jake
    # "+15550000003", # Sam
]
# ---------------------------------------------------------------------------


def send_restock_alert(retailer, product, url, price=None, recipients=None):
    """Text every recipient that `product` is back in stock at `retailer`.

    Returns a list of (number, "sent"/"failed: reason") so you can see results.
    """
    if recipients is None:
        # Check TWILIO_TO env var (supports comma-separated for multiple numbers)
        env_to = os.environ.get("TWILIO_TO", "")
        recipients = [n.strip() for n in env_to.split(",") if n.strip()] or RECIPIENTS

    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    price_str = f" — {price}" if price else ""
    # Kept short so it doesn't split into multiple texts.
    body = f"RESTOCK: {retailer} — {product}{price_str}\nBuy: {url}"

    results = []
    for number in recipients:
        try:
            client.messages.create(body=body, from_=TWILIO_FROM_NUMBER, to=number)
            results.append((number, "sent"))
        except Exception as e:
            results.append((number, f"failed: {e}"))
    return results


if __name__ == "__main__":
    # Quick test — sends a sample text to everyone in RECIPIENTS (or TWILIO_TO).
    outcome = send_restock_alert(
        retailer="Best Buy",
        product="Surging Sparks Elite Trainer Box",
        url="https://www.bestbuy.com/site/shop/pokemon-tcg",
        price="$59.99",
    )
    for number, status in outcome:
        print(f"{number}: {status}")
