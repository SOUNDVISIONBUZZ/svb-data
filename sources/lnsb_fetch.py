cd ~/Documents/GitHub/svb-data
cat > sources/lnsb_fetch.py <<'PY'
# sources/lnsb_fetch.py
# LiveNotesSB scraper: parse homepage bullets only (no Selenium/JSON-LD).
# - Splits the big lineup into bullet segments that actually start with a bullet.
# - Extracts "Venue - Title - time" from each bullet.
# - Filters region headers / junk, enriches from data/venues_sb.json.
# - Writes tmp_lnsb/index.html, segments.txt, preview.txt for debugging.

from __future__ import annotations

import re, json, html, datetime as dt
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
REGION_HEADERS = {
    "CARPINTERIA","SANTA BARBARA","GOLETA/I.V","GOLETA / I.V",
    "SANTA YNEZ/LOS OLIVOS","SANTA YNEZ / LOS OLIVOS","SOLVANG"
}

def _clean(s: Optional[str]) -> str:
    if not s: return ""
    s = html.unescape(s).replace("\xa0"," ").replace("–","-").replace("—","-").replace("•","*")
    return re.sub(r"\s+"," ",s).strip()

def _fetch_html(url: str) -> Optional[str]:
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent":"Mozilla/5.0 (SVB/1.0)"})
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
    t = _clean(tstr).lower().replace(".","")
    m = re.search(
        r"\b(?P<h1>\d{1,2})(?::(?P<m1>\d{2}))?\s*(?P<ap1>am|pm)?\s*(?:-\s*(?P<h2>\d{1,2})(?::(?P<m2>\d{2}))?\s*(?P<ap2>am|pm)?)?",
        t, re.I
    )
    if not m: return None
    h1 = int(m.group("h1")); m1 = int(m.group("m1") or 0)
    ap1 = (m.group("ap1") or "").lower()
    ap2 = (m.group("ap2") or "").lower()
    if not ap1:
        ap1 = ap2 or ("pm" if 4 <= h1 <= 11 else "am")
    if ap1 == "pm" and h1 < 12: h1 += 12
    if ap1 == "am" and h1 == 12: h1 = 0
    if 0 <= h1 <= 23 and 0 <= m1 <= 59:
        return dt.time(h1, m1)
    return None

def _is_region_header(s: str) -> bool:
    ss = _clean(s).upper()
    return any(ss.startswith(h) for h in REGION_HEADERS)

def _segment_bullets(text: str) -> List[str]:
    # Insert line breaks before stars/bullets, then split.
    text = re.sub(r"\s\*\s+","\n* ", text)
    text = re.sub(r"\s•\s+","\n* ", text)
    parts = re.split(r"(?:^|\n)\*\s+", text)

    segs = []
    for p in parts[1:]:  # skip preamble before the first bullet
        p = _clean(p)
        if not p: continue
        if p.lower() in BLACKLIST_TITLES: continue
        if _is_region_header(p): continue
        # drop site tails and time-leading fragments
        if "iOS App Android App" in p:
            p = p.replace("iOS App Android App","").strip(" -")
        if re.match(r"^\d{1,2}(:\d{2})?\s*(am|pm)\b", p, re.I):
            continue
        segs.append(p)
    return segs

def _extract_from_segment(seg: str) -> Optional[Tuple[str,str,str]]:
    seg = _clean(seg)
    parts = [s.strip() for s in seg.split(" - ")]
    if len(parts) >= 3 and not _is_region_header(parts[0]):
        venue = parts[0]
        title = next((c for c in parts[1:] if not TIME_TOKEN_RE.search(c)), parts[1])
        time_text = next((c for c in reversed(parts) if TIME_TOKEN_RE.search(c)), "")
        if venue and title and time_text:
            return (venue, title, time_text)
    # fallback: find a time and split around it
    m = TIME_TOKEN_RE.search(seg)
    if m:
        before, after = seg[:m.start()].strip(" -"), seg[m.start():].strip()
        sub = before.split(" - ", 1)
        venue, title = (sub[0], sub[1]) if len(sub)==2 else (before, before)
        if not _is_region_header(venue) and venue and title:
            return (venue, title, after)
    return None

def _make_id(day: dt.date, venue: str, title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+","-", _clean(title).lower()).strip("-")
    vslug = re.sub(r"[^a-z0-9]+","-", _clean(venue).lower()).strip("-")
    return f"lnsb-{day.isoformat()}-{vslug or 'venue'}-{slug or 'event'}"

def lnsb_fetch() -> List[Dict]:
    today = dt.date.today()
    html = _fetch_html(SITE)
    if not html: return []
    (DEBUG_DIR/"index.html").write_text(html, encoding="utf-8")

    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("main") or soup
    text = _clean(main.get_text("\n", strip=True))
    context_day = _pick_date_context(text, today)

    bullet_segments = _segment_bullets(text)

    extracted: List[Tuple[str,str,str]] = []
    for seg in bullet_segments:
        got = _extract_from_segment(seg)
        if got:
            extracted.append(got)

    # Debug dump
    with (DEBUG_DIR/"segments.txt").open("w", encoding="utf-8") as f:
        for v, t, tm in extracted:
            f.write(f"{v} | {t} | {tm}\n")

    registry = _load_venue_registry()
    events: List[Dict] = []
    seen = set()

    for venue, title, time_text in extracted:
        venue = _clean(venue); title = _clean(title)
        if not venue or venue.lower() in BLACKLIST_TITLES or _is_region_header(venue): continue
        if not title: continue

        start_time = _parse_time_range(time_text) or dt.time(19, 0)
        start_iso = (
            dt.datetime.combine(context_day, start_time)
            .replace(microsecond=0)
            .isoformat()
        )
        # add static tz offset (Pacific)
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

        vinfo = registry.get(venue) or registry.get(venue.replace("’","'")) or {}
        if vinfo.get("address"): ev["address"] = vinfo["address"]
        if vinfo.get("zip"):     ev["zip"] = vinfo["zip"]
        if vinfo.get("city"):    ev["city"] = vinfo["city"]

        # future-only (allow same-day)
        try:
            when = dt.datetime.fromisoformat(start_iso.replace("Z","+00:00"))
            if when < dt.datetime.now() - dt.timedelta(days=1): continue
        except Exception:
            pass

        events.append(ev)

    # Sort
    def _k(e):
        try: return dt.datetime.fromisoformat(e["start"].replace("Z","+00:00"))
        except Exception: return dt.datetime.max
    events.sort(key=_k)

    # Preview
    (DEBUG_DIR/"preview.txt").write_text(
        "\n".join(f"{e['start']} | {e.get('venue_name','?')} | {e['title']}" for e in events[:30]),
        encoding="utf-8"
    )
    return events
PY
