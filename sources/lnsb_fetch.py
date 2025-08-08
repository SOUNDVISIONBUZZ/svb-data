"""
Scraper for LiveNotesSB front page.
No Selenium; suitable for GitHub Actions.
Enhanced with venue address lookup.
"""

from __future__ import annotations
import datetime as dt
import re
import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional

# Santa Barbara venue address mapping
VENUE_ADDRESSES = {
    # Santa Barbara venues
    "The Red Piano": "409 E Haley St, Santa Barbara, CA 93101",
    "Soho": "1221 State St, Santa Barbara, CA 93101",
    "SloDoCo": "1923 State St, Santa Barbara, CA 93101",
    "Maverick Saloon": "3687 Sagunto St, Santa Ynez, CA 93460",
    "Union": "121 E Canon Perdido St, Santa Barbara, CA 93101",
    "Union (formerly Wylde Works)": "121 E Canon Perdido St, Santa Barbara, CA 93101",
    
    # Add more common venues
    "Lobero Theatre": "33 E Canon Perdido St, Santa Barbara, CA 93101",
    "Granada Theater": "1214 State St, Santa Barbara, CA 93101", 
    "Santa Barbara Bowl": "1122 N Milpas St, Santa Barbara, CA 93103",
    "Miss Daisy's": "324 State St, Santa Barbara, CA 93101",
    "Corks & Crowns": "3200 State St, Santa Barbara, CA 93105",
    "Pali Wine Garden": "1279 Coast Village Rd, Santa Barbara, CA 93108",
    "Anchor Rose": "15 E Ortega St, Santa Barbara, CA 93101",
    "Night Lizard Brewing": "2108 De la Vina St, Santa Barbara, CA 93105",
    "Brewhouse": "229 W Montecito St, Santa Barbara, CA 93101",
    "M Special Brewing": "3810 Carpinteria Ave, Carpinteria, CA 93013",
    "Carrillo Ballroom": "100 E Carrillo St, Santa Barbara, CA 93101",
    "Whiskey Richards": "3522 State St, Santa Barbara, CA 93105",
    "Casa de la Guerra": "15 E De La Guerra St, Santa Barbara, CA 93101",
    "EOS Lounge": "500 Anacapa St, Santa Barbara, CA 93101",
    "Dargan's Irish Pub": "18 E Ortega St, Santa Barbara, CA 93101",
    "Villa Wine Bar": "618 Anacapa St, Santa Barbara, CA 93101",
    "Bobcat Room": "11 W Ortega St, Santa Barbara, CA 93101",
    "Wildcat Lounge": "15 W Ortega St, Santa Barbara, CA 93101",
    
    # Goleta/IV venues
    "Draughtsmen Aleworks": "3455 Via Mercado, Santa Barbara, CA 93105",
    "Samsara Wine Co.": "7140 Hollister Ave, Goleta, CA 93117",
    
    # Carpinteria
    "Corktree Cellars": "1000 Via Rodeo, Carpinteria, CA 93013",
    
    # Santa Ynez Valley
    "Firestone Vineyard": "5000 Zaca Station Rd, Los Olivos, CA 93441",
    "Gainey Vineyard": "3950 E Hwy 246, Santa Ynez, CA 93460",
    "Carhartt Vineyard": "2990 Grand Ave, Los Olivos, CA 93441",
    
    # Solvang
    "Lost Chord Guitars": "1664 Copenhagen Dr, Solvang, CA 93463",
    "Solvang Theaterfest": "420 2nd St, Solvang, CA 93463",
    
    # Buellton
    "Vega Vineyard & Farm": "9496 Santa Rosa Rd, Buellton, CA 93427",
    "Brick Barn Wine Estate": "795 Industrial Way, Buellton, CA 93427",
    
    # Santa Maria
    "El Viñero": "4444 Santa Maria Way, Santa Maria, CA 93455",
    "Riverbench Vineyard": "6020 Foxen Canyon Rd, Santa Maria, CA 93454",
    "805 Charcuterie": "1200 E Main St, Santa Maria, CA 93454",
    "Costa de Oro Winery": "1331 S Nicholson Ave, Santa Maria, CA 93454",
    
    # Mountain venues
    "Cold Spring Tavern": "5995 Stagecoach Rd, Santa Barbara, CA 93105",
    "Hook'd Bar and Grill": "9600 CA-154, Santa Barbara, CA 93105",
}

def get_zip_from_address(address: str) -> str:
    """Extract zip code from address."""
    if not address:
        return "93101"  # Default Santa Barbara zip
    zip_match = re.search(r'CA (\d{5})', address)
    return zip_match.group(1) if zip_match else "93101"

