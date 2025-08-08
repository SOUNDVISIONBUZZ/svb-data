# sources/lnsb_fetch.py
# LiveNotesSB scraper that segments the homepage text into individual events.
# - No Selenium, no JSON-LD. Pure text parsing.
# - Normalizes en/em-dashes to "-" and bullets to "*".
# - Splits the lineup into segments (bullet items and "Venue - Title - time" triples).
# - Parses start time (supports "6-9 pm", "8 pm-12 am", "7:30 pm", etc.).
# - Enriches with data/venues_sb.json when available (address, zip, city).
# - Future-only, de-dupe, sorted.

from __future__ import annotations

import re
import json
import html
import datetime as dt
from typing import List, Dict, Optional, Tuple
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://livenotessb.com"
VENUE_REG = ROOT / "data" / "venues_sb.json"
DEBUG_DIR = ROOT / "tmp_lnsb"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

MONTHS = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)"
DATE_RE = re.compile(rf"\b{MONTHS}\s+\d{{1,2}}(?:,\s*\d{{2,4}})?\b", re.I)
TIME_TOKEN_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)

BLACKLIST_TITLES = {"skip to content","home","about","contact","menu","search","events","calendar","venues"}

def _clean(s: Optional[str]) -> str:
    if not s: return ""
    s = html.unescape(s)
    s = s.replace("\xa0", " ").replace("–", "-").replace("—", "-").replace("•", "*")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _fetch_html(url: str) -> Optional[str]:
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (SVB/1.0)"})
        if r.status_code == 200 and r.text:
            return r.text
        print(f"LNSB fetch {r.status_code} {url}")
    except Exception as e:
        print(f"LNSB fetch error: {e}")
    return None

def _load_venue_registry() -> Dict[str, Dict[str, str]]:
    try:
        if VENUE_REG.exists():
            return json.loads(VENUE_REG.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def _pick_date_context(text: str, today: dt.date) -> dt.date:
    # take first date we see on page; else today
    m = DATE_RE.search(text)
    if m:
        for fmt in ("%B %d, %Y","%b %d, %Y","%B %d, %y","%b %d, %y","%B %d","%b %d"):
            try:
                d = dt.datetime.strptime(m.group(0), fmt)
                if d.year == 1900: d = d.replace(year=today.year)
                return d.date()
            except Exception:
                pass
    return today

def _parse_time_range(tstr: str) -> Optional[dt.time]:
    """
    Accepts:
      "6-9 pm"  -> 18:00
      "7 pm-12 am" -> 19:00
      "7:30 pm" -> 19:30
      "6 pm" -> 18:00
    """
    t = _clean(tstr).lower().replace(".", "")
    m = re.search(
        r"\b(?P<h1>\d{1,2})(?::(?P<m1>\d{2}))?\s*(?P<ap1>am|pm)?\s*(?:-\s*(?P<h2>\d{1,2})(?::(?P<m2>\d{2}))?\s*(?P<ap2>am|pm)?)?",
        t, re.I
    )
    if not m: return None
    h1 = int(m.group("h1")); m1 = int(m.group("m1") or 0)
    ap1 = m.group("ap1")
    ap2 = m.group("ap2")

    # infer am/pm for start if missing
    if not ap1:
        if ap2: ap1 = ap2  # "6-9 pm" => assume pm
        else:
            # evening default; most LNSB shows are pm
            ap1 = "pm" if 4 <= h1 <= 11 else "am"

    if ap1.lower() == "pm" and h1 < 12: h1 += 12
    if ap1.lower() == "am" and h1 == 12: h1 = 0

    if 0 <= h1 <= 23 and 0 <= m1 <= 59:
        return dt.time(h1, m1)
    return None

def _segment_bullets(text: str) -> List[str]:
    """
    Split on bullet/star separators into candidate segments.
    """
    # force line breaks before bullets/stars
    text = re.sub(r"\s\*\s+", "\n* ", text)
    text = re.sub(r"\s•\s+", "\n* ", text)
    parts = re.split(r"(?:^|\n)\*\s+", text)
    segs = []
    for p in parts:
        p = _clean(p)
        if not p: continue
        # ignore global headers etc.
        if p.lower() in BLACKLIST_TITLES: continue
        segs.append(p)
    return segs

def _segment_triples(text: str) -> List[Tuple[str, str, str]]:
    """
    Find inline 'Venue - Title - time' triples anywhere in the text.
    Returns list of (venue, title, time_text).
    """
    triples = []
    # non-greedy between dashes; time mu
