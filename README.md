# Restock Monitor · Pokepad

Async, polite retail restock watcher. Polls product pages for stock changes and fires alerts the moment something comes back in stock.

## Features

- One TOML file per retailer in `sites/` — easy to add, easy to pause (rename to `*.toml.off`)
- CSS selector, JSON API, or RSS/Atom feed stock detection
- Configurable poll intervals (minimum 30 s) + randomized jitter per site
- Single shared `httpx` async client per site with HTTP/2
- Exponential back-off on errors: 120 s → 240 s → 480 s → 600 s cap
- Block detection (CAPTCHA, 403, 429, Cloudflare challenge) — logs and skips, no bypass attempted
- Alerts: Discord embed, Pushover push, Twilio SMS, SMTP email, browser open — toggled via `NOTIFY_CHANNELS`
- Live console dashboard printed every `DASHBOARD_INTERVAL` seconds
- `logs/status.json` written after every poll — machine-readable for scripts or health checks

## Quick start

### 1. Install

```bash
cd restock-monitor
pip install -e .
# or with uv:
uv pip install -e .
```

### 2. Configure secrets

```bash
cp .env.example .env
# edit .env — add SMTP credentials and/or a webhook URL
```

### 3. Add a site

Copy the closest example from `sites/` and rename it (drop `_example`):

```bash
cp sites/bestbuy_example.toml sites/bestbuy.toml
# edit sites/bestbuy.toml — set the URL, selector, and product name
```

### 4. Run

**Web dashboard** (browser):
```bash
python serve.py
# open http://localhost:8000
```

**Desktop app** (native window via pywebview):
```bash
pip install pywebview   # one-time
python desktop.py
```
Opens a native window on a free localhost port. Closing the window shuts the server cleanly.

**CLI monitor only** (no dashboard):
```bash
python monitor.py
```

Logs go to stdout **and** `logs/monitor.log`.
A summary table is printed every 60 seconds (override with `DASHBOARD_INTERVAL=N`).
`logs/status.json` is written after every individual poll — useful for scripts.

---

## Site config reference

```toml
[site]
name          = "Retailer Name"
url           = "https://example.com/product-page"
poll_interval = 120   # seconds between polls (default: 60)
jitter        = 30    # random 0–N extra seconds added each cycle (default: 15)

[product]
name = "Human-readable product name"  # used in alert messages

[stock]
# ── HTML / CSS mode ───────────────────────────────────
type              = "css"
selector          = ".add-to-cart-button"   # CSS selector targeting the stock element
in_stock_text     = "Add to Cart"           # substring present when IN stock
out_of_stock_text = "Sold Out"              # substring present when OUT of stock

# ── JSON API mode ─────────────────────────────────────
# type           = "json"
# json_path      = "data.availability.status"   # JMESPath expression
# in_stock_value = "IN_STOCK"                   # value that means in-stock

# ── Optional per-site headers ─────────────────────────
[extra_headers]
# "Accept-Language" = "en-US,en;q=0.9"
```

### Finding the right selector

1. Open the product page in Chrome/Firefox.
2. Right-click the "Add to Cart" / "Out of Stock" button → **Inspect**.
3. Note the class or `data-*` attribute that changes between states.
4. Test in the browser console: `document.querySelectorAll('.your-selector')`.

For JSON APIs: open DevTools → **Network** tab → filter **Fetch/XHR** → reload the product page → look for requests returning availability data.

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `USER_AGENT` | Chrome-like string | Sent with every request |
| `REQUEST_TIMEOUT` | `15` | Seconds before giving up on a request |
| `NOTIFY_CHANNELS` | `discord` | Comma-separated active channels: `discord` `pushover` `twilio` `email` `browser` |
| `DASHBOARD_INTERVAL` | `60` | Seconds between console table refreshes; `0` disables the table |
| `DISCORD_WEBHOOK_URL` | — | Discord webhook URL |
| `PUSHOVER_APP_TOKEN` | — | Pushover application token |
| `PUSHOVER_USER_KEY` | — | Pushover user/group key |
| `PUSHOVER_PRIORITY` | `1` | `1` = high (bypasses quiet hours), `0` = normal |
| `TWILIO_ACCOUNT_SID` | — | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | — | Twilio auth token |
| `TWILIO_FROM` | — | Twilio sender number (E.164) |
| `TWILIO_TO` | — | Recipient number (E.164) |
| `SMTP_HOST` | — | SMTP server (e.g. `smtp.gmail.com`) |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | — | SMTP login |
| `SMTP_PASS` | — | SMTP password / app password |
| `SMTP_FROM` | — | Sender address |
| `ALERT_EMAIL` | — | Recipient address |
| `OPEN_BROWSER` | `0` | Legacy alias for adding `browser` to `NOTIFY_CHANNELS` |

