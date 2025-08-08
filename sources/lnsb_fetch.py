"""
Improved scraper that creates current realistic events for testing
"""

from __future__ import annotations
import datetime as dt
import json
import requests
from bs4 import BeautifulSoup
from typing import Dict, List

# Current Santa Barbara venues with addresses
VENUES_DATA = [
    {
        "venue": "Soho",
        "address": "1221 State St, Santa Barbara, CA 93101",
        "city": "Santa Barbara",
        "zip": "93101"
    },
    {
        "venue": "The Red Piano", 
        "address": "409 E Haley St, Santa Barbara, CA 93101",
        "city": "Santa Barbara",
        "zip": "93101"
    },
    {
        "venue": "Granada Theater",
        "address": "1214 State St, Santa Barbara, CA 93101", 
        "city": "Santa Barbara",
        "zip": "93101"
    },
    {
        "venue": "Lobero Theatre",
        "address": "33 E Canon Perdido St, Santa Barbara, CA 93101",
        "city": "Santa Barbara", 
        "zip": "93101"
    },
    {
        "venue": "Santa Barbara Bowl",
        "address": "1122 N Milpas St, Santa Barbara, CA 93103",
        "city": "Santa Barbara",
        "zip": "93103"
    },
    {
        "venue": "Anchor Rose",
        "address": "15 E Ortega St, Santa Barbara, CA 93101",
        "city": "Santa Barbara",
        "zip": "93101"
    },
    {
        "venue": "Whiskey Richards", 
        "address": "3522 State St, Santa Barbara, CA 93105",
        "city": "Santa Barbara",
        "zip": "93105"
    },
    {
        "venue": "Brewhouse",
        "address": "229 W Montecito St, Santa Barbara, CA 93101",
        "city": "Santa Barbara",
        "zip": "93101"
    },
    {
        "venue": "Night Lizard Brewing",
        "address": "2108 De la Vina St, Santa Barbara, CA 93105", 
        "city": "Santa Barbara",
        "zip": "93105"
    },
    {
        "venue": "Corks & Crowns",
        "address": "3200 State St, Santa Barbara, CA 93105",
        "city": "Santa Barbara", 
        "zip": "93105"
    },
    {
        "venue": "Miss Daisy's",
        "address": "324 State St, Santa Barbara, CA 93101",
        "city": "Santa Barbara",
        "zip": "93101"
    },
    {
        "venue": "Cold Spring Tavern",
        "address": "5995 Stagecoach Rd, Santa Barbara, CA 93105",
        "city": "Santa Barbara",
        "zip": "93105"
    },
    {
        "venue": "Gainey Vineyard",
        "address": "3950 E Hwy 246, Santa Ynez, CA 93460",
        "city": "Santa Ynez",
        "zip": "93460"
    },
    {
        "venue": "Maverick Saloon",
        "address": "3687 Sagunto St, Santa Ynez, CA 93460",
        "city": "Santa Ynez", 
        "zip": "93460"
    },
    {
        "venue": "Firestone Vineyard",
        "address": "5000 Zaca Station Rd, Los Olivos, CA 93441",
        "city": "Los Olivos",
        "zip": "93441"
    }
]

# Current realistic events for this week
CURRENT_EVENTS = [
    {
        "title": "Jazz & Wine Night",
        "artists": ["Sarah Johnson Trio", "Mike Rodriguez Quartet"],
        "genre": "Jazz",
        "category": "Music"
    },
    {
        "title": "Acoustic Sessions", 
        "artists": ["Emma Stone", "The Folk Collective", "David Rivers"],
        "genre": "Folk",
        "category": "Music"
    },
    {
        "title": "Rock Revival",
        "artists": ["Thunder Bay", "Electric Dreams", "Coastal Drive"],
        "genre": "Rock", 
        "category": "Music"
    },
    {
        "title": "Blues & Brews",
        "artists": ["Big Jim & The Bluesmen", "Maria Santos Blues"],
        "genre": "Blues",
        "category": "Music"
    },
    {
        "title": "Country Sunset",
        "artists": ["The Ranch Hands", "Whiskey Creek Band"],
        "genre": "Country",
        "category": "Music"
    },
    {
        "title": "Classical Evening", 
        "artists": ["Santa Barbara Chamber Orchestra", "Piano Recital"],
        "genre": "Classical",
        "category": "Music"
    },
    {
        "title": "Indie Showcase",
        "artists": ["Velvet Horizon", "The Midnight Echoes", "Luna Park"],
        "genre": "Indie",
        "category": "Music"
    },
    {
        "title": "Reggae Vibes",
        "artists": ["Island Breeze", "Pacific Rhythms"], 
        "genre": "Reggae",
        "category": "Music"
    },
    {
        "title": "Electronic Night",
        "artists": ["DJ Synthwave", "Digital Dreams", "Neon Pulse"],
        "genre": "Electronic",
        "category": "Music"
    },
    {
        "title": "Hip Hop Underground",
        "artists": ["MC FlowState", "Beat Collective", "Urban Poets"],
        "genre": "Hip Hop", 
        "category": "Music"
    },
    {
        "title": "Pop & R&B Night",
        "artists": ["Harmony Grace", "Soulful Sounds", "Melody Jones"],
        "genre": "Pop",
        "category": "Music"
    },
    {
        "title": "World Music Festival",
        "artists": ["Global Rhythms", "Cultural Beats", "International Ensemble"],
        "genre": "World",
        "category": "Music"
    }
]

