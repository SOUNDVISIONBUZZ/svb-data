# sources/lnsb_fetch.py
# LiveNotesSB scraper: resilient selectors + heuristic fallback, ASCII only.

from __future__ import annotations

import re
import html
import logging
import datetime as dt
from typing import List, Dict, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

LOG = logging.getLogger("lnsb")
LOG.setLevel(logging.INFO)

SITE = "https://livenotessb.com"

# --- time helpers ------------------------------------------------------------

def _tz_offset(d: dt.datetime) -> str:
    # crude PDT/PST guess by month: Mar–Nov PDT (-07:00), else PST (-08:00)
    return "-07:00" if 3 <= d.month <= 11 else "-08:00"

def _iso(d: dt.datetime) -> str:
    return d.replace(microsecond=0).isoformat() + _tz_offset(d)

def _clean_text(x: Optional[str]) -> str:
    if not x:
        return ""
    x = html.unescape(x)
    x = x.replace("\xa0", " ").strip()
    return re.sub(r"\s+", " ", x)

def _slug(s: str) -> str:
    s = _clean_text(s).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "event"

def _parse_date(text: str) -> Optional[dt.date]:
    text = _clean_text(text)
    fmts = ["%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d", "%a, %b %d, %Y"]
    for fmt in fmts:
        try:
            return dt.datetime.strptime(text, fmt).date()
        except Exception:
            pass
    m = re.search(r"([A-Za-z]{3,9})\s+(\d{1,2})(?:,\s*(\d{4}))?", text)
    if m:
        mon, day, year = m.group(1), m.group(2), m.group(3) or str(dt.date.today().year)
        for fmt in ("%B %d, %Y", "%b %d, %Y"):
            try:
                return dt.datetime.strptime(f"{mon} {day}, {year}", fmt).date()
            except Exception:
                pass
    return None

def _parse_time(text: str) -> Optional[dt.time]:
    t = _clean_text(text).lower().replace(".", "")
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", t)
    if not m:
        return None
    h = int(m.group(1))
    mm = int(m.group(2) or 0)
    ap = m.group(3)
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    if not ap and h == 24:
        h = 0
    if 0 <= h <= 23 and 0 <= mm <= 59:
        return dt.time(hour=h, minute=mm)
    return None

def _compose_start(day: Optional[dt.date], time_: Optional[dt.time]) -> Optional[str]:
    if not day:
        return None
    t = time_ or dt.time(19, 0)  # default 7:00 PM
    return _iso(dt.datetime.combine(day, t))

def _event_dict(day: Optional[dt.date],
                title: str,
                venue: Optional[str],
                address: Optional[str],
                city: str = "Santa Barbara",
                zip_code: Optional[str] = None,
                time_text: Optional[str] = None) -> Optional[Dict]:
    title = _clean_text(title)
    if not title or not day:
        return None
    start = _compose_start(day, _parse_time(time_text or ""))
    if not start:
        return None
    vid = _slug(venue or "")
    eid = f"lnsb-{day.isoformat()}-{vid}-{_slug(title)}"
    ev = {
        "id": eid,
        "title": title,
        "category": "Music",
        "start": start,
        "city": city,
    }
    if venue:
        ev["venue_name"] = _clean_text(venue)
    if address:
        ev["address"] = _clean_text(address)
    if zip_code:
        ev["zip"] = _clean_text(zip_code)
    return ev

def _extract_text(el) -> str:
    if not el:
        return ""
    if hasattr(el, "has_attr") and el.has_attr("datetime") and el.get("datetime"):
        return _clean_text(el.get("datetime"))
    return _clean_text(el.get_text(" "))

def _fetch_html(url: str) -> Optional[str]:
    try:
        r = requests.get(url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (compatible; SVB/1.0; +https://soundvision.buzz)"
        })
        if r.status_code == 200 and r.text:
            return r.text
    except Exception as e:
        LOG.warning("Fetch failed for %s: %s", url, e)
    return None

# --- structured strategies ---------------------------------------------------

def _try_events_calendar(soup: BeautifulSoup) -> List[Dict]:
    # The Events Calendar (Tribe)
    out: List[Dict] = []
    cards = soup.select(".tribe-events-calendar-list__event, .tec-event, .tribe-events-calendar-list__event-row")
    for c in cards:
        title = _extract_text(c.select_one(".tribe-events-calendar-list__event-title, .tribe-common-h3, .tribe-common-h2, h3, h2, a"))
        date_el = c.select_one("time[datetime], .tribe-events-c-small-cta__date, .tribe-events-calendar-list__event-date-tag, .tribe-events-date")
        date_text = _extract_text(date_el)
        day = None
        if date_el and date_el.has_attr("datetime"):
            try:
                day = dt.datetime.fromisoformat(date_el["datetime"][:10]).date()
            except Exception:
                pass
        if not day:
            day = _parse_date(date_text)

        time_text = _extract_text(c.select_one("time, .tribe-event-time, .tribe-events-calendar-list__event-time, .tribe-events-time"))

        venue = _extract_text(c.select_one(".tribe-events-venue, .tribe-events-calendar-list__event-venue, .tribe-venue, .venue, .location"))
        address = _extract_text(c.select_one(".tribe-events-address, .address, .tribe-address"))

        zip_code = ""
        mzip = re.search(r"\b(\d{5})(?:-\d{4})?\b", address)
        if mzip:
            zip_code = mzip.group(1)

        ev = _event_dict(day, title or "Live music", venue or None, address or None, "Santa Barbara", zip_code or None, time_text or "")
        if ev:
            out.append(ev)
    return out

