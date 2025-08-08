# sources/lnsb_fetch.py
# LiveNotesSB bullet-list scraper with debug outputs.
# Strategy:
# - Fetch homepage HTML
# - Extract visible text
# - Pull out "Venue | Title | time" triples from the big bullet text
# - Parse time (best-effort) and build ISO start timestamps for "today"
# - Write debug artifacts: tmp_lnsb/segments.txt and tmp_lnsb/preview.txt

import datetime as dt
import json
import os
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

# Region headers or junk tokens we should ignore as venues
REGION_HEADERS = {
    "CARPINTERIA",
    "SANTA BARBARA",
    "GOLETA/I.V",
    "GOLETA",
    "SANTA YNEZ/LOS OLIVOS",
    "SANTA YNEZ",
    "LOS OLIVOS",
    "SOLVANG",
}

BLACKLIST_TITLES = {
    "first thursday hosted by downtown sb",
    "august",
    "ios app",
    "android app",
}

# Minimal venue registry for addresses (expand later)
# If not found, we still emit the event without address.
VENUE_REGISTRY: Dict[str, Dict[str, str]] = {
    "Corktree Cellars": {"address": "910 Linden Ave", "city": "Carpinteria", "zip": "93013"},
    "Corks & Crowns": {"address": "32 Anacapa St", "city": "Santa Barbara", "zip": "93101"},
    "The Red Piano": {"address": "519 State St", "city": "Santa Barbara", "zip": "93101"},
    "Soho": {"address": "1221 State St", "city": "Santa Barbara", "zip": "93101"},
    "Anchor Rose": {"address": "113 Harbor Way", "city": "Santa Barbara", "zip": "93109"},
    "Villa Wine Bar & Kitchen": {"address": "618 Anacapa St", "city": "Santa Barbara", "zip": "93101"},
    "Satellite": {"address": "1117 State St", "city": "Santa Barbara", "zip": "93101"},
    "The Good Lion": {"address": "1212 State St", "city": "Santa Barbara", "zip": "93101"},
    "El Encanto, a Belmond Hotel": {"address": "800 Alvarado Pl", "city": "Santa Barbara", "zip": "93103"},
    "Validation Ale": {"address": "102 E Yanonali St", "city": "Santa Barbara", "zip": "93101"},
    "Institution Ale": {"address": "516 State St", "city": "Santa Barbara", "zip": "93101"},
    "The Leta Hotel": {"address": "5650 Calle Real", "city": "Goleta", "zip": "93117"},
    "Maverick Saloon": {"address": "3687 Sagunto St", "city": "Santa Ynez", "zip": "93460"},
    "Lost Chord Guitars": {"address": "1576 Copenhagen Dr", "city": "Solvang", "zip": "93463"},
    "Alisal River Grill/ Alisal Ranch": {"address": "150 Alisal Rd", "city": "Solvang", "zip": "93463"},
    "SloDoCo": {"address": "???", "city": "Goleta", "zip": ""},
    "ITH Santa Barbara Beach Hostel": {"address": "134 Chapala St", "city": "Santa Barbara", "zip": "93101"},
    "Reef & Run": {"address": "Cabrillo Blvd", "city": "Santa Barbara", "zip": "93101"},
    "Brothers Red Barn": {"address": "3539 Sagunto St", "city": "Santa Ynez", "zip": "93460"},
    "The V Lounge": {"address": "1455 Mission Dr", "city": "Solvang", "zip": "93463"},
    "800 Block of State Street": {"address": "800 State St", "city": "Santa Barbara", "zip": "93101"},
}

def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def _slug(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s

def _fetch_html(url: str) -> str:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
        r.raise_for_status()
        html = r.text
        name = url.strip("/").split("/")[-1] or "index"
        (DEBUG_DIR / f"{name}.html").write_text(html, encoding="utf-8")
        return html
    except Exception as ex:
        # Fallback to any cached copy if present
        name = url.strip("/").split("/")[-1] or "index"
        cache = DEBUG_DIR / f"{name}.html"
        if cache.exists():
            return cache.read_text(encoding="utf-8")
        raise

def _visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Drop script/style
    for t in soup(["script", "style", "noscript"]):
        t.extract()
    text = soup.get_text(separator="\n")
    # Normalize whitespace
    text = re.sub(r"\u00a0", " ", text)  # nbsp
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()

TIME_PATTERNS = [
    # 6-9 pm, 8 pm-12 am, 7-10 pm
    re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*-\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I),
    # single explicit time like "6 pm" or "6:30 pm"
    re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I),
    # compact "5-8 pm" -> start is 5 pm
    re.compile(r"\b(\d{1,2})\s*-\s*(\d{1,2})\s*(am|pm)\b", re.I),
]

