# sources/livenotessb.py
"""
Scrape daily listings from https://livenotessb.com/

• Each day starts with   <h4>DAY – Month DD</h4>
• Each event is a <p> beginning with an asterisk:
    *Venue – Artist (genre) – 5-8 pm

We resolve the (Month DD) to the next matching calendar date (this year
or next), assume Pacific time, and give each event a 2-hour duration.
"""

from __future__ import annotations
import datetime as dt, re, unicodedata, hashlib
from bs4 import BeautifulSoup
import requests

URL   = "https://livenotessb.com/"
HEAD  = {"User-Agent": "Mozilla/5.0"}
TZ    = dt.timezone(dt.timedelta(hours=-7))      # PDT
LOOKAHEAD_DAYS = 370                             # keep ~one year out

# ── helpers ─────────────────────────────────────────────────────────
MONTH_NUM = {m.lower(): i for i, m in enumerate(
    "January February March April May June July August September October November December".split(), 1)
}

DASH = r"[-–—\-]"          # hyphen / en-dash / em-dash / minus

def slug(txt: str, limit: int = 32) -> str:
    txt = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode()
    txt = re.sub(r"[^a-z0-9]+", "-", txt.lower()).strip("-")
    if len(txt) > limit:
        txt = txt[:limit].rsplit("-", 1)[0]
    return txt or hashlib.sha1(txt.encode()).hexdigest()[:8]

def next_calendar_date(month: str, day: int) -> dt.date:
    today = dt.date.today()
    for add in (0, 1):
        try:
            candidate = dt.date(today.year + add, MONTH_NUM[month.lower()], day)
        except ValueError:
            continue
        if 0 <= (candidate - today).days <= LOOKAHEAD_DAYS:
            return candidate
    raise ValueError("unable to resolve date")

# ── core scrape ─────────────────────────────────────────────────────
def fetch() -> list[dict]:
    html = requests.get(URL, headers=HEAD, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")
    events: list[dict] = []

    # iterate over every day header
    for h4 in soup.find_all("h4"):
        m = re.search(fr"\b([A-Za-z]+)\s*{DASH}\s*([A-Za-z]+)\s+(\d{{1,2}})", h4.get_text(" ", strip=True))
        if not m:
            continue
        month, day = m.group(2), int(m.group(3))
        event_date  = next_calendar_date(month, day)

        # walk <p> siblings until the next header or <hr>
        for sib in h4.find_next_siblings():
            if sib.name in ("h4", "hr"):
                break
            if sib.name != "p":
                continue
            text = sib.get_text(" ", strip=True)

            # *Venue – Artist (genre) – 7 pm   (anything after time is ignored)
            p = re.match(
                fr"\*?\s*([^ {DASH}]+(?: [^ {DASH}]+)*)\s*{DASH}\s*"
                fr"([^({DASH}]+?)\s*(?:\(([^)]+)\))?\s*{DASH}\s*"
                fr"([0-9]{{1,2}}(?::[0-9]{{2}})?\s*[ap]m)",
                text, re.I
            )
            if not p:
                continue

            venue, title, genre, time_str = (x.strip() if x else "" for x in p.groups())

            tmatch = re.match(r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)", time_str, re.I)
            if not tmatch:
                continue
            hour = int(tmatch.group(1)) % 12 + (12 if tmatch.group(3).lower() == "pm" else 0)
            minute = int(tmatch.group(2) or 0)

            start_dt = dt.datetime.combine(event_date, dt.time(hour, minute), TZ)
            end_dt   = start_dt + dt.timedelta(hours=2)

            ev_id = f"lnsb-{start_dt:%Y%m%d}-{slug(title)}"
            events.append({
                "id":        ev_id,
                "title":     title,
                "category":  "Music",
                "genre":     genre or None,
                "city":      "Santa Barbara",
                "zip":       "",
                "start":     start_dt.isoformat(),
                "end":       end_dt.isoformat(),
                "venue":     venue,
                "address":   "",
                "popularity": 60,
            })

    print("• LiveNotesSB fetch\n  ↳", len(events), "LiveNotesSB events")
    return events

# alias expected by fetch_and_build.py
lnsb_fetch = fetch


