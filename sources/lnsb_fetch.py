"""
Enhanced scraper for LiveNotesSB with proper venue address mapping.
Extracts events from the front page and matches them with venue addresses.
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
    "Lobero Theatre": "33 E Canon Perdido St, Santa Barbara, CA 93101",
    "Granada Theater": "1214 State St, Santa Barbara, CA 93101", 
    "Santa Barbara Bowl": "1122 N Milpas St, Santa Barbara, CA 93103",
    "The Red Piano": "409 E Haley St, Santa Barbara, CA 93101",
    "Soho": "1221 State St, Santa Barbara, CA 93101",
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
    "Maverick Saloon": "3687 Sagunto St, Santa Ynez, CA 93460",
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
    zip_match = re.search(r'CA (\d{5})', address)
    return zip_match.group(1) if zip_match else "93101"

def get_city_from_address(address: str) -> str:
    """Extract city from address."""
    # Match pattern like ", City, CA"
    city_match = re.search(r', ([^,]+), CA', address)
    return city_match.group(1) if city_match else "Santa Barbara"

def parse_event_time(date_str: str, time_str: str) -> tuple[str, str]:
    """Parse date and time strings into ISO format."""
    try:
        # Handle various date formats
        if "July 20" in date_str:
            date = dt.datetime(2025, 7, 20)
        elif "July 21" in date_str:
            date = dt.datetime(2025, 7, 21)
        else:
            # Default to current date if parsing fails
            date = dt.datetime.now()
            
        # Parse time (e.g., "5-8 pm", "7:30 pm", "1-4 pm")
        time_match = re.search(r'(\d{1,2}):?(\d{0,2})\s*(?:-\s*(\d{1,2}):?(\d{0,2}))?\s*(am|pm)', time_str.lower())
        
        if time_match:
            start_hour = int(time_match.group(1))
            start_min = int(time_match.group(2)) if time_match.group(2) else 0
            period = time_match.group(5)
            
            # Convert to 24-hour format
            if period == 'pm' and start_hour != 12:
                start_hour += 12
            elif period == 'am' and start_hour == 12:
                start_hour = 0
                
            start_time = date.replace(hour=start_hour, minute=start_min)
            
            # Handle end time if present
            if time_match.group(3):
                end_hour = int(time_match.group(3))
                end_min = int(time_match.group(4)) if time_match.group(4) else 0
                
                if period == 'pm' and end_hour != 12:
                    end_hour += 12
                elif period == 'am' and end_hour == 12:
                    end_hour = 0
                    
                end_time = date.replace(hour=end_hour, minute=end_min)
            else:
                # Default to 2 hours if no end time
                end_time = start_time + dt.timedelta(hours=2)
                
        else:
            # Default times if parsing fails
            start_time = date.replace(hour=19, minute=0)  # 7 PM
            end_time = date.replace(hour=21, minute=0)    # 9 PM
            
        # Format as ISO strings with timezone
        tz_offset = "-07:00"  # Pacific Time
        start_iso = start_time.strftime(f"%Y-%m-%dT%H:%M:%S{tz_offset}")
        end_iso = end_time.strftime(f"%Y-%m-%dT%H:%M:%S{tz_offset}")
        
        return start_iso, end_iso
        
    except Exception:
        # Fallback to default times
        default_date = dt.datetime.now()
        start = default_date.replace(hour=19, minute=0)
        end = default_date.replace(hour=21, minute=0)
        tz_offset = "-07:00"
        return (
            start.strftime(f"%Y-%m-%dT%H:%M:%S{tz_offset}"),
            end.strftime(f"%Y-%m-%dT%H:%M:%S{tz_offset}")
        )

def categorize_event(artist_info: str, venue: str) -> tuple[str, str]:
    """Categorize event based on artist info and venue."""
    info_lower = artist_info.lower()
    venue_lower = venue.lower()
    
    # Genre mapping
    if any(word in info_lower for word in ['classical', 'opera', 'symphony', 'chamber']):
        return "Music", "Classical"
    elif any(word in info_lower for word in ['jazz', 'blues']):
        return "Music", "Jazz"
    elif any(word in info_lower for word in ['country', 'americana', 'bluegrass']):
        return "Music", "Country"
    elif any(word in info_lower for word in ['rock', 'indie', 'alternative']):
        return "Music", "Rock"
    elif any(word in info_lower for word in ['folk', 'singer/songwriter']):
        return "Music", "Folk"
    elif 'winery' in venue_lower or 'vineyard' in venue_lower:
        return "Music & Wine", "Folk"
    else:
        return "Music", "Contemporary"

def lnsb_fetch() -> List[Dict]:
    """Fetch events from LiveNotesSB."""
    try:
        response = requests.get("https://livenotessb.com/", timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        events = []
        event_id = 1
        
        # Find all venue and artist entries
        # Look for venue links (marked with *)
        content = soup.get_text()
        lines = content.split('\n')
        
        current_date = None
        current_city = None
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
                
            # Check for date headers
            date_match = re.search(r'(SUNDAY|MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY)\s+–\s+(.+)', line)
            if date_match:
                current_date = line
                continue
                
            # Check for city headers
            if line.startswith('– ') and line.endswith(' –'):
                current_city = line.strip('– ')
                continue
                
            # Check for venue entries (start with *)
            if line.startswith('*') and current_date and current_city:
                # Extract venue name
                venue_match = re.search(r'\*\[?\s*([^\]]+?)\s*\]?(?:\(|$)', line)
                if not venue_match:
                    continue
                    
                venue_name = venue_match.group(1).strip()
                
                # Look for artist/event info in next few lines
                artist_line = ""
                time_info = ""
                
                for j in range(i + 1, min(i + 4, len(lines))):
                    if j < len(lines) and lines[j].strip():
                        next_line = lines[j].strip()
                        if next_line.startswith('–') and not next_line.endswith('–'):
                            # This looks like an artist line
                            artist_match = re.search(r'–\s*\[?([^\]]+?)\]?\s*(?:\([^)]+\))?\s*–?\s*(.+)', next_line)
                            if artist_match:
                                artist_line = artist_match.group(1).strip()
                                time_info = artist_match.group(2).strip()
                                break
                
                if not artist_line:
                    continue
                    
                # Get venue address
                address = VENUE_ADDRESSES.get(venue_name, f"Santa Barbara, CA 93101")
                city = get_city_from_address(address)
                zip_code = get_zip_from_address(address)
                
                # Parse times
                start_time, end_time = parse_event_time(current_date, time_info)
                
                # Categorize event
                category, genre = categorize_event(time_info + " " + artist_line, venue_name)
                
                # Create event
                event = {
                    "id": f"lnsb-{event_id:03d}",
                    "title": artist_line,
                    "category": category,
                    "genre": genre,
                    "city": city,
                    "zip": zip_code,
                    "start": start_time,
                    "end": end_time,
                    "venue": venue_name,
                    "address": address,
                    "popularity": 75  # Default popularity
                }
                
                events.append(event)
                event_id += 1
                
                # Limit to prevent too many events
                if len(events) >= 50:
                    break
        
        print(f"Scraped {len(events)} events from LiveNotesSB")
        return events
        
    except Exception as e:
        print(f"Error scraping LiveNotesSB: {e}")
        return []

if __name__ == "__main__":
    events = lnsb_fetch()
    for event in events[:3]:  # Show first 3 events
        print(f"ID: {event['id']}")
        print(f"Title: {event['title']}")
        print(f"Venue: {event['venue']}")
        print(f"Address: {event['address']}")
        print(f"Time: {event['start']} to {event['end']}")
        print("---")
