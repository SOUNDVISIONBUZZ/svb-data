# sources/lnsb_fetch.py
# LiveNotesSB scraper (bullet/dash/pipe tolerant) with debug outputs.

import datetime as dt
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

SITE = "https://livenotessb.com"
UA = "Mozilla/5.0 (SVB/1.0; +https://github.com/SOUNDVISIONBUZZ/svb-data)"
ROOT = Path(__file__).resolve().parent.parent
DEBUG_DIR = ROOT / "tmp_lnsb"
DEBUG_DIR.mkdir(exist_ok=True)

REGION_HEADERS = {
    "CARPINTERIA", "SANTA BARBARA", "GOLETA/I.V", "GOLETA",
    "SANTA YNEZ/LOS OLIVOS", "SANTA YNEZ", "LOS OLIVOS", "SOLVANG",
}
BLACKLIST_TITLES = {"first thursday hosted by downtown sb", "august", "ios app", "android app"}

VENUE_REGISTRY: Dict[str, Dict[str, str]] = {
    "Corktree Cellars":{"address":"910 Linden Ave","city":"Carpinteria","zip":"93013"},
    "Corks & Crowns":{"address":"32 Anacapa St","city":"Santa Barbara","zip":"93101"},
    "The Red Piano":{"address":"519 State St","city":"Santa Barbara","zip":"93101"},
    "Soho":{"address":"1221 State St","city":"Santa Barbara","zip":"93101"},
    "Anchor Rose":{"address":"113 Harbor Way","city":"Santa Barbara","zip":"93109"},
    "Villa Wine Bar & Kitchen":{"address":"618 Anacapa St","city":"Santa Barbara","zip":"93101"},
    "Satellite":{"address":"1117 State St","city":"Santa Barbara","zip":"93101"},
    "The Good Lion":{"address":"1212 State St","city":"Santa Barbara","zip":"93101"},
    "El Encanto, a Belmond Hotel":{"address":"800 Alvarado Pl","city":"Santa Barbara","zip":"93103"},
    "Validation Ale":{"address":"102 E Yanonali St","city":"Santa Barbara","zip":"93101"},
    "Institution Ale":{"address":"516 State St","city":"Santa Barbara","zip":"93101"},
    "The Leta Hotel":{"address":"5650 Calle Real","city":"Goleta","zip":"93117"},
    "Maverick Saloon":{"address":"3687 Sagunto St","city":"Santa Ynez","zip":"93460"},
    "Lost Chord Guitars":{"address":"1576 Copenhagen Dr","city":"Solvang","zip":"93463"},
    "Alisal River Grill/ Alisal Ranch":{"address":"150 Alisal Rd","city":"Solvang","zip":"93463"},
    "SloDoCo":{"address":"", "city":"Goleta","zip":""},
    "ITH Santa Barbara Beach Hostel":{"address":"134 Chapala St","city":"Santa Barbara","zip":"93101"},
    "Reef & Run":{"address":"Cabrillo Blvd","city":"Santa Barbara","zip":"93101"},
    "Brothers Red Barn":{"address":"3539 Sagunto St","city":"Santa Ynez","zip":"93460"},
    "The V Lounge":{"address":"1455 Mission Dr","city":"Solvang","zip":"93463"},
    "800 Block of State Street":{"address":"800 State St","city":"Santa Barbara","zip":"93101"},
}