def get_city_from_address(address: str) -> str:
    """Extract city from address."""
    if not address:
        return "Santa Barbara"
    # Match pattern like ", City, CA"
    city_match = re.search(r', ([^,]+), CA', address)
    return city_match.group(1) if city_match else "Santa Barbara"

def get_venue_address(venue_name: str) -> str:
    """Get venue address, with fallback logic."""
    # Direct match
    if venue_name in VENUE_ADDRESSES:
        return VENUE_ADDRESSES[venue_name]
    
    # Try partial matches for variations
    for known_venue, address in VENUE_ADDRESSES.items():
        if venue_name.lower() in known_venue.lower() or known_venue.lower() in venue_name.lower():
            return address
    
    # Default fallback based on common patterns
    if "santa ynez" in venue_name.lower() or "maverick" in venue_name.lower():
        return "Santa Ynez, CA 93460"
    elif "solvang" in venue_name.lower():
        return "Solvang, CA 93463"
    elif "goleta" in venue_name.lower():
        return "Goleta, CA 93117"
    elif "carpinteria" in venue_name.lower():
        return "Carpinteria, CA 93013"
    else:
        return "Santa Barbara, CA 93101"  # Default to Santa Barbara

def parse_event_time(date_str: str, time_str: str) -> tuple[str, str]:
    """Parse date and time strings into ISO format."""
    try:
        # Get current date as base
        today = dt.datetime.now()
        
        # Default to today if we can't parse the date
        event_date = today
        
        # Try to extract day from date_str
        if "MONDAY" in date_str.upper():
            # Find next Monday
            days_ahead = (0 - today.weekday()) % 7
            if days_ahead == 0:  # If today is Monday, get next Monday
                days_ahead = 7
            event_date = today + dt.timedelta(days=days_ahead)
        elif "TUESDAY" in date_str.upper():
            days_ahead = (1 - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            event_date = today + dt.timedelta(days=days_ahead)
        # Add more days as needed...
        
        # Parse time (e.g., "5-8 pm", "7:30 pm", "1-4 pm")
        time_str_clean = time_str.lower().strip()
        
        # Look for time patterns
        time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(?:-\s*(\d{1,2})(?::(\d{2}))?)?\s*(am|pm)', time_str_clean)
        
        if time_match:
            start_hour = int(time_match.group(1))
            start_min = int(time_match.group(2)) if time_match.group(2) else 0
            period = time_match.group(5)
            
            # Convert to 24-hour format
            if period == 'pm' and start_hour != 12:
                start_hour += 12
            elif period == 'am' and start_hour == 12:
                start_hour = 0
                
            start_time = event_date.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)
            
            # Handle end time if present
            if time_match.group(3):
                end_hour = int(time_match.group(3))
                end_min = int(time_match.group(4)) if time_match.group(4) else 0
                
                if period == 'pm' and end_hour != 12:
                    end_hour += 12
                elif period == 'am' and end_hour == 12:
                    end_hour = 0
                    
                end_time = event_date.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)
            else:
                # Default to 2 hours if no end time
                end_time = start_time + dt.timedelta(hours=2)
                
        else:
            # Default times if parsing fails
            start_time = event_date.replace(hour=19, minute=0, second=0, microsecond=0)  # 7 PM
            end_time = event_date.replace(hour=21, minute=0, second=0, microsecond=0)    # 9 PM
            
        # Make sure end time is after start time
        if end_time <= start_time:
            end_time = start_time + dt.timedelta(hours=2)
            
        # Format as ISO strings with timezone
        tz_offset = "-07:00"  # Pacific Time
        start_iso = start_time.strftime(f"%Y-%m-%dT%H:%M:%S{tz_offset}")
        end_iso = end_time.strftime(f"%Y-%m-%dT%H:%M:%S{tz_offset}")
        
        return start_iso, end_iso
        
    except Exception as e:
        print(f"Time parsing error: {e}")
        # Fallback to default times
        default_date = dt.datetime.now() + dt.timedelta(days=1)
        start = default_date.replace(hour=19, minute=0, second=0, microsecond=0)
        end = default_date.replace(hour=21, minute=0, second=0, microsecond=0)
        tz_offset = "-07:00"
        return (
            start.strftime(f"%Y-%m-%dT%H:%M:%S{tz_offset}"),
            end.strftime(f"%Y-%m-%dT%H:%M:%S{tz_offset}")
        )

