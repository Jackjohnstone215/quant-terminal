"""Push a concise alert about the day's quant scan to Telegram (optional).

Enabled only when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set (e.g. as GitHub Actions
secrets). Without them, every function is a safe no-op, so the scheduled scan is completely
unaffected. Uses only the Python standard library — no new dependencies. Public Telegram Bot API.

Thresholds are env-tunable so you can tighten/loosen the alerts without code changes:
  NOTIFY_TOP_N            (default 5)   max ideas per message
  NOTIFY_MIN_CONVICTION   (default 65)  only alert on ideas at/above this conviction score
"""
import os
import json
import urllib.request
import urllib.parse

APP_URL = "https://quant-terminal-museq45xbpxspebjedgotf.streamlit.app/"


def _config():
    return os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")


def telegram_enabled():
    tok, chat = _config()
    return bool(tok and chat)


def send_telegram(text):
    """Send one HTML message. Returns True on success. Safe no-op (returns False) if the bot
    token / chat id aren't configured, and never raises — a notification must not break a scan."""
    tok, chat = _config()
    if not (tok and chat):
        return False
    url = f"https://api.telegram.org/bot{tok}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
            return bool(json.loads(r.read().decode()).get("ok"))
    except Exception as e:
        print(f"Telegram send failed: {str(e)[:140]}", flush=True)
        return False


def _num(row, key, default=None):
    try:
        v = row.get(key, default)
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def build_scan_alert(rows, label=""):
    """Format an HTML Telegram message for the day's most notable freshly-scanned ideas, ranked
    by Research Priority and filtered to a conviction floor. Returns None when nothing clears the
    bar, so quiet days send no message (no noise)."""
    top_n = int(os.getenv("NOTIFY_TOP_N", "5"))
    min_conv = float(os.getenv("NOTIFY_MIN_CONVICTION", "65"))

    picks = [r for r in rows if (_num(r, "Conviction Score") or 0) >= min_conv]
    if not picks:
        return None
    picks.sort(key=lambda r: (_num(r, "Research Priority", 0) or 0), reverse=True)
    picks = picks[:top_n]

    header = f"📈 <b>Quant scan — {label}</b>" if label else "📈 <b>Quant scan</b>"
    lines = [header, f"{len(picks)} idea(s) cleared the bar (conviction ≥ {min_conv:.0f}):", ""]
    for r in picks:
        tkr = r.get("Ticker", "?")
        name = r.get("Company", "") or ""
        conv = _num(r, "Conviction Score")
        prio = _num(r, "Research Priority")
        up = _num(r, "Upside %")
        tier = r.get("Tier") or r.get("Research Action") or ""
        up_s = f" · {up:+.0f}% upside" if up is not None else ""
        lines.append(f"<b>{tkr}</b> — {name}")
        bits = []
        if conv is not None:
            bits.append(f"conviction {conv:.0f}")
        if prio is not None:
            bits.append(f"priority {prio:.0f}")
        lines.append("  " + " · ".join(bits) + up_s)
        if tier:
            lines.append(f"  <i>{tier}</i>")
        lines.append("")
    lines.append(f'<a href="{APP_URL}">Open the terminal ↗</a>')
    return "\n".join(lines)
