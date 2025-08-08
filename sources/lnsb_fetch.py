# sources/lnsb_fetch.py
# LiveNotesSB scraper that ONLY scrapes the homepage and uses JSON-LD first.
# Adds simple debug prints so you can see what's found.

from __future__ import annotations

import re
import json
import html
import datetime as dt
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup

SITE = "https://livenotessb.com"

def _tz_offset(d: dt.datetime) -> str:
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
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        pass
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        return dt.datetime(y, mo, d, 19, 0)
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})", s)
    if m:
        try:
            return dt.datetime.fromisoformat(m.group(1))
        except Exception:
            return None
    return None

def _compose_start(dt_in: Optional[dt.datetime]) -> Optional[str]:
    if not dt_in:
        return None
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
        print(f"Fetch {url} returned {r.status_code}")
    except Exception as e:
        print(f"Fetch failed for {url}: {e}")
    return None

def _iter_jsonld(soup: BeautifulSoup):
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        txt = tag.string or tag.get_text()
        if not txt:
            continue
        # Some sites jam multiple JSON objects together; try best-effort splits
        chunks = []
        try:
            chunks = [json.loads(txt)]
        except Exception:
            # naive split on }\s*{ boundaries
            parts = re.split(r"}\s*{", txt.strip())
            if len(parts) > 1:
                fixed = []
                for i, p in enumerate(parts):
                    if i == 0:
                        fixed.append(p + "}")
                    elif i == len(parts)-1:
                        fixed.append("{" + p)
                    else:
                        fixed.append("{" + p + "}")
                for f in fixed:
                    try:
                        chunks.append(json.loads(f))
                    except Exception:
                        pass
        for c in chunks:
            yield c

def _flatten_jsonld(root):
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
    t = obj.get("@type")
    types = t if isinstance(t, list) else [t] if isinstance(t, str) else []
    if not any(isinstance(x, str) and x.lower() == "event" for x in types):
        return None
    title = obj.get("name") or obj.get("headline") or ""
    start_str = obj.get("startDate") or obj.get("startTime") or obj.get("date")
    start_dt = _parse_isoish(_clean(start_str))

    venue_name = None
    addr = None
    city = None
    zip_code = None

    loc = obj.get("location")
    if isinstance(loc, str):
        venue_name = loc
    elif isinstance(loc, dict):
        venue_name = loc.get("name") or venue_name
        address = loc.get("address")
        if isinstance(address, dict):
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

    if not addr and isinstance(obj.get("address"), (str, dict)):
        if isinstance(obj["address"], str):
            addr = obj["address"]
        else:
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

def lnsb_fetch() -> List[Dict]:
    html = _fetch(SITE)
    if not html:
        print("LNSB: no HTML")
        return []
    soup = BeautifulSoup(html, "html.parser")

    # 1) JSON-LD first
    jsonld_events: List[Dict] = []
    blobs = list(_iter_jsonld(soup))
    print(f"LNSB: JSON-LD scripts found: {len(blobs)}")
    for blob in blobs:
        for obj in _flatten_jsonld(blob):
            ev = _from_jsonld_obj(obj)
            if ev:
                jsonld_events.append(ev)

    # de-dupe & future filter
    seen = set()
    out: List[Dict] = []
    for ev in jsonld_events:
        try:
            start_dt = dt.datetime.fromisoformat(ev["start"].replace("Z","+00:00"))
            if start_dt < dt.datetime.now() - dt.timedelta(days=1):
                continue
        except Exception:
            pass
        if ev["id"] in seen:
            continue
        seen.add(ev["id"])
        out.append(ev)

    print(f"LNSB: JSON-LD events parsed: {len(out)}")

    # 2) If none, minimal HTML fallback (very strict)
    if not out:
        text = soup.get_text(" ")
        # Look for obvious event lines like "Aug 10, 2025", etc.
        DATE_RE = re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)\s+\d{1,2}(?:,\s*\d{4})?\b")
        TIME_RE = re.compile(r"\b\d{1,2}(?::\d{2})?\s*(am|pm)\b", re.I)
        if DATE_RE.search(text) and TIME_RE.search(text):
            # This is deliberately conservative; without structure we won't guess titles.
            print("LNSB: found date/time hints in HTML but no JSON-LD; skipping to avoid junk.")
        else:
            print("LNSB: no recognizable events in HTML.")

    # Sort by start
    def _k(e):
        try:
            return dt.datetime.fromisoformat(e["start"].replace("Z","+00:00"))
        except Exception:
            return dt.datetime.max
    out.sort(key=_k)
    return out
