# sources/lnsb_fetch.py
# LiveNotesSB scraper using JSON-LD (schema.org) with safe fallbacks. ASCII only.

from __future__ import annotations

import re
import json
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

# ---------- helpers ----------

def _tz_offset(d: dt.datetime) -> str:
    # crude PDT/PST guess by month
    return "-07:00" if 3 <= d.month <= 11 else "-08:00"

def _clean(s: Optional[str]) -> str:
    if not s:
        return ""
    s = html.unescape(s).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()

def _slug(s: str) -> str:
    s = _clean(s).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "event"

def _parse_isoish(s: str) -> Optional[dt.datetime]:
    if not s:
        return None
    s = s.strip()
    try:
        # handle Z
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        pass
    # handle date-only "YYYY-MM-DD"
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        return dt.datetime(y, mo, d, 19, 0)  # default 7pm
    # handle "YYYY-MM-DDTHH:MM" missing offset
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})", s)
    if m:
        try:
            base = dt.datetime.fromisoformat(m.group(1))
            return base
        except Exception:
            return None
    return None

def _compose_start(dt_in: Optional[dt.datetime]) -> Optional[str]:
    if not dt_in:
        return None
    # if no tzinfo, append guessed offset
    if not (dt_in.tzinfo and dt_in.tzinfo.utcoffset(dt_in) is not None):
        return dt_in.replace(microsecond=0).isoformat() + _tz_offset(dt_in)
    return dt_in.replace(microsecond=0).isoformat()

def _event_dict(daytime: Optional[dt.datetime],
                title: str,
                venue: Optional[str],
                address: Optional[str],
                city: Optional[str],
                zip_code: Optional[str]) -> Optional[Dict]:
    title = _clean(title)
    if not title:
        return None
    start = _compose_start(daytime)
    if not start:
        return None
    vid = _slug(venue or "")
    eid = f"lnsb-{start[:10]}-{vid}-{_slug(title)}"
    ev = {
        "id": eid,
        "title": title,
        "category": "Music",
        "start": start,
        "city": _clean(city) or "Santa Barbara",
    }
    if venue:
        ev["venue_name"] = _clean(venue)
    if address:
        ev["address"] = _clean(address)
    if zip_code:
        ev["zip"] = _clean(zip_code)
    return ev

def _fetch(url: str) -> Optional[str]:
    try:
        r = requests.get(url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (compatible; SVB/1.0; +https://soundvision.buzz)"
        })
        if r.status_code == 200 and r.text:
            return r.text
        LOG.warning("Fetch %s returned %s", url, r.status_code)
    except Exception as e:
        LOG.warning("Fetch failed for %s: %s", url, e)
    return None

# ---------- JSON-LD extraction ----------

def _iter_jsonld(soup: BeautifulSoup):
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            txt = tag.string or tag.get_text()
            if not txt:
                continue
            data = json.loads(txt)
            yield data
        except Exception:
            # sometimes there are multiple JSONs glued together; ignore failures
            continue

def _flatten_jsonld(root):
    # yields dict objects inside root (dict, list, or graph) that look like objects
    stack = [root]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            yield cur
            if "@graph" in cur and isinstance(cur["@graph"], list):
                stack.extend(cur["@graph"])
            for v in cur.values():
                if isinstance(v, (list, dict)):
                    stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)

def _from_jsonld_obj(obj: dict) -> Optional[Dict]:
    # detect Event
    t = obj.get("@type")
    types = []
    if isinstance(t, list):
        types = t
    elif isinstance(t, str):
        types = [t]
    else:
        types = []

    if not any(isinstance(x, str) and x.lower() == "event" for x in types):
        return None

    title = obj.get("name") or obj.get("headline") or ""
    start_str = obj.get("startDate") or obj.get("startTime") or obj.get("date")
    start_dt = _parse_isoish(_clean(start_str))

    # location can be string or Place
    loc = obj.get("location")
    venue_name = None
    addr = None
    city = None
    zip_code = None

    if isinstance(loc, str):
        venue_name = loc
    elif isinstance(loc, dict):
        # Place
        venue_name = loc.get("name") or venue_name
        address = loc.get("address")
        if isinstance(address, dict):
            # PostalAddress
            parts = [
                address.get("streetAddress") or "",
                address.get("addressLocality") or "",
                address.get("addressRegion") or "",
                address.get("postalCode") or "",
            ]
            addr = _clean(" ".join([p for p in parts if p]))
            city = address.get("addressLocality") or city
            zip_code = address.get("postalCode") or zip_code
        elif isinstance(address, str):
            addr = address
    # sometimes address stored directly on obj
    if not addr and isinstance(obj.get("address"), (str, dict)):
        if isinstance(obj["address"], str):
            addr = obj["address"]
        elif isinstance(obj["address"], dict):
            parts = [
                obj["address"].get("streetAddress") or "",
                obj["address"].get("addressLocality") or "",
                obj["address"].get("addressRegion") or "",
                obj["address"].get("postalCode") or "",
            ]
            addr = _clean(" ".join([p for p in parts if p]))
            city = obj["address"].get("addressLocality") or city
            zip_code = obj["address"].get("postalCode") or zip_code

    return _event_dict(start_dt, title, venue_name, addr, city, zip_code)

