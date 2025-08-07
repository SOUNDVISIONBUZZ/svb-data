# sources/livenotessb.py
"""
Scrape https://livenotessb.com/ daily listings.

The HTML layout is:

<h4>… DAY – Month DD …</h4>
<p>*Venue – Artist (genre) – 6-8 pm</p>
<p>*Another Venue – …</p>
<hr/>
<h4>next day …</h4>
…

We walk every <h4>, turn its “Month DD” into a date in the *next* 12 months,
then collect the <p> siblings until we reach the next <h4> or <hr>.
"""

from __future__ import annotations
import datetime as dt, re, unicodedata, hashlib
from bs4 import BeautifulSoup
import requests

URL   = "https://livenotessb.com/"
HEAD  = {"User-Agent": "Mozilla/5.0"}
TZ    = dt.timezone(dt.timedelta(hours=-7))             # PDT
YEAR_MAX_LOOKAHEAD = 370                                # days

# ───────────────────────── helpers ─────────────────────────
MONTHS = {m.lower(): i for i, m in enumerate(("January February March April May June "
                                             "July August September October November December").split(), 1)}

def slugify(txt: str, n: int = 32) -> str:
    txt = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode()
    txt = re.sub(r"[^a-z0-9]+", "-", txt.lower()).strip("-")
    if len(txt) > n:
        txt = txt[:n].rsplit("-", 1)[0]       # avoid cutting inside a word
    return txt or hashlib.sha1(txt.encode()).hexdigest()[:8]

def next_date(month: str, day: int) -> dt.date:
    """Return the first date with that month/day in the next ~12 months."""
    today = dt.date.today()
    for add_years in (0, 1):
        try:
            d = dt.date(today.year + add_years, MONTHS[month.lower()], day)
        except ValueError:
            continue
        if 0 <= (d - today).days <= YEAR_MAX_LOOKAHEAD:
            return d
    raise ValueError("date resolution failed")

# ──────────────────────── main scrape ──────────────────────
def fetch() -> list[dict]:
    html   = requests.get(URL, headers=HEAD, timeout=20).text
    soup   = BeautifulSoup(html, "html.parser")
    events = []

    for h4 in soup.find_all("h4"):
        m = re.search(r"([A-Za-z]+)\s*–\s*([A-Za-z]+)\s+(\d{1,2})", h4.text)
        if not m:
            continue
        month, day = m.group(2), int(m.group(3))
        date = next_date(month, day)

        # iterate over the sibling tags until the next heading/hr
        for sib in h4.find_next_siblings():
            if sib.name in ("h4", "hr"):
                break
            if sib.name != "p":
                continue
            text = sib.get_text(" ", strip=True)
            # pattern: "*Venue – Artist (genre) – 5-8 pm"
            m2 = re.match(r"\*?([^–]+?)\s*–\s*([^–(]+?)\s*(?:\(([^)]+)\))?\s*–\s*([0-9:apm\- ]+)", text, re.I)
            if not m2:
                continue
            venue, title, genre, times = [x.strip() if x else "" for x in m2.groups()]
            start_str = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", times, re.I)
            if not start_str:
                continue
            hour   = int(start_str.group(1)) % 12 + (12 if start_str.group(3).lower() == "pm" else 0)
            minute = int(start_str.group(2) or 0)
            start_dt = dt.datetime.combine(date, dt.time(hour, minute), TZ)
            end_dt   = start_dt + dt.timedelta(hours=2)

            ev_id = f"lnsb-{start_dt.strftime('%Y%m%d')}-{slugify(title)}"
            events.append({
                "id":        ev_id,
                "title":     title,
                "category":  "Music",
                "genre":     genre or None,
                "city":      "Santa Barbara",   # default; fine-tune later
                "zip":       "",
                "start":     start_dt.isoformat(),
                "end":       end_dt.isoformat(),
                "venue":     venue,
                "address":   "",
                "popularity": 60,
            })

    print("✓ scraped", len(events), "LiveNotesSB events")
    return events

# keep the alias used by fetch_and_build.py
lnsb_fetch = fetch

