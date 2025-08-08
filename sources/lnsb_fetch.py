# sources/lnsb_fetch.py
# LiveNotesSB bullet-list scraper (no Selenium) with debug outputs.
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

SITE = "https://livenotessb.com"
DEBUG_DIR = Path("tmp_lnsb")
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

UA = "Mozilla/5.0 (SVB/1.0; +https://soundvisionbuzz.com)"

# Very light registry for known venues -> address/city/zip (optional).
# You can expand this over time; unknown venues still work.
VENUE_REGISTRY: Dict[str, Dict[str, str]] = {
    # "Corktree Cellars": {"address": "910 Linden Ave, Carpinteria, CA", "city": "Carpinteria", "zip": "93013"},
}

BLACKLIST_TITLES = {
    "santa ynez/los olivos",
    "carpinteria",
    "santa barbara",
    "solvang",
    "goleta/i.v",
    "goleta/i.v.",
}

PT = dt.timezone(dt.timedelta(hours=-7))  # simple fixed offset; adequate for now


def _fetch_html(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    # Save the raw for inspection
    (DEBUG_DIR / "index.html").write_text(r.text, encoding="utf-8")
    return r.text


def _visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Strip scripts/styles
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text).strip()
    (DEBUG_DIR / "visible.txt").write_text(text[:100000], encoding="utf-8")
    return text


# Try to catch "Venue | Title | time" first (most reliable from your logs)
TRIPLE_BAR = re.compile(
    r"""
    (?P<venue>[A-Za-z0-9&'()./,\- ]{2,}?)\s*\|\s*
    (?P<title>[^|]{2,}?)\s*\|\s*
    (?P<time>
        \d{1,2}(:\d{2})?\s*(?:am|pm)\b
        |
        \d{1,2}\s*-\s*\d{1,2}\s*(?:am|pm)\b
        |
        \d{1,2}\s*-\s*\d{1,2}\s*pm\b
        |
        \d{1,2}\s*pm\b(?:\s*-\s*\d{1,2}\s*(?:am|pm)\b)?
        |
        \d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}\s*(?:am|pm)?
    )
    """,
    re.I | re.X,
)

# Fallback for "Venue – Title – time" or "Venue - Title - time"
TRIPLE_DASH = re.compile(
    r"""
    (?P<venue>[A-Za-z0-9&'()./,\- ]{2,}?)\s*[–-]\s*
    (?P<title>[^–\-]{2,}?)\s*[–-]\s*
    (?P<time>
        \d{1,2}(:\d{2})?\s*(?:am|pm)\b
        |
        \d{1,2}\s*-\s*\d{1,2}\s*(?:am|pm)\b
        |
        \d{1,2}\s*-\s*\d{1,2}\s*pm\b
        |
        \d{1,2}\s*pm\b(?:\s*-\s*\d{1,2}\s*(?:am|pm)\b)?
        |
        \d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}\s*(?:am|pm)?
    )
    """,
    re.I | re.X,
)


def _is_region_header(s: str) -> bool:
    s2 = re.sub(r"[^A-Za-z/\. ]+", "", s).strip().lower()
    return s2 in BLACKLIST_TITLES


def _parse_time_start(time_text: str) -> dt.time:
    """Return the *start* time as a dt.time; assume PM where ambiguous like '7-10 pm'."""
    s = time_text.strip().lower()
    # 7-10 pm -> 7 pm
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*-\s*\d{1,2}(?::\d{2})?\s*(am|pm)\b", s)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2) or 0)
        ap = m.group(3)
        if ap == "pm" and hh < 12:
            hh += 12
        if ap == "am" and hh == 12:
            hh = 0
        return dt.time(hh, mm)

    # 7 pm, 6:30 pm, 8pm-12am, etc -> take first time occurrence
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", s)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2) or 0)
        ap = m.group(3)
        if ap == "pm" and hh < 12:
            hh += 12
        if ap == "am" and hh == 12:
            hh = 0
        return dt.time(hh, mm)

    # fallback guess 7:00 pm
    return dt.time(19, 0)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" -*\u2013")  # strip spaces, hyphens, en-dash


def _load_venue_registry() -> Dict[str, Dict[str, str]]:
    # normalize keys for matching
    reg: Dict[str, Dict[str, str]] = {}
    for k, v in VENUE_REGISTRY.items():
        reg[k.lower()] = v
    return reg


def lnsb_fetch(today: Optional[dt.date] = None) -> List[Dict]:
    day = today or dt.date.today()

    html = _fetch_html(SITE)
    text = _visible_text(html)

    # Try triple matches over the full visible text (bar, then dash)
    segments: List[Tuple[str, str, str]] = []
    for rx in (TRIPLE_BAR, TRIPLE_DASH):
        for m in rx.finditer(text):
            venue = _clean(m.group("venue"))
            title = _clean(m.group("title"))
            time_text = _clean(m.group("time"))
            if not venue or not title:
                continue
            if _is_region_header(venue):
                continue
            segments.append((venue, title, time_text))

    # If nothing found, attempt splitting by " * " bullets and re-scan each (helps with awkward wraps)
    if not segments:
        parts = [p.strip() for p in re.split(r"\s+\*\s+", text) if p.strip()]
        for chunk in parts:
            m = TRIPLE_BAR.search(chunk) or TRIPLE_DASH.search(chunk)
            if not m:
                continue
            venue = _clean(m.group("venue"))
            title = _clean(m.group("title"))
            time_text = _clean(m.group("time"))
            if not venue or not title or _is_region_header(venue):
                continue
            segments.append((venue, title, time_text))

    # Debug dump of the raw segments we think are events
    with (DEBUG_DIR / "segments.txt").open("w", encoding="utf-8") as f:
        for v, t, tm in segments:
            f.write(f"{v} | {t} | {tm}\n")

    reg = _load_venue_registry()
    events: List[Dict] = []
    seen = set()

    for venue, title, time_text in segments:
        start_time = _parse_time_start(time_text)
        start_dt = dt.datetime.combine(day, start_time, tzinfo=PT)
        start_iso = start_dt.isoformat()

        reg_hit = reg.get(venue.lower(), {})
        ev = {
            "source": "LiveNotesSB",
            "title": title,
            "venue_name": venue,
            "address": reg_hit.get("address", ""),
            "city": reg_hit.get("city", "Santa Barbara"),
            "zip": reg_hit.get("zip", ""),
            "start": start_iso,
            "tags": ["music"],
        }

        key = (ev["start"], ev["venue_name"], ev["title"])
        if key in seen:
            continue
        seen.add(key)
        events.append(ev)

    # Sort oldest -> newest
    def _k(e: Dict) -> dt.datetime:
        try:
            return dt.datetime.fromisoformat(e["start"])
        except Exception:
            return dt.datetime.max

    events.sort(key=_k)

    # Quick preview file
    preview = "\n".join(f"{e['start']} | {e['venue_name']} | {e['title']}" for e in events[:30])
    (DEBUG_DIR / "preview.txt").write_text(preview, encoding="utf-8")

    return events