def _jsonld_events(soup: BeautifulSoup) -> List[Dict]:
    events: List[Dict] = []
    for blob in _iter_jsonld(soup):
        for obj in _flatten_jsonld(blob):
            ev = _from_jsonld_obj(obj)
            if ev:
                events.append(ev)
    return events

# ---------- HTML fallback (minimal) ----------

MONTHS = "(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)"
DATE_RE = re.compile(rf"\b{MONTHS}\s+\d{{1,2}}(?:,\s*\d{{4}})?\b", re.I)
TIME_RE = re.compile(r"\b\d{1,2}(?::\d{2})?\s*(am|pm)\b", re.I)

def _html_fallback(soup: BeautifulSoup) -> List[Dict]:
    out: List[Dict] = []
    # event-like cards
    cards = soup.select(".tribe-events-calendar-list__event, .tec-event, .mec-event-article, .mec-event-list-item, article, li.event, div.event")
    def txt(el):
        return _clean(el.get_text(" ")) if el else ""
    for c in cards:
        text = txt(c)
        if not (DATE_RE.search(text) and TIME_RE.search(text)):
            continue
        title_el = c.select_one(".tribe-events-calendar-list__event-title a, .mec-event-title a, h3, h2, a")
        title = txt(title_el)
        if not title or title.strip().lower() in {"skip to content", "home", "about", "contact", "menu"}:
            continue
        # date
        day = None
        tstr = ""
        ttag = c.select_one("time[datetime]")
        if ttag and ttag.has_attr("datetime"):
            try:
                day = dt.datetime.fromisoformat(ttag["datetime"].replace("Z","+00:00"))
            except Exception:
                day = None
            tstr = txt(ttag)
        if not day:
            mdate = DATE_RE.search(text)
            if mdate:
                try:
                    # try full parse; if only date, default 19:00 below
                    day = dt.datetime.strptime(mdate.group(0), "%B %d, %Y")
                except Exception:
                    # rough parse via month abbrev
                    pass
        # time
        mtime = TIME_RE.search(text)
        if mtime and not tstr:
            tstr = mtime.group(0)
        # compose start
        start = _parse_isoish((day.isoformat() if isinstance(day, dt.datetime) else None) or "")
        start = start or _parse_isoish(mdate.group(0) if (mdate := DATE_RE.search(text)) else "")
        if not start:
            continue

        # venue/address guesses
        venue = txt(c.select_one(".tribe-events-venue, .venue, .location, .mec-venue-name"))
        addr_text = txt(c.select_one(".tribe-events-address, .address, .mec-address")) or text
        zip_code = (re.search(r"\b(\d{5})(?:-\d{4})?\b", addr_text) or re.search(r"\b(931\d{2})\b", addr_text) or [None]) if addr_text else [None]
        zip_val = zip_code.group(1) if hasattr(zip_code, "group") else None

        ev = _event_dict(start, title, venue or None, addr_text or None, "Santa Barbara", zip_val)
        if ev:
            out.append(ev)
    return out

# ---------- entry point ----------

def lnsb_fetch() -> List[Dict]:
    # Prioritize event pages; include homepage last just in case JSON-LD lives there
    urls = [
        urljoin(SITE, "/events"),
        urljoin(SITE, "/calendar"),
        urljoin(SITE, "/upcoming"),
        SITE,
    ]
    events: List[Dict] = []
    seen = set()

    for url in urls:
        html_text = _fetch(url)
        if not html_text:
            continue
        soup = BeautifulSoup(html_text, "html.parser")

        found = _jsonld_events(soup)
        if not found:
            found = _html_fallback(soup)

        for ev in found:
            # future events only (allow same-day)
            try:
                start_dt = dt.datetime.fromisoformat(ev["start"].replace("Z", "+00:00"))
                if start_dt < dt.datetime.now() - dt.timedelta(days=1):
                    continue
            except Exception:
                pass
            if ev["id"] in seen:
                continue
            seen.add(ev["id"])
            events.append(ev)

        if len(events) >= 40:
            break

    def _k(e):
        try:
            return dt.datetime.fromisoformat(e["start"].replace("Z","+00:00"))
        except Exception:
            return dt.datetime.max
    events.sort(key=_k)
    return events