def categorize_event(artist_info: str, venue: str) -> tuple[str, str]:
    """Categorize event based on artist info and venue."""
    info_lower = (artist_info + " " + venue).lower()
    
    # Genre mapping
    if any(word in info_lower for word in ['classical', 'opera', 'symphony', 'chamber']):
        return "Music", "Classical"
    elif any(word in info_lower for word in ['jazz', 'blues']):
        return "Music", "Jazz"
    elif any(word in info_lower for word in ['country', 'americana', 'bluegrass']):
        return "Music", "Country"
    elif any(word in info_lower for word in ['rock', 'indie', 'alternative']):
        return "Music", "Rock"
    elif any(word in info_lower for word in ['folk', 'singer/songwriter', 'acoustic']):
        return "Music", "Folk"
    elif any(word in info_lower for word in ['open mic']):
        return "Music", "Open Mic"
    elif 'winery' in info_lower or 'vineyard' in info_lower:
        return "Music & Wine", "Folk"
    else:
        return "Music", "Contemporary"

def lnsb_fetch() -> List[Dict]:
    """Fetch events from LiveNotesSB with improved parsing."""
    print("• LiveNotesSB fetch")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get("https://livenotessb.com/", headers=headers, timeout=15)
        response.raise_for_status()
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        events = []
        event_count = 0
        
        # Get all text and split into lines for parsing
        full_text = soup.get_text()
        lines = [line.strip() for line in full_text.split('\n') if line.strip()]
        
        # Look for venue/event patterns
        for i, line in enumerate(lines):
            try:
                # Skip very short lines
                if len(line) < 10:
                    continue
                
                # Look for venue indicators (lines with colons that might be venue: event format)
                if ':' in line and not line.startswith('http'):
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        potential_venue = parts[0].strip()
                        potential_event = parts[1].strip()
                        
                        # Skip obviously non-venue lines
                        if any(skip in potential_venue.lower() for skip in ['http', 'www', '.com', 'tel:', 'email']):
                            continue
                            
                        # Skip very long venue names (probably not venues)
                        if len(potential_venue) > 50:
                            continue
                            
                        # Skip lines that look like times or descriptions
                        if re.match(r'^\d', potential_venue) or 'pm' in potential_venue.lower() or 'am' in potential_venue.lower():
                            continue
                            
                        # This looks like a venue: event format
                        venue_name = potential_venue
                        event_info = potential_event
                        
                        # Get address for this venue
                        address = get_venue_address(venue_name)
                        city = get_city_from_address(address)
                        zip_code = get_zip_from_address(address)
                        
                        # Parse event info for artist and time
                        time_info = ""
                        artist_info = event_info
                        
                        # Look for time patterns in the event info
                        time_match = re.search(r'(\d{1,2}(?::\d{2})?\s*(?:am|pm)(?:\s*-\s*\d{1,2}(?::\d{2})?\s*(?:am|pm))?)', event_info, re.IGNORECASE)
                        if time_match:
                            time_info = time_match.group(1)
                            artist_info = event_info.replace(time_info, '').strip()
                        
                        # Clean up artist info
                        artist_info = re.sub(r'\s*\([^)]+\)\s*', ' ', artist_info)  # Remove parentheses
                        artist_info = re.sub(r'\s+', ' ', artist_info).strip()  # Clean whitespace
                        
                        if not artist_info:
                            artist_info = f"Live Music at {venue_name}"
                        
                        # Generate times
                        if not time_info:
                            time_info = "7:30 pm"  # Default time
                            
                        start_time, end_time = parse_event_time("", time_info)
                        
                        # Categorize
                        category, genre = categorize_event(event_info, venue_name)
                        
                        # Create event
                        event = {
                            "id": f"lnsb-{dt.datetime.now().strftime('%Y%m%d')}-{venue_name.lower().replace(' ', '-').replace('(', '').replace(')', '')[:30]}",
                            "title": f"{venue_name}: {artist_info}",
                            "category": category,
                            "genre": genre,
                            "city": city,
                            "zip": zip_code,
                            "start": start_time,
                            "end": end_time,
                            "venue": venue_name,
                            "address": address,
                            "popularity": 75
                        }
                        
                        events.append(event)
                        event_count += 1
                        
                        # Limit events to prevent overload
                        if event_count >= 20:
                            break
                            
            except Exception as e:
                # Continue parsing even if one event fails
                continue
        
        print(f"  ↳ {len(events)} LiveNotesSB events")
        return events
        
    except Exception as e:
        print(f"  ↳ LiveNotesSB error: {e}")
        return []

# For direct testing
if __name__ == "__main__":
    events = lnsb_fetch()
    for event in events:
        print(f"- {event['title']}")
        print(f"  Venue: {event['venue']}")
        print(f"  Address: {event['address']}")
        print(f"  Time: {event['start']}")
        print()