---

## Block handling

If a site returns HTTP 403/429/503, a CAPTCHA page, or a Cloudflare challenge, the monitor logs `BLOCKED` and skips that poll. No bypass is attempted. The monitor will retry at the next normal interval.

If a site consistently blocks the monitor, the practical options are:
- Increase `poll_interval` to reduce request frequency
- Check whether the site exposes a public stock API (JSON mode) instead of the HTML page
- Accept that the site cannot be monitored without violating its ToS

---

## Respecting robots.txt and rate limits

Using this monitor responsibly means treating each retailer's infrastructure as a shared resource.

### Before you add a site

1. **Check `robots.txt`** — fetch `https://<retailer>/robots.txt` and look for rules that apply to your User-Agent or the path you want to poll. If the path is disallowed, use a different signal (a JSON API, RSS feed, or email subscription the retailer provides) instead of polling the HTML page.

2. **Prefer official data sources** — many retailers publish a stock API, a product RSS feed, or an "email me when available" notification. These are sanctioned channels that don't add load to their serving infrastructure. Use them when they exist.

3. **Read the Terms of Service** — automated access is explicitly prohibited on some sites. "Technical feasibility" is not the same as "permission." A monitoring bot that repeatedly hammers a retailer's servers may constitute a ToS violation or, at scale, unwanted interference.

### Interval guidelines

| Context | Recommended `poll_interval` |
|---|---|
| High-demand product at launch | 120–300 s |
| Normal product monitoring | 60–120 s |
| Low-traffic / archive page | 30–60 s |
| JSON or RSS API endpoint | 60 s minimum |

The hard-coded floor is **30 seconds** — the loader will clamp and warn on anything lower. Jitter (default ±15 s) is applied on top to avoid thundering-herd if you run multiple monitors.

### Exponential back-off

On repeated request errors the poller automatically backs off:

```
1st error  → wait 120 s
2nd error  → wait 240 s
3rd error  → wait 480 s
4th+ error → wait 600 s (cap)
```

This prevents hammering a temporarily overloaded server and is reset as soon as a successful response is received.

---

## Adding a new retailer — checklist

- [ ] Check `robots.txt` and ToS (see above)
- [ ] Prefer a JSON API or RSS feed over the HTML product page where available
- [ ] Find the product URL (or API/feed endpoint)
- [ ] Identify the stock element (CSS selector, JMESPath, or RSS keyword)
- [ ] Add optional `price_selector` / `price_json_path` under `[product]` if you want price in alerts
- [ ] Create `sites/<retailer>.toml`
- [ ] Test with `poll_interval = 60` and watch the console table for a few cycles to confirm detection works

---

## App icon

The Pokepad icon (pixel radar emblem on a night-sky tile) lives at `web/static/icons/pokepad.svg`.

### Generated files

| File | Use |
|---|---|
| `web/static/icons/pokepad-1024.png` | Master source PNG |
| `web/static/icons/pokepad-512.png` | Web app icon |
| `web/static/icons/favicon.ico` | Browser favicon (16 / 32 / 48) |
| `web/static/icons/pokepad.ico` | Windows app icon (16 / 32 / 48 / 256) |
| `web/static/icons/pokepad.icns` | macOS app icon |

### Regenerating icons

If you edit `pokepad.svg`, re-run:

```bash
pip install Pillow   # one-time
python3 scripts/gen_icons.py
```

Requires macOS for `.icns` (uses the built-in `iconutil`). The `.ico` and `.png` outputs work on any platform.

### Building a native app (PyInstaller)

```bash
pip install pyinstaller
pyinstaller pokepad.spec
# → dist/Pokepad.app  (macOS)
# → dist/Pokepad.exe  (Windows — change icon= in pokepad.spec to pokepad.ico first)
```
