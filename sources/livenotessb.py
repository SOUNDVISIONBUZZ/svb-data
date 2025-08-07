# sources/livenotessb.py
"""
Scraper for https://livenotessb.com/

Grabs each <h4> header like  “TUESDAY – August 5”
then every <p> until the next <h4>/<hr>, looking for lines:

  *Venue – Artist (genre) – 5-8 pm

• Accepts normal / en / em dashes.
• Converts NBSPs to normal spaces.
• Creates an id  lnsb-YYYYMMDD-slug .
"""

from __future__ import annotations
import datetime as dt, re, unicodedata, html
from bs4 import BeautifulSoup
import requests

URL   = "https://livenotessb.com/"
HEAD  = {"User-Agent": "Mozilla/5.0"}
TZ    = dt.timezone(dt.timedelta(hours=-7))          # PDT / Santa Barbara
DLASH = "-–—-"                                      # hyphen, en-dash, em-dash

MONTH_NUM = {m.lower(): i for i, m in enumerate(
    "January February March April May June July August September October November December".split(), 1)
}

def slug(txt: str, limit: int = 32) -> str:
    txt = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode()
    txt = re.sub(r"[^a-z0-9]+", "-", txt.lower()).strip("-")
    return (txt[:limit].rsplit("-", 1)[0] or txt) if len(txt) > limit else txt

def next_date(month: str, day: int) -> dt.date:
    today = dt.date.today()
    for add_year in (0, 1):
        try:
            d = dt.date(today.year + add_year, MONTH_NUM[month.lower()], day)
        except ValueError:
            continue
        if d >= today - dt.timedelta(days=2):       # allow 48 h past
            return d
    raise ValueError("unusable date in header")

TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)", re.I)
HDR_RE  = re.compile(rf"\b([A-Za-z]+)\s*[{DLASH}]\s*([A-Za-z]+)\s+(\d{{1,2}})", re.I)
ROW_RE  = re.compile(
    rf"^\*?\s*(?P<venue>[^ {DLASH}][^{DLASH}]+?)\s*[{DLASH}]\s*"
    rf"(?P<artist>[^ {DLASH}][^{DLASH}]+?)\s*[{DLASH}]\s*"
    rf"(?P<time>.+?)$"
)

def fetch() -> list[dict]:
    html_text = requests.get(URL, headers=HEAD, timeout=20).text
    soup = BeautifulSoup(html_text, "html.parser")

    events: list[dict] = []

    for h4 in soup.find_all("h4"):
        header = h4.get_text(" ", strip=True).replace("\u00a0", " ")
        m = HDR_RE.search(header)
        if not m:
            continue
        month, day = m.group(2), int(m.group(3))
        e_date = next_date(month, day)

        for tag in h4.find_next_siblings():
            if tag.name in ("h4", "hr"):
                break
            if tag.name != "p":
                continue

            text = tag.get_text(" ", strip=True).replace("\u00a0", " ")
            text = html.unescape(text)
            row = ROW_RE.match(text)
            if not row:
                continue

            venue  = row["venue"].strip()
            artist = row["artist"].strip()

            # optional (genre) inside artist
            genre = None
            g = re.search(r"\(([^)]+)\)", artist)
            if g:
                genre = g.group(1).strip()
                artist = artist[:g.start()].strip()

            t = TIME_RE.search(row["time"])
            if not t:
                continue
            hour = int(t.group(1)) % 12 + (12 if t.group(3).lower() == "pm" else 0)
            minute = int(t.group(2) or 0)
            start = dt.datetime.combine(e_date, dt.time(hour, minute), TZ)
            end   = start + dt.timedelta(hours=2)

            ev_id = f"lnsb-{start:%Y%m%d}-{slug(artist or venue)}"
            events.append({
                "id": ev_id,
                "title": artist or venue,
                "category": "Music",
                "genre": genre,
                "city": "Santa Barbara",
                "zip": "",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "venue": venue,
                "address": "",
                "popularity": 60,
            })

    print(f"• LiveNotesSB fetch\n  ↳ {len(events)} LiveNotesSB events")
    return events

# alias
lnsb_fetch = fetch