def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def _slug(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s

def _fetch_html(url: str) -> str:
    name = url.strip("/").split("/")[-1] or "index"
    cache = DEBUG_DIR / f"{name}.html"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
        r.raise_for_status()
        html = r.text
        cache.write_text(html, encoding="utf-8")
        return html
    except Exception:
        if cache.exists():
            return cache.read_text(encoding="utf-8")
        raise

def _visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.extract()
    text = soup.get_text(separator="\n")
    text = text.replace("\u00a0"," ")
    text = re.sub(r"[ \t]+"," ", text)
    text = re.sub(r"\n{2,}","\n", text)
    return text.strip()

# time patterns: "6-9 pm", "8 pm-12 am", "6 pm", "7-10pm"
TIME_ANY_RE = re.compile(
    r"(?:(\d{1,2})(?::(\d{2}))?\s*-\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm))|"  # 6-9 pm / 6:30-9:15 pm
    r"(?:(\d{1,2})(?::(\d{2}))?\s*(am|pm))|"                                # 6 pm / 6:30 pm
    r"(?:(\d{1,2})\s*-\s*(\d{1,2})\s*(am|pm))",                             # 6-9 pm (single am/pm)
    re.I,
)

# triple pattern: Venue – Title – Time  OR Venue | Title | Time  (accept -, –, —)
TRIPLE_RE = re.compile(r"""
    (?P<venue> [^\n|–—-]{2,120}? )
    \s*(?:\||–|—|-)\s*
    (?P<title> [^|–—-\n]{2,240}? )
    \s*(?:\||–|—|-)\s*
    (?P<time>
       (?:\d{1,2}(?::\d{2})?\s*-\s*\d{1,2}(?::\d{2})?\s*(?:am|pm))|
       (?:\d{1,2}\s*-\s*\d{1,2}\s*(?:am|pm))|
       (?:\d{1,2}(?::\d{2})?\s*(?:am|pm))
    )
""", re.I | re.X)

SEP_RE = re.compile(r"\s*(?:\||–|—|-)\s*")

def _start_time_from_text(s: str) -> Optional[dt.time]:
    m = TIME_ANY_RE.search(s)
    if not m:
        return None
    if m.group(1):  # range with explicit am/pm after
        h = int(m.group(1)); mm = int(m.group(2) or 0); ap = m.group(5).lower()
    elif m.group(6):  # single time
        h = int(m.group(6)); mm = int(m.group(7) or 0); ap = m.group(8).lower()
    else:  # 9/10/11 groups
        h = int(m.group(9)); mm = 0; ap = m.group(11).lower()
    if ap == "pm" and h < 12: h += 12
    if ap == "am" and h == 12: h = 0
    return dt.time(h, mm)

def _split_bullets(text: str) -> List[str]:
    norm = text.replace(" – ", " - ").replace(" — ", " - ")
    raw = re.split(r"\s\*\s|\n", norm)
    return [_clean(x) for x in raw if _clean(x)]

def _extract_from_segment(seg: str) -> Optional[Tuple[str, str, str]]:
    s = _clean(seg)
    if not s:
        return None
    if s.upper() in REGION_HEADERS or s.upper().startswith("AUGUST "):
        return None
    if not TIME_ANY_RE.search(s):
        return None

    if s.count("|") >= 2:
        parts = [_clean(p) for p in s.split("|") if _clean(p)]
        if len(parts) >= 3:
            return (parts[0], _clean(" | ".join(parts[1:-1])), parts[-1])

    parts = [_clean(p) for p in SEP_RE.split(s) if _clean(p)]
    if len(parts) >= 3:
        return (parts[0], _clean(" - ".join(parts[1:-1])), parts[-1])

    return None

def _build_event(day: dt.date, venue: str, title: str, start_time: Optional[dt.time]) -> Dict:
    reg = VENUE_REGISTRY.get(venue, {})
    start = dt.datetime.combine(day, start_time or dt.time(19, 0))
    start_iso = start.isoformat() + "-07:00"
    return {
        "id": f"lnsb-{day.isoformat()}-{_slug(venue)[:30]}-{_slug(title)[:40]}",
        "source": "LiveNotesSB",
        "url": SITE,
        "title": title,
        "venue_name": venue,
        "venueName": venue,  # camelCase for iOS
        "address": reg.get("address", ""),
        "city": reg.get("city", "Santa Barbara"),
        "zip": reg.get("zip", ""),
        "start": start_iso,
        "tags": ["music"],
    }

def lnsb_fetch(today: Optional[dt.date] = None):
    day = today or dt.date.today()
    html = _fetch_html(SITE)
    text = _visible_text(html)

    # save visible text for inspection
    (DEBUG_DIR / "visible.txt").write_text(text, encoding="utf-8")

    extracted: List[Tuple[str, str, str]] = []

    # Pass 1: regex triples across the entire page
    for m in TRIPLE_RE.finditer(text):
        venue = _clean(m.group("venue"))
        title = _clean(m.group("title"))
        time_text = _clean(m.group("time"))
        if venue and title and time_text:
            extracted.append((venue, title, time_text))

    # Pass 2: fallback to bullet-ish splitting if pass 1 is too thin
    if len(extracted) < 5:
        bullets = _split_bullets(text)
        for seg in bullets:
            got = _extract_from_segment(seg)
            if got:
                extracted.append(got)

    # Debug dump of (venue|title|time)
    with (DEBUG_DIR / "segments.txt").open("w", encoding="utf-8") as f:
        for v, t, tm in extracted:
            f.write(f"{v} | {t} | {tm}\n")

    events: List[Dict] = []
    seen = set()
    for venue, title, time_text in extracted:
        v = _clean(venue); t = _clean(title)
        if not v or not t:
            continue
        if t.lower() in BLACKLIST_TITLES:
            continue
        if v.upper() in REGION_HEADERS:
            continue

        start_time = _start_time_from_text(time_text) or dt.time(19, 0)
        ev = _build_event(day, v, t, start_time)
        key = (ev["start"], ev["venue_name"], ev["title"])
        if key in seen:
            continue
        seen.add(key)
        events.append(ev)

    # sort by start time
    def _k(e):
        try:
            return dt.datetime.fromisoformat(e["start"].replace("Z", "+00:00"))
        except Exception:
            return dt.datetime.max
    events.sort(key=_k)

    # human preview
    (DEBUG_DIR / "preview.txt").write_text(
        "\n".join(f"{e['start']} | {e.get('venue_name','?')} | {e['title']}" for e in events[:40]),
        encoding="utf-8",
    )

    return events
