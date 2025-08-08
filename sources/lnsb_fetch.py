# sources/lnsb_fetch.py
# LNSB homepage text segmenter (no Selenium). ASCII only.
# - Fetches https://livenotessb.com
# - Normalizes bullets/dashes
# - Splits into item-like segments
# - Extracts (venue, title/artist, time), date from context or defaults to today
# - Enriches address/zip/city from data/venues_sb.json
# - Future-only filter, de-dupe, sort

from __future__ import annotations

import re
import json
import html
import datetime as dt
from pathlib import Path
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://livenotessb.com"
VENUE_REG = ROOT / "data" / "venues_sb.json"
DEBUG_DIR = ROOT / "tmp_lnsb"
DEBUG_DIR.mkdir(exist_ok=True, parents=True)

MONTHS = "(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)"
DATE_RE = re.compile(rf"\b{MONTHS}\s+\d{{1,2}}(?:,\s*\d{{2,4}})?\b", re.I)
TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)

BLACKLIST = {"skip to content","home","about","contact","menu","search","events","calendar","venues"}

def _clean(s: Optional[str]) -> str:
    if not s: return ""
    s = html.unescape(s).replace("\xa0", " ")
    s = s.replace("–", "-").replace("—", "-").replace("•", "*")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _tz_offset(d: dt.datetime) -> str:
    return "-07:00" if 3 <= d.month <= 11 else "-08:00"

def _iso(d: dt.datetime) -> str:
    return d.replace(microsecond=0).isoformat() + _tz_offset(d)

def _parse_date(text: str, today: dt.date) -> Optional[dt.date]:
    text = _clean(text)
    # Full month name first, then short
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%B %d, %y", "%b %d, %y", "%B %d", "%b %d"):
        try:
            t = dt.datetime.strptime(text, fmt)
            if t.year == 1900:
                t = t.replace(year=today.year)
            return t.date()
        except Exception:
            pass
    m = DATE_RE.search(text)
    if m:
        return _parse_date(m.group(0), today)
    return None

def _parse_time(text: str) -> Optional[dt.time]:
    t = _clean(text).lower().replace(".", "")
    m = TIME_RE.search(t)
    if not m: return None
    h = int(m.group(1)); mm = int(m.group(2) or 0)
    ap = m.group(3)
    if ap == "pm" and h < 12: h += 12
    if ap == "am" and h == 12: h = 0
    if 0 <= h <= 23 and 0 <= mm <= 59:
        return dt.time(h, mm)
    return None

def _make_id(day: dt.date, venue: str, title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _clean(title).lower()).strip("-")
    vslug = re.sub(r"[^a-z0-9]+", "-", _clean(venue).lower()).strip("-")
    return f"lnsb-{day.isoformat()}-{vslug or 'venue'}-{slug or 'event'}"

def _fetch_html(url: str) -> Optional[str]:
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (SVB/1.0)"})
        if r.status_code == 200 and r.text:
            return r.text
        print(f"LNSB fetch status {r.status_code} for {url}")
    except Exception as e:
        print(f"LNSB fetch error {e}")
    return None

def _load_venue_registry() -> Dict[str, Dict[str, str]]:
    if VENUE_REG.exists():
        try:
            return json.loads(VENUE_REG.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def _pick_date_context(text: str, today: dt.date) -> dt.date:
    # If the page has a "First Thursday – August 7" style, grab the closest date; else assume today.
    d = _parse_date(text, today)
    return d or today

def _split_segments(raw: str) -> List[str]:
    # Split on bullets or star separators first, then newlines as fallback.
    raw = raw.replace(" * ", "\n* ").replace("* ", "\n* ")
    pieces = re.split(r"\n\*\s+|\s\*\s+|\n-\s+|\s•\s+|\n\u2022\s+", raw)
    out = []
    for p in pieces:
        p = _clean(p)
        if p and len(p) > 6:
            out.append(p)
    return out

def _extract_fields(seg: str, default_day: dt.date) -> Optional[Dict]:
    # Heuristic: "Venue - Title (genres) - 6-9 pm" OR "Venue - Artist - 7 pm"
    # 1) Venue: prefer leading proper-noun chunk before first " - "
    parts = [s.strip() for s in seg.split(" - ")]
    if len(parts) < 2:
        return None

    venue = parts[0]
    if not venue or venue.lower() in BLACKLIST:
        return None

    # 2) Find time anywhere in the segment
    time_obj = _parse_time(seg)
    if not time_obj:
        # allow default 7pm if a venue + some text exists
        time_obj = dt.time(19, 0)

    # 3) Title/artist: take the next non-time-ish chunk after venue
    title = ""
    for chunk in parts[1:]:
        if TIME_RE.search(chunk.lower()):
            continue
        title = chunk
        break
    if not title:
        # fallback: everything after venue
        title = " ".join(parts[1:])

    # Compose start
    start_iso = _iso(dt.datetime.combine(default_day, time_obj))
    return {
        "venue": venue,
        "title": _clean(title),
        "start": start_iso,
    }

def lnsb_fetch() -> List[Dict]:
    today = dt.date.today()
    html = _fetch_html(SITE)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("main") or soup
    text = main.get_text("\n", strip=True)

    # Save debug so we can iterate fast if needed
    (DEBUG_DIR / "raw.txt").write_text(text, encoding="utf-8")

    context_day = _pick_date_context(text, today)

    segments = _split_segments(text)
    reg = _load_venue_registry()

    events: List[Dict] = []
    seen = set()

    for seg in segments:
        fields = _extract_fields(seg, context_day)
        if not fields:
            continue

        venue = fields["venue"]
        title = fields["title"]
        start = fields["start"]

        eid = _make_id(context_day, venue, title)
        if eid in seen:
            continue

        ev = {
            "id": eid,
            "title": title,
            "category": "Music",
            "start": start,
            "city": "Santa Barbara"
        }

        # Enrich from registry
        if venue in reg:
            ev["venue_name"] = venue
            v = reg[venue]
            if v.get("address"): ev["address"] = v["address"]
            if v.get("zip"):     ev["zip"] = v["zip"]
            if v.get("city"):    ev["city"] = v["city"]
        else:
            ev["venue_name"] = venue

        # Future-ish only
        try:
            when = dt.datetime.fromisoformat(start.replace("Z","+00:00"))
            if when < dt.datetime.now() - dt.timedelta(days=1):
                continue
        except Exception:
            pass

        seen.add(eid)
        events.append(ev)

    # Sort by start
    def _k(e):
        try:
            return dt.datetime.fromisoformat(e["start"].replace("Z","+00:00"))
        except Exception:
            return dt.datetime.max
    events.sort(key=_k)

    # Save a quick debug preview
    preview = "\n".join(f"{e['start']} | {e.get('venue_name','?')} | {e['title']}" for e in events[:10])
    (DEBUG_DIR / "preview.txt").write_text(preview, encoding="utf-8")

    return events