def _parse_time_range(s: str) -> Optional[dt.time]:
    s = _clean(s)
    # Try "h(:mm)? - h(:mm)? am|pm"
    m = TIME_PATTERNS[0].search(s)
    if m:
        h = int(m.group(1))
        mm = int(m.group(2) or 0)
        ap = m.group(5).lower()
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        return dt.time(h, mm)
    # Try "h(:mm)? am|pm"
    m = TIME_PATTERNS[1].search(s)
    if m:
        h = int(m.group(1))
        mm = int(m.group(2) or 0)
        ap = m.group(3).lower()
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        return dt.time(h, mm)
    # Try "5-8 pm" -> start 5 pm
    m = TIME_PATTERNS[2].search(s)
    if m:
        h = int(m.group(1))
        ap = m.group(3).lower()
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        return dt.time(h, 0)
    return None

def _segment_bullets(big_text: str) -> List[str]:
    """
    LNSB uses long bullet-like runs separated by ' * ' and also by line breaks.
    Split aggressively, then trim.
    """
    # Replace " - " runs that are clearly separators with asterisk separator too
    txt = big_text.replace(" – ", " - ")  # normalize en-dash to hyphen
    # Split on " * " and newlines
    parts = []
    for chunk in re.split(r"\s\*\s|\n", txt):
        c = _clean(chunk)
        if c:
            parts.append(c)
    return parts

TRIPLE_RE = re.compile(
    r"(?P<venue>[^|]{2,}?)\s*\|\s*(?P<title>[^|]{2,}?)\s*\|\s*(?P<time>[^|]{1,30})",
    re.I,
)

def _segment_triples(chunks: List[str]) -> List[Tuple[str, str, str]]:
    triples: List[Tuple[str, str, str]] = []
    for c in chunks:
        m = TRIPLE_RE.search(c)
        if not m:
            continue
        v = _clean(m.group("venue"))
        t = _clean(m.group("title"))
        tm = _clean(m.group("time"))
        if not v or not t or not tm:
            continue
        triples.append((v, t, tm))
    return triples

def _is_region_header(s: str) -> bool:
    ss = _clean(s)
    return ss.upper() in REGION_HEADERS or ss.upper().startswith("AUGUST ")

def _make_id(day: dt.date, venue: str, title: str) -> str:
    return f"lnsb-{day.isoformat()}-{_slug(venue)[:30]}-{_slug(title)[:40]}"

def _build_event(
    day: dt.date,
    venue: str,
    title: str,
    start_time: Optional[dt.time],
) -> Dict:
    reg = VENUE_REGISTRY.get(venue, {})
    start = dt.datetime.combine(day, start_time or dt.time(19, 0))
    start_iso = start.isoformat() + "-07:00"
    ev = {
        "id": _make_id(day, venue, title),
        "source": "LiveNotesSB",
        "url": SITE,
        "title": title,
        "venue_name": venue,   # snake_case
        "venueName": venue,    # camelCase for iOS app
        "address": reg.get("address", ""),
        "city": reg.get("city", "Santa Barbara"),
        "zip": reg.get("zip", ""),
        "start": start_iso,
        "tags": ["music"],
    }
    return ev

def lnsb_fetch(today: Optional[dt.date] = None) -> List[Dict]:
    day = today or dt.date.today()

    # 1) Fetch HTML (homepage carries the full daily list)
    html = _fetch_html(SITE)
    text = _visible_text(html)

    # 2) Aggressive segmentation and triple extraction
    chunks = _segment_bullets(text)
    triples = _segment_triples(chunks)

    # Write debug: what we parsed out of the wall of text
    with (DEBUG_DIR / "segments.txt").open("w", encoding="utf-8") as f:
        for v, t, tm in triples:
            f.write(f"{v} | {t} | {tm}\n")

    # 3) Transform to structured events
    events: List[Dict] = []
    seen = set()

    for venue, title, time_text in triples:
        v = _clean(venue)
        t = _clean(title)

        if _is_region_header(v):
            continue
        if not v or not t:
            continue
        if t.lower() in BLACKLIST_TITLES:
            continue

        start_time = _parse_time_range(time_text) or dt.time(19, 0)
        ev = _build_event(day, v, t, start_time)
        key = (ev["start"], ev["venue_name"], ev["title"])
        if key in seen:
            continue
        seen.add(key)
        events.append(ev)

    # 4) Sort by start time ASC
    def _k(e: Dict) -> dt.datetime:
        try:
            return dt.datetime.fromisoformat(e["start"].replace("Z", "+00:00"))
        except Exception:
            return dt.datetime.max

    events.sort(key=_k)

    # 5) Quick preview debug for the first 30
    preview_lines = [
        f"{e['start']} | {e.get('venue_name','?')} | {e['title']}"
        for e in events[:30]
    ]
    (DEBUG_DIR / "preview.txt").write_text("\n".join(preview_lines), encoding="utf-8")

    return events
