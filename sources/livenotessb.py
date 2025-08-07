# sources/livenotessb.py
"""
Scraper for https://livenotessb.com/  – returns a list of event dicts.

Changes:
• first try plain HTTP (often faster / no TLS timeout)
• if HTTPS is needed, retry once with verify=False
"""

from __future__ import annotations
import datetime as dt, re, unicodedata, html, time, requests
from bs4 import BeautifulSoup

BASE  = "livenotessb.com"
UA    = {"User-Agent":
         "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
         "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"}
TZ    = dt.timezone(dt.timedelta(hours=-7))       # PDT
DASH  = r"[-–—\-]"

# ───────────────────────── helpers (unchanged) ──────────────────────
MONTHS = {m.lower(): i for i, m in enumerate(
    "January February March April May June July August September October November December".split(), 1)
}
def slug(t: str, lim: int = 32) -> str:
    t = unicodedata.normalize("NFKD", t).encode("ascii","ignore").decode()
    t = re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")
    return (t[:lim].rsplit("-", 1)[0] or t) if len(t) > lim else t

def parse_date(month: str, day: int) -> dt.date:
    today = dt.date.today()
    for y in (today.year, today.year + 1):
        d = dt.date(y, MONTHS[month.lower()], day)
        if d >= today - dt.timedelta(days=2):
            return d
    return today  # shouldn’t happen

TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)", re.I)
HDR_RE  = re.compile(rf"\b([A-Za-z]+)\s*{DASH}\s*([A-Za-z]+)\s+(\d{{1,2}})", re.I)

# ───────────────────────── downloader ───────────────────────────────
def _download() -> str | None:
    urls = [f"http://{BASE}/", f"https://{BASE}/"]  # try HTTP first
    for url in urls:
        try:
            verify = url.startswith("https://")
            r = requests.get(url, headers=UA, timeout=(5, 60), verify=verify)
            r.raise_for_status()
            return r.text
        except Exception as e:
            print(f"  ↻ {url} failed ({e.__class__.__name__}); trying next …")
            time.sleep(1)
    print("  ✕ LiveNotesSB: both HTTP and HTTPS failed.")
    return None

# ───────────────────────── main fetch ──────────────────────────────
def fetch() -> list[dict]:
    raw = _download()
    if raw is None:
        return []

    soup = BeautifulSoup(raw, "html.parser")
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

    print(f"• LiveNotesSB fetch → {len(events)} events")
    return events

lnsb_fetch = fetch







