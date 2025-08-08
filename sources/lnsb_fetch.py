#!/usr/bin/env python3
"""
Simple test scraper to debug LiveNotesSB issues
"""

import requests
from bs4 import BeautifulSoup
import json
import datetime as dt

def test_lnsb_connection():
    """Test if we can connect to LiveNotesSB"""
    print("Testing connection to LiveNotesSB...")
    
    try:
        response = requests.get("https://livenotessb.com/", timeout=10)
        print(f"Status code: {response.status_code}")
        print(f"Content length: {len(response.text)} characters")
        
        if response.status_code == 200:
            # Save first 1000 characters to see what we got
            preview = response.text[:1000]
            print("First 1000 characters:")
            print(preview)
            print("="*50)
            
            # Look for event indicators
            soup = BeautifulSoup(response.text, 'html.parser')
            text_content = soup.get_text()
            
            # Check for common LiveNotesSB patterns
            if "SUNDAY" in text_content or "MONDAY" in text_content:
                print("✅ Found day headers - looks like event data is there")
            else:
                print("❌ No day headers found")
                
            if "SANTA BARBARA" in text_content:
                print("✅ Found Santa Barbara references")
            else:
                print("❌ No Santa Barbara references found")
                
            if "*" in text_content[:2000]:  # Check first 2000 chars for venue markers
                print("✅ Found * markers (likely venues)")
            else:
                print("❌ No * venue markers found")
                
            return True
        else:
            print(f"❌ Bad status code: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

def create_sample_events():
    """Create some sample events as backup"""
    print("Creating sample LiveNotesSB events...")
    
    events = []
    base_date = dt.datetime.now() + dt.timedelta(days=1)
    
    sample_data = [
        {
            "title": "Live Jazz at Soho",
            "venue": "Soho",
            "genre": "Jazz",
            "time": "7:30 pm"
        },
        {
            "title": "Blues Night at The Red Piano", 
            "venue": "The Red Piano",
            "genre": "Blues",
            "time": "8:00 pm"
        },
        {
            "title": "Acoustic Evening at Anchor Rose",
            "venue": "Anchor Rose", 
            "genre": "Folk",
            "time": "6:00 pm"
        },
        {
            "title": "Rock Show at Whiskey Richards",
            "venue": "Whiskey Richards",
            "genre": "Rock", 
            "time": "9:00 pm"
        },
        {
            "title": "Wine Country Music at Gainey Vineyard",
            "venue": "Gainey Vineyard",
            "genre": "Country",
            "time": "3:00 pm"
        }
    ]
    
    venue_addresses = {
        "Soho": "1221 State St, Santa Barbara, CA 93101",
        "The Red Piano": "409 E Haley St, Santa Barbara, CA 93101", 
        "Anchor Rose": "15 E Ortega St, Santa Barbara, CA 93101",
        "Whiskey Richards": "3522 State St, Santa Barbara, CA 93105",
        "Gainey Vineyard": "3950 E Hwy 246, Santa Ynez, CA 93460"
    }
    
    for i, data in enumerate(sample_data, 1):
        # Calculate date and time
        event_date = base_date + dt.timedelta(days=i)
        
        # Parse time
        time_str = data["time"]
        if "pm" in time_str:
            hour = int(time_str.split(":")[0])
            if hour != 12:
                hour += 12
        else:
            hour = int(time_str.split(":")[0])
            
        minutes = 0
        if ":" in time_str:
            minutes = int(time_str.split(":")[1].split()[0])
            
        start_time = event_date.replace(hour=hour, minute=minutes, second=0, microsecond=0)
        end_time = start_time + dt.timedelta(hours=2)
        
        # Get address
        address = venue_addresses.get(data["venue"], "Santa Barbara, CA 93101")
        
        # Determine city and zip from address
        if "Santa Ynez" in address:
            city = "Santa Ynez"
            zip_code = "93460"
        elif "Goleta" in address:
            city = "Goleta" 
            zip_code = "93117"
        else:
            city = "Santa Barbara"
            zip_code = "93101"
        
        event = {
            "id": f"lnsb-{i:03d}",
            "title": data["title"],
            "category": "Music",
            "genre": data["genre"],
            "city": city,
            "zip": zip_code,
            "start": start_time.strftime("%Y-%m-%dT%H:%M:%S-07:00"),
            "end": end_time.strftime("%Y-%m-%dT%H:%M:%S-07:00"),
            "venue": data["venue"],
            "address": address,
            "popularity": 75 + (i * 3)  # Varying popularity
        }
        
        events.append(event)
    
    return events

def main():
    print("LiveNotesSB Scraper Debug Test")
    print("=" * 40)
    
    # Test connection first
    if test_lnsb_connection():
        print("\n🔄 Attempting to scrape real events...")
        try:
            # Try to import and run the real scraper
            from lnsb_fetch import lnsb_fetch
            real_events = lnsb_fetch()
            
            if real_events:
                print(f"✅ Real scraper worked! Found {len(real_events)} events")
                # Show first event
                print("First real event:")
                print(json.dumps(real_events[0], indent=2))
                return real_events
            else:
                print("❌ Real scraper returned no events")
        except Exception as e:
            print(f"❌ Real scraper failed: {e}")
    
    print("\n🔄 Creating sample events instead...")
    sample_events = create_sample_events()
    print(f"✅ Created {len(sample_events)} sample events")
    
    # Show first sample event
    print("First sample event:")
    print(json.dumps(sample_events[0], indent=2))
    
    return sample_events

if __name__ == "__main__":
    events = main()
