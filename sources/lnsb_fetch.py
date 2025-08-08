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
    # non-greedy between dashes; time must exist
    for m in re.finditer(r"([A-Z0-9][^-]{1,80}?)\s-\s([^-\n]{1,160}?)\s-\s([^.\n]{4,40}?\b(?:am|pm)\b[^.\n]{0,20})", text, re.I):
        venue = _clean(m.group(1))
        title = _clean(m.group(2))
        ttxt  = _clean(m.group(3))
        if venue and title and TIME_TOKEN_RE.search(ttxt):
            triples.append((venue, title, ttxt))
    return triples

def _extract_from_segment(seg: str) -> Optional[Tuple[str, str, str]]:
    """
    Given a bullet segment like 'Anchor Rose - David Segall - 6-9 pm',
    return (venue, title, time_text).
    """
    # normalize " - " dashes
    seg = _clean(seg)
    # try explicit triple split first
    parts = [p.strip() for p in seg.split(" - ")]
    if len(parts) >= 3:
        venue = parts[0]
        # pick first non-time chunk as title after venue
        title = ""
        for chunk in parts[1:]:
            if TIME_TOKEN_RE.search(chunk):  # looks like time
                continue
            title = chunk
            break
        if not title and len(parts) >= 2:
            title = parts[1]
        # last piece that contains a time token becomes time_text
        time_text = ""
        for chunk in reversed(parts):
            if TIME_TOKEN_RE.search(chunk):
                time_text = chunk
                break
        if venue and title and time_text:
            return (venue, title, time_text)

    # fallback: scan for time and split around it
    tm = TIME_TOKEN_RE.search(seg)
    if tm:
        # take some text before as venue/title heuristically
        before = seg[:tm.start()].strip(" -")
        after  = seg[tm.start():].strip()
        # if "Venue - Title" pattern exists in before
        sub = before.split(" - ", 1)
        if len(sub) == 2:
            venue, title = sub[0].strip(), sub[1].strip()
        else:
            # best guess: first proper-noun-ish chunk is venue, rest title
            chunks = before.split(" ")
            if len(chunks) > 3:
                venue = " ".join(chunks[:3]); title = " ".join(chunks[3:])
            else:
                venue = before; title = before
        return (venue, title, after)

    return None

def _make_id(day: dt.date, venue: str, title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _clean(title).lower()).strip("-")
    vslug = re.sub(r"[^a-z0-9]+", "-", _clean(venue).lower()).strip("-")
    return f"lnsb-{day.isoformat()}-{vslug or 'venue'}-{slug or 'event'}"

def lnsb_fetch() -> List[Dict]:
    today = dt.date.today()

    html = _fetch_html(SITE)
    if not html: return []

    (DEBUG_DIR / "index.html").write_text(html, encoding="utf-8")

    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("main") or soup
    text = _clean(main.get_text("\n", strip=True))

    context_day = _pick_date_context(text, today)

    # Build candidate segments two ways, then unify:
    bullet_segments = _segment_bullets(text)              # items that start with bullets
    triple_segments = _segment_triples(text)              # (venue, title, time_text) found inline

    # Try to parse bullet segments into (venue, title, time_text)
    extracted = []
    for seg in bullet_segments:
        got = _extract_from_segment(seg)
        if got:
            extracted.append(got)

    # Add inline triples too
    extracted.extend(triple_segments)

    # Debug: write the segments we think are events
    with (DEBUG_DIR / "segments.txt").open("w", encoding="utf-8") as f:
        for v, t, tm in extracted:
            f.write(f"{v} | {t} | {tm}\n")

    # Load venue registry for address enrichment
    registry = _load_venue_registry()

    events: List[Dict] = []
    seen = set()

    for venue, title, time_text in extracted:
        venue = _clean(venue)
        title = _clean(title)
        if not venue or venue.lower() in BLACKLIST_TITLES: continue
        if not title: continue

        start_time = _parse_time_range(time_text) or dt.time(19, 0)
        start_iso = dt.datetime.combine(context_day, start_time).replace(microsecond=0).isoformat()
        # add static tz offset
        start_iso += ("-07:00" if 3 <= context_day.month <= 11 else "-08:00")

        eid = _make_id(context_day, venue, title)
        if eid in seen: continue
        seen.add(eid)

        ev = {
            "id": eid,
            "title": title,
            "category": "Music",
            "start": start_iso,
            "city": "Santa Barbara",
            "venue_name": venue
        }

        # enrich from registry when available
        vinfo = registry.get(venue) or registry.get(venue.replace("’","'")) or {}
        if vinfo.get("address"): ev["address"] = vinfo["address"]
        if vinfo.get("zip"):     ev["zip"] = vinfo["zip"]
        if vinfo.get("city"):    ev["city"] = vinfo["city"]

        # future-only filter (allow same-day)
        try:
            dt_start = dt.datetime.fromisoformat(start_iso.replace("Z","+00:00"))
            if dt_start < dt.datetime.now() - dt.timedelta(days=1):  # older than yesterday
                continue
        except Exception:
            pass

        events.append(ev)

    # Sort by start
    def _k(e):
        try:
            return dt.datetime.fromisoformat(e["start"].replace("Z","+00:00"))
        except Exception:
            return dt.datetime.max
    events.sort(key=_k)

    # Quick preview for sanity
    preview = "\n".join(f"{e['start']} | {e.get('venue_name','?')} | {e['title']}" for e in events[:20])
    (DEBUG_DIR / "preview.txt").write_text(preview, encoding="utf-8")

    return events

