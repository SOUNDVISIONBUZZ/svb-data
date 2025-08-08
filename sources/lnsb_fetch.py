# sources/lnsb_fetch.py
# LiveNotesSB scraper:
# - Scrapes the homepage (other paths 404)
# - Tries JSON-LD (schema.org Event) first
# - If none, renders the page with headless Selenium and tries again
# - Conservative HTML fallback to avoid nav/hero junk
# ASCII-only.

from __future__ import annotations

import os
import re
import json
import html
import time
import datetime as dt
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup

SITE = "https://livenotessb.com"

# ---------------- helpers ----------------

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
        return dt.datetime(y, mo, d, 19, 0)  # default 7pm
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
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (SVB/1.0)"})
        if r.status_code == 200 and r.text:
            return r.text
        print(f"Fetch {url} returned {r.status_code}")
    except Exception as e:
        print(f"Fetch failed for {url}: {e}")
    return None

# ---------------- JSON-LD ----------------

def _iter_jsonld(soup: BeautifulSoup):
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        txt = tag.string or tag.get_text()
        if not txt:
            continue
        try:
            yield json.loads(txt)
        except Exception:
            parts = re.split(r"}\s*{", txt.strip())
            if len(parts) > 1:
                fixed = []
                for i, p in enumerate(parts):
                    if i == 0:
                        fixed.append(p + "}")
                    elif i == len(parts) - 1:
                        fixed.append("{" + p)
                    else:
                        fixed.append("{" + p + "}")
                for f in fixed:
                    try:
                        yield json.loads(f)
                    except Exception:
                        pass

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

def _jsonld_events_from_html(html_text: str) -> List[Dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    out: List[Dict] = []
    for blob in _iter_jsonld(soup):
        for obj in _flatten_jsonld(blob):
            ev = _from_jsonld_obj(obj)
            if ev:
                out.append(ev)
    return out

# ---------------- HTML fallback (conservative) ----------------

MONTHS = "(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)"
DATE_RE = re.compile(rf"\b{MONTHS}\s+\d{{1,2}}(?:,\s*\d{{4}})?\b", re.I)
TIME_RE = re.compile(r"\b\d{1,2}(?::\d{2})?\s*(am|pm)\b", re.I)

def _html_fallback(html_text: str) -> List[Dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    scope = soup.select_one("main") or soup
    out: List[Dict] = []
    cards = scope.select("article, .tribe-events-calendar-list__event, .mec-event-article, .mec-event-list-item, li, section, div")
    def txt(el): return _clean(el.get_text(" ")) if el else ""
    for c in cards:
        t = txt(c)
        if not (DATE_RE.search(t) and TIME_RE.search(t)):
            continue
        t_el = c.select_one(".tribe-events-calendar-list__event-title a, .mec-event-title a, h3, h2, a")
        title = txt(t_el)
        bad = title.strip().lower() in {"skip to content", "home", "about", "contact", "menu", "search", "events", "calendar", "venues"}
        if not title or bad:
            continue
        date_m = DATE_RE.search(t)
        time_m = TIME_RE.search(t)
        if not date_m:
            continue
        dt_guess = None
        for fmt in ("%B %d, %Y", "%b %d, %Y"):
            try:
                dt_guess = dt.datetime.strptime(date_m.group(0), fmt); break
            except Exception:
                pass
        if not dt_guess:
            continue
        if time_m:
            hm = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", time_m.group(0), re.I)
            if hm:
                h = int(hm.group(1)); m = int(hm.group(2) or 0); ap = hm.group(3).lower()
                if ap == "pm" and h < 12: h += 12
                if ap == "am" and h == 12: h = 0
                dt_guess = dt_guess.replace(hour=h, minute=m)
        else:
            dt_guess = dt_guess.replace(hour=19, minute=0)
        venue = txt(c.select_one(".tribe-events-venue, .venue, .location, .mec-venue-name"))
        addr_text = txt(c.select_one(".tribe-events-address, .address, .mec-address")) or t
        zip_code = None
        mz = re.search(r"\b(\d{5})(?:-\d{4})?\b", addr_text)
        if mz: zip_code = mz.group(1)
        ev = _event_dict(dt_guess, title, venue or None, addr_text or None, "Santa Barbara", zip_code)
        if ev:
            out.append(ev)
    return out

# ---------------- Selenium render ----------------

def _render_with_selenium(url: str) -> Optional[str]:
    if os.getenv("SVB_USE_SELENIUM", "1") not in ("1", "true", "True"):
        return None
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.common.exceptions import WebDriverException

        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1200,1800")

        try:
            driver = webdriver.Chrome(options=opts)  # Selenium Manager
        except WebDriverException:
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=opts)

        driver.set_page_load_timeout(30)
        driver.get(url)
        time.sleep(4)  # allow JS to inject JSON-LD
        page = driver.page_source
        driver.quit()
        return page
    except Exception as e:
        print(f"Selenium fallback failed: {e}")
        return None

# ---------------- entry ----------------

def lnsb_fetch() -> List[Dict]:
    html_text = _fetch(SITE)
    if not html_text:
        return []

    events = _jsonld_events_from_html(html_text)

    if not events:
        rendered = _render_with_selenium(SITE)
        if rendered:
            events = _jsonld_events_from_html(rendered)
            if not events:
                events = _html_fallback(rendered)

    if not events:
        events = _html_fallback(html_text)

    seen = set()
    out: List[Dict] = []
    now = dt.datetime.now() - dt.timedelta(days=1)
    for ev in events:
        try:
            start_dt = dt.datetime.fromisoformat(ev["start"].replace("Z", "+00:00"))
            if start_dt < now:
                continue
        except Exception:
            pass
        if ev["id"] in seen:
            continue
        seen.add(ev["id"])
        out.append(ev)

    def _k(e):
        try:
            return dt.datetime.fromisoformat(e["start"].replace("Z","+00:00"))
        except Exception:
            return dt.datetime.max
    out.sort(key=_k)
    return out