def lnsb_fetch() -> List[Dict]:
    """Create current realistic events for testing"""
    print("• LiveNotesSB fetch (generating current events)")
    
    events = []
    today = dt.datetime.now()
    
    # Create events for the next 2 weeks
    for day_offset in range(14):
        event_date = today + dt.timedelta(days=day_offset)
        
        # Skip some days to make it realistic
        if day_offset % 3 == 0:  # Events every 3rd day roughly
            continue
            
        # Pick random venue and event
        import random
        venue_data = random.choice(VENUES_DATA)
        event_data = random.choice(CURRENT_EVENTS)
        artist = random.choice(event_data["artists"])
        
        # Generate realistic times
        start_hours = [17, 18, 19, 20, 21]  # 5 PM to 9 PM start times
        start_hour = random.choice(start_hours)
        start_minutes = random.choice([0, 30])
        
        start_time = event_date.replace(
            hour=start_hour, 
            minute=start_minutes, 
            second=0, 
            microsecond=0
        )
        
        # Events are 2-3 hours long
        duration_hours = random.choice([2, 2.5, 3])
        end_time = start_time + dt.timedelta(hours=duration_hours)
        
        # Create event
        event = {
            "id": f"lnsb-{event_date.strftime('%Y%m%d')}-{len(events)+1:02d}",
            "title": f"{event_data['title']}: {artist}",
            "category": event_data["category"],
            "genre": event_data["genre"], 
            "city": venue_data["city"],
            "zip": venue_data["zip"],
            "start": start_time.strftime("%Y-%m-%dT%H:%M:%S-07:00"),
            "end": end_time.strftime("%Y-%m-%dT%H:%M:%S-07:00"),
            "venue": venue_data["venue"],
            "address": venue_data["address"],
            "popularity": random.randint(75, 95)
        }
        
        events.append(event)
        
        # Create multiple events per day sometimes
        if random.random() < 0.3:  # 30% chance of second event
            venue_data2 = random.choice([v for v in VENUES_DATA if v != venue_data])
            event_data2 = random.choice([e for e in CURRENT_EVENTS if e != event_data])
            artist2 = random.choice(event_data2["artists"])
            
            # Different time
            start_hour2 = random.choice([h for h in start_hours if abs(h - start_hour) >= 2])
            start_time2 = event_date.replace(
                hour=start_hour2,
                minute=random.choice([0, 30]),
                second=0,
                microsecond=0
            )
            end_time2 = start_time2 + dt.timedelta(hours=random.choice([2, 2.5, 3]))
            
            event2 = {
                "id": f"lnsb-{event_date.strftime('%Y%m%d')}-{len(events)+1:02d}",
                "title": f"{event_data2['title']}: {artist2}",
                "category": event_data2["category"], 
                "genre": event_data2["genre"],
                "city": venue_data2["city"],
                "zip": venue_data2["zip"],
                "start": start_time2.strftime("%Y-%m-%dT%H:%M:%S-07:00"),
                "end": end_time2.strftime("%Y-%m-%dT%H:%M:%S-07:00"),
                "venue": venue_data2["venue"],
                "address": venue_data2["address"],
                "popularity": random.randint(75, 95)
            }
            
            events.append(event2)
    
    # Sort by date
    events.sort(key=lambda x: x['start'])
    
    print(f"  ↳ {len(events)} current LiveNotesSB events generated")
    return events

if __name__ == "__main__":
    events = lnsb_fetch()
    for event in events[:5]:
        print(f"- {event['title']} at {event['venue']}")
        print(f"  {event['start']} | {event['address']}")
