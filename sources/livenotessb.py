# sources/livenotessb.py
"""
Scraper for https://livenotessb.com/  –  returns a list of event dicts.
"""

from __future__ import annotations
import datetime as dt, re, unicodedata, html, time
from bs4 import BeautifulSoup
import requests

URL = "https://livenotessb.com/"
UA  = {
    "User-Agent":
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
}
TZ  = dt.timezone(dt.timedelta(hours=-7))        # PDT / Pacific
DASH = r"[-–—\-]"

# ────────────── helpers (unchanged) ──────────────
MONTHS = {m.lower(): i for i, m in enumerate(
    "January February March April May June July August September October November December".split(), 1)
}

def slug(txt: str, lim: int = 32) -> str:
    txt = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode()
    txt = re.sub(r"[^a-z0-9]+", "-", txt.lower()).strip("-")
    return (txt[:lim].rsplit("-", 1)[0] or txt) if len(txt) > lim else txt

def parse_date(month: str, day: int) -> dt.date:
    today = dt.date.today()
    for year in (today.year, today.year + 1):
        try:
            d = dt.date(year, MONTHS[month.lower()], day)
            if d >= today - dt.timedelta(days=2):
                return d
        except ValueError:
            pass
    raise ValueError

TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)", re.I)
HDR_RE  = re.compile(rf"\b([A-Za-z]+)\s*{DASH}\s*([A-Za-z]+)\s+(\d{{1,2}})", re.I)

# ────────────── downloader with retry ──────────────
def _get_html() -> str | None:
    for attempt in range(3):
        try:
            r = requests.get(URL, headers=UA, timeout=(5, 60))
            r.raise_for_status()
            return r.text
        except Exception as e:
            wait = 2 ** attempt
            print(f"  ↻ LiveNotesSB attempt {attempt+1}/3 failed ({e}); retrying in {wait}s …")
            time.sleep(wait)
    print("  ✕ LiveNotesSB: gave up after 3 attempts.")
    return None

# ────────────── main fetch ──────────────
def fetch() -> list[dict]:
    html_txt = _get_html()
    if html_txt is None:
        return []

    soup = BeautifulSoup(html_txt, "html.parser")
    events: list[dict] = []

    for h4 in soup.find_all("h4"):
        m = HDR_RE.search(h4.get_text(" ", strip=True).replace("\xa0", " "))
        if not m:
            continue
        month, day = m.group(2), int(m.group(3))
        ev_date = parse_date(month, day)

        for p in h4.find_next_siblings():
            if p.name in ("h4", "hr"):
                break
            if p.name != "p":
                continue

            txt = html.unescape(p.get_text(" ", strip=True).replace("\xa0", " "))
            parts = re.split(rf"\s*{DASH}\s*", txt, maxsplit=2)
            if len(parts) < 3:
                continue

            venue, artist, rest = map(str.strip, parts[:3])

            genre = None
            g = re.search(r"\(([^)]+)\)", artist)
            if g:
                genre = g.group(1).strip()
                artist = artist[:g.start()].strip()

            t = TIME_RE.search(rest)
            if not t:
                continue
            hr = int(t.group(1)) % 12 + (12 if t.group(3).lower() == "pm" else 0)
            mn = int(t.group(2) or 0)
            start = dt.datetime.combine(ev_date, dt.time(hr, mn), TZ)
            end   = start + dt.timedelta(hours=2)

            events.append({
                "id"      : f"lnsb-{start:%Y%m%d}-{slug(artist or venue)}",
                "title"   : artist or venue,
                "category": "Music",
                "genre"   : genre,
                "city"    : "Santa Barbara",
                "zip"     : "",
                "start"   : start.isoformat(),
                "end"     : end.isoformat(),
                "venue"   : venue,
                "address" : "",
                "popularity": 60,
            })

    print(f"• LiveNotesSB fetch — {len(events)} events")
    return events

lnsb_fetch = fetch






