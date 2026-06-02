"""
preorder_detect.py — decide when a watched item becomes orderable.

This is the *decision* layer. Your Pokepad monitor does the polite page
check (fetch + parse, skipping anything that throws a bot-check) and hands
this module a few simple signals it extracted. This module classifies the
state and tells you whether to fire an alert — treating a PRE-ORDER as a
win just like an in-stock restock.

It deliberately does NOT fetch anything itself, so all the "respect
robots.txt / skip if blocked / polite intervals" rules stay in one place
upstream in your monitor.

States:
  UNLISTED     - search returned nothing / product page 404 (not listed yet)
  COMING_SOON  - page exists but no buy button ("coming soon", announced only)
  PREORDER     - orderable now as a pre-order  -> ALERT
  IN_STOCK     - orderable now, ships now       -> ALERT
  OUT_OF_STOCK - listed but sold out
  BLOCKED      - the check hit a bot-wall; we couldn't tell (never alerts)

Fire an alert on a transition INTO an orderable state (PREORDER or IN_STOCK)
from a non-orderable one. That catches a set the moment a pre-order opens.
"""

UNLISTED     = "unlisted"
COMING_SOON  = "coming_soon"
PREORDER     = "preorder"
IN_STOCK     = "in_stock"
OUT_OF_STOCK = "out_of_stock"
BLOCKED      = "blocked"

ORDERABLE = {PREORDER, IN_STOCK}


def classify(signals):
    """Turn raw signals from your scraper into one of the states above.

    `signals` is a dict your monitor fills in from the page it just checked:
      - blocked (bool):        the check hit a CAPTCHA/queue/bot-wall
      - listed (bool):         a product/search result exists at all
      - result_count (int):    for SEARCH pages, how many items matched
      - buy_text (str):        the buy button's label, lowercased, "" if none
                               e.g. "pre-order", "add to cart", "sold out",
                               "coming soon", "notify me"
    Any missing key is treated as falsy/empty.
    """
    if signals.get("blocked"):
        return BLOCKED

    # Search pages: nothing matched yet = not listed.
    if "result_count" in signals and signals.get("result_count", 0) <= 0:
        return UNLISTED

    if not signals.get("listed", signals.get("result_count", 0) > 0):
        return UNLISTED

    buy = (signals.get("buy_text") or "").lower()

    if "pre-order" in buy or "preorder" in buy or "pre order" in buy:
        return PREORDER
    if "add to cart" in buy or "buy now" in buy or "add to bag" in buy:
        return IN_STOCK
    if "sold out" in buy or "out of stock" in buy:
        return OUT_OF_STOCK
    if "coming soon" in buy or "notify" in buy or buy == "":
        return COMING_SOON

    # Listed, unknown button -> safest to treat as not-yet-orderable.
    return COMING_SOON


def should_alert(previous_state, current_state):
    """True only when we cross from non-orderable into orderable.

    Never alerts on BLOCKED (we genuinely don't know), and never re-alerts
    while it simply stays orderable.
    """
    if current_state not in ORDERABLE:
        return False
    if previous_state in ORDERABLE:
        return False          # already alerted last time; don't repeat
    return True               # non-orderable -> orderable = the moment we want


def alert_label(state):
    """Human text for the notification so you know which kind of win it is."""
    return {
        PREORDER: "PRE-ORDER OPEN",
        IN_STOCK: "IN STOCK",
    }.get(state, state.upper())


if __name__ == "__main__":
    # Tiny demo of the transitions — no network involved.
    timeline = [
        {"result_count": 0},                          # not listed yet
        {"listed": True, "buy_text": "Coming Soon"},  # announced
        {"listed": True, "buy_text": "Pre-Order"},    # <-- should alert
        {"listed": True, "buy_text": "Pre-Order"},    # still preorder, no repeat
        {"listed": True, "buy_text": "Sold Out"},     # preorder closed
        {"listed": True, "buy_text": "Add to Cart"},  # <-- should alert (live)
    ]
    prev = None
    for sig in timeline:
        state = classify(sig)
        fire = should_alert(prev, state)
        flag = f"  *** ALERT: {alert_label(state)} ***" if fire else ""
        print(f"{state:<12} (from {str(prev):<12}){flag}")
        prev = state