def _try_modern_events_calendar(soup: BeautifulSoup) -> List[Dict]:
    # MEC (Modern Events Calendar)
    out: List[Dict] = []
    cards = soup.select(".mec-event-article, .mec-monthly-view-event, .mec-wrap .mec-event-list-item")
    for c in cards:
        title = _extract_text(c.select_one(".mec-event-title, h3, h2, a"))
        date_text = _extract_text(c.select_one(".mec-start-date, .mec-date, time[datetime]"))
        day = None
        el = c.select_one("time[datetime]")
        if el and el.has_attr("datetime"):
            try:
                day = dt.datetime.fromisoformat(el["datetime"][:10]).date()
            except Exception:
                pass
        if not day:
            day = _parse_date(date_text)

        time_text = _extract_text(c.select_one(".mec-time, .mec-event-time, time"))
        venue = _extract_text(c.select_one(".mec-venue-name, .venue, .location, .mec-address"))
        address = _extract_text(c.select_one(".mec-address, .address"))
        zip_code = ""
        mzip = re.search(r"\b(\d{5})(?:-\d{4})?\b", address)
        if mzip:
            zip_code = mzip.group(1)

        ev = _event_dict(day, title or "Live music", venue or None, address or None, "Santa Barbara", zip_code or None, time_text or "")
        if ev:
            out.append(ev)
    return out

# --- heuristic fallback ------------------------------------------------------

MONTHS = "(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)"
DATE_LINE = re.compile(rf"\b{MONTHS}\s+\d{{1,2}}(?:,\s*\d{{4}})?\b", re.I)
TIME_LINE = re.compile(r"\b(\d{1,2})(?::\d{2})?\s*(am|pm)\b", re.I)

def _try_heuristic(soup: BeautifulSoup) -> List[Dict]:
    out: List[Dict] = []
    # look for blocks that contain a date and a time
    for blk in soup.find_all(["article", "div", "li", "section"]):
        txt = _clean_text(blk.get_text(" "))
        if not (DATE_LINE.search(txt) and TIME_LINE.search(txt)):
            continue
        # crude guesses
        title = _clean_text((blk.find(["h3","h2","h1","a"]) or {}).get_text() if blk.find(["h3","h2","h1","a"]) else "")
        if not title:
            # fallback: first 8 words
            words = txt.split()
            title = " ".join(words[:8]) if words else "Live music"

        date_m = DATE_LINE.search(txt)
        day = _parse_date(date_m.group(0)) if date_m else None
        time_m = TIME_LINE.search(txt)
        time_text = time_m.group(0) if time_m else ""

        addr = ""
        for cand in re.findall(r"\b\d{2,5}\s+[A-Za-z0-9 .'-]+(?:St|Street|Ave|Avenue|Blvd|Boulevard|Rd|Road|Way|Place|Pl|Dr|Drive)\b.*?(?:\bCA\b|\bCalifornia\b|\b931\d{2}\b)?", txt):
            addr = cand
            break
        zip_code = ""
        mzip = re.search(r"\b(931\d{2})\b", txt)
        if mzip:
            zip_code = mzip.group(1)

        ev = _event_dict(day, title, None, addr or None, "Santa Barbara", zip_code or None, time_text)
        if ev:
            out.append(ev)
    return out

# --- entry point -------------------------------------------------------------

def lnsb_fetch() -> List[Dict]:
    urls = [
        SITE,
        urljoin(SITE, "/events"),
        urljoin(SITE, "/calendar"),
        urljoin(SITE, "/upcoming"),
    ]
    events: List[Dict] = []
    seen = set()

    for url in urls:
        html_text = _fetch_html(url)
        if not html_text:
            continue
        soup = BeautifulSoup(html_text, "html.parser")

        for strat in (_try_events_calendar, _try_modern_events_calendar, _try_heuristic):
            for ev in strat(soup):
                # keep future-ish events; do not drop if parsing fails
                try:
                    dt_start = dt.datetime.fromisoformat(ev["start"].replace("Z", "+00:00"))
                    if dt_start < dt.datetime.now() - dt.timedelta(days=1):
                        continue
                except Exception:
                    pass
                if ev["id"] in seen:
                    continue
                seen.add(ev["id"])
                events.append(ev)

        if len(events) >= 20:
            break

    # sort ascending by start
    def _k(e):
        try:
            return dt.datetime.fromisoformat(e["start"].replace("Z", "+00:00"))
        except Exception:
            return dt.datetime.max
    events.sort(key=_k)
    return events
