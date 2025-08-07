# sources/livenotessb.py
"""
Tiny scraper for LiveNotesSB.com – no Selenium, runs quickly in GitHub Actions.

• Pulls the front page that lists day-by-day live-music schedules.
• Extracts every bullet that looks like “Venue – Artist (style) – 5-8 pm”.
• Produces an event-dict list compatible with the rest of the `svb-data`
  toolchain (same shape as the hand-written `events.json` records).

Notes
-----
* The site is WordPress; headings are like `<h4>TUESDAY – August 5</h4>`
  and each bullet is inside a `<p>` that begins with an asterisk “*”.
* IDs are generated `lnsb-YYYY-MM-DD-slugified-title`.
* Only Santa Barbara-county cities appear, so no geo-filter is applied here.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
import requests
from bs4 import BeautifulSoup

BASE = "https://livenotessb.com"

# ── helper ──────────────────────────────────────────────────────────────
def _download(timeout: int = 20) -> str:
    """Return raw HTML from the LiveNotesSB front page (debug / local use)."""
    return requests.get(
        BASE, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout
    ).text
# -----------------------------------------------------------------------


MONTH_RE  = r"(January|February|March|April|May|June|July|August|September|October|November|December)"
HDR_RE    = re.compile(rf"{MONTH_RE}\s+\d{{1,2}}", re.I)          # e.g. “August 5”
TIME_RE   = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.I) # crude time capture


def _iso(raw_date: str, raw_time: str, tz: str = "-07:00") -> str:
    """
    Combine pieces → ISO-8601 string. Examples
        raw_date = 'August 5 2025'
        raw_time = '5-8 pm'   (we’ll look at the first time only)
    """
    m = TIME_RE.search(raw_time)
    if not m:
        raise ValueError(f"time not found: {raw_time!r}")
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    if m.group(3).lower() == "pm" and hour != 12:
        hour += 12

    dt_obj = dt.datetime.strptime(raw_date, "%B %d %Y").replace(
        hour=hour, minute=minute
    )
    return dt_obj.isoformat() + tz


def _slug(text: str, maxlen: int = 40) -> str:
    """Simple slugify → lower-case, ascii, hyphens."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:maxlen] or "event"


def fetch() -> list[dict]:
    """Return a list of event dicts collected from LiveNotesSB."""
    print("• LiveNotesSB fetch")
    html = _download()
    soup = BeautifulSoup(html, "html.parser")

    events: list[dict] = []
    today_year = dt.datetime.now().year

    # walk <h4> headings (each date) ------------------------
    for h4 in soup.find_all("h4"):
        hdr_txt = h4.get_text(" ", strip=True).replace("\xa0", " ")
        if not HDR_RE.search(hdr_txt):
            continue  # skip non-date headings

        # 'TUESDAY – August 5'  →  'August 5 <current-year>'
        parts = hdr_txt.split("–")[-1].strip()   # keep “August 5”
        date_str = f"{parts} {today_year}"

        # the bullets live in subsequent <p> tags until next <hr>/<h4>
        for sibling in h4.find_all_next(["p", "h4", "hr"], limit=200):
            if sibling.name in ("h4", "hr"):
                break
            txt = sibling.get_text(" ", strip=True).replace("\xa0", " ")
            if not txt.startswith("–") and "*" not in txt:
                continue  # skip paragraphs that aren’t bullets

            # crude split: "– Venue – Artist (style) – 5-8 pm"
            bits = [b.strip("– ").strip() for b in txt.split("–") if b.strip()]
            if len(bits) < 2:
                continue

            venue  = bits[0]
            title  = bits[1]
            time_s = bits[-1]

            try:
                start_iso = _iso(date_str, time_s)
            except ValueError:
                continue  # skip if time parse fails

            ev_id = f"lnsb-{start_iso[:10]}-{_slug(title)}"

            events.append(
                {
                    "id":       ev_id,
                    "title":    title,
                    "category": "Music",
                    "genre":    "Live",          # unknown; could be refined later
                    "city":     "",              # city not easily parsed from bullet
                    "zip":      "",
                    "start":    start_iso,
                    "end":      "",              # unknown duration
                    "venue":    venue,
                    "address":  "",
                    "popularity": 50,            # neutral default
                }
            )

    print(f"  ↳ {len(events)} LiveNotesSB events")
    return events








