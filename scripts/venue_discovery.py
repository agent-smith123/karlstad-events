#!/usr/bin/env python3
"""
Venue Discovery Module for Karlstad Events
Continuously searches for new event sources and venues in the area
"""

import os
import re
import json
import yaml
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, asdict

# Configuration
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
VENUES_FILE = SCRIPT_DIR / "venues.yaml"
NEW_SOURCES_FILE = DATA_DIR / "new-sources.json"
DISCOVERY_LOG = DATA_DIR / "discovery-log.json"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)

# Search areas (expandable)
SEARCH_AREAS = [
    "Karlstad",
    "Forshaga", 
    "Kil",
    "Molkom",
    "Skattkärr",
    "Väse",
    "Vålberg",
    "Deje",
    # Nearby areas to expand coverage
    "Hammarö",
    "Kristinehamn",
    "Sunne",
    "Torsby",
    "Årjäng",
    "Säffle",
    "Arvika",
    "Grums",
]

# Event keywords for search
EVENT_KEYWORDS = [
    "evenemang",
    "konserter",
    "teater",
    "festival",
    "kultur",
    "nöje",
    "utställningar",
    "live music",
    "pub quiz",
    "stand-up",
    "opera",
    "musikal",
]


@dataclass
class DiscoveredVenue:
    """Newly discovered venue candidate"""
    name: str
    location: str
    url: Optional[str] = None
    type: Optional[str] = None
    source: Optional[str] = None  # How it was found
    confidence: str = "medium"  # low, medium, high
    discovered_date: str = None
    notes: Optional[str] = None
    
    def __post_init__(self):
        if self.discovered_date is None:
            self.discovered_date = datetime.now().isoformat()


class VenueDiscovery:
    """Discovers new event venues and sources"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; KarlstadEventsBot/1.0)'
        })
        self.known_venues = self._load_known_venues()
        self.new_sources = self._load_new_sources()
        self.discovery_log = self._load_discovery_log()
    
    def _load_known_venues(self) -> Set[str]:
        """Load all currently known venue names"""
        known = set()
        if VENUES_FILE.exists():
            with open(VENUES_FILE) as f:
                data = yaml.safe_load(f)
                for tier in ['tier1_major', 'tier2_cultural', 'tier3_small', 'tier4_aggregators', 'tier5_municipal']:
                    for key, venue in data.get(tier, {}).items():
                        known.add(venue.get('name', '').lower())
                        known.add(key.lower())
        return known
    
    def _load_new_sources(self) -> List[Dict]:
        """Load previously discovered but unreviewed sources"""
        if NEW_SOURCES_FILE.exists():
            with open(NEW_SOURCES_FILE) as f:
                return json.load(f).get('venues', [])
        return []
    
    def _load_discovery_log(self) -> Dict:
        """Load discovery activity log"""
        if DISCOVERY_LOG.exists():
            with open(DISCOVERY_LOG) as f:
                return json.load(f)
        return {"searches": [], "discoveries": []}
    
    def save_new_sources(self):
        """Save new sources for review"""
        with open(NEW_SOURCES_FILE, 'w') as f:
            json.dump({
                "last_updated": datetime.now().isoformat(),
                "venues": [asdict(v) if isinstance(v, DiscoveredVenue) else v for v in self.new_sources]
            }, f, indent=2, default=str)
    
    def save_discovery_log(self):
        """Save discovery log"""
        with open(DISCOVERY_LOG, 'w') as f:
            json.dump(self.discovery_log, f, indent=2, default=str)
    
    def is_known(self, name: str) -> bool:
        """Check if venue is already known"""
        name_lower = name.lower()
        return any(name_lower in known or known in name_lower for known in self.known_venues)
    
    def add_discovery(self, venue: DiscoveredVenue):
        """Add a newly discovered venue"""
        if not self.is_known(venue.name):
            self.new_sources.append(asdict(venue))
            self.discovery_log["discoveries"].append({
                "date": datetime.now().isoformat(),
                "name": venue.name,
                "location": venue.location,
                "source": venue.source
            })
            print(f"  ✨ New discovery: {venue.name} ({venue.location})")
            return True
        return False
    
    def search_web_for_venues(self, area: str, keyword: str) -> List[DiscoveredVenue]:
        """Search web for venues in an area"""
        discovered = []
        
        # This would integrate with Brave Search API
        # For now, we'll use a placeholder that can be enhanced
        query = f"{keyword} {area}"
        
        try:
            # Note: In production, this would call Brave Search API
            # search_results = brave_search(query)
            # For now, we log the search attempt
            self.discovery_log["searches"].append({
                "date": datetime.now().isoformat(),
                "query": query,
                "area": area,
                "keyword": keyword
            })
        except Exception as e:
            print(f"  ⚠️ Search error for '{query}': {e}")
        
        return discovered
    
    def check_facebook_pages(self, area: str) -> List[DiscoveredVenue]:
        """Look for venue Facebook pages (manual list to check)"""
        # Common patterns for venue Facebook pages
        suggestions = [
            f"https://facebook.com/search/top?q={area}+evenemang",
            f"https://facebook.com/search/top?q={area}+konsert",
        ]
        
        venues = []
        for url in suggestions:
            venues.append(DiscoveredVenue(
                name=f"Facebook search: {area}",
                location=area,
                url=url,
                type="social_media",
                source="facebook_search",
                confidence="low",
                notes="Manual review needed - check for venue pages"
            ))
        
        return venues
    
    def check_google_maps(self, area: str) -> List[DiscoveredVenue]:
        """Generate Google Maps search URLs for venues"""
        venue_types = [
            "konserthall",
            "teater",
            "kulturhus",
            "pub",
            "restaurang+live+music",
            "evenemangslokal",
        ]
        
        venues = []
        for vtype in venue_types:
            venues.append(DiscoveredVenue(
                name=f"Google Maps: {vtype.replace('+', ' ')} i {area}",
                location=area,
                url=f"https://www.google.com/maps/search/{vtype}+{area}",
                type=vtype.replace('+', '_'),
                source="google_maps",
                confidence="low",
                notes="Browse for potential event venues"
            ))
        
        return venues
    
    def run_discovery_cycle(self):
        """Run a full discovery cycle"""
        print("🔍 Venue Discovery Cycle")
        print("=" * 40)
        
        total_new = 0
        
        # Check each area
        for area in SEARCH_AREAS:
            print(f"\n📍 Exploring {area}...")
            
            # Web searches
            for keyword in EVENT_KEYWORDS[:3]:  # Limit to avoid rate limits
                venues = self.search_web_for_venues(area, keyword)
                for v in venues:
                    if self.add_discovery(v):
                        total_new += 1
            
            # Facebook suggestions
            fb_venues = self.check_facebook_pages(area)
            for v in fb_venues:
                if self.add_discovery(v):
                    total_new += 1
            
            # Google Maps suggestions
            map_venues = self.check_google_maps(area)
            for v in map_venues:
                if self.add_discovery(v):
                    total_new += 1
        
        # Save results
        self.save_new_sources()
        self.save_discovery_log()
        
        print(f"\n✅ Discovery complete!")
        print(f"📋 Total new sources pending review: {len(self.new_sources)}")
        print(f"🆕 Found this cycle: {total_new}")
        
        return total_new
    
    def get_pending_reviews(self) -> List[Dict]:
        """Get venues pending human review"""
        return self.new_sources
    
    def approve_venue(self, venue_name: str, tier: str = "tier3_small"):
        """Move approved venue from pending to active config"""
        # Find in new sources
        for i, v in enumerate(self.new_sources):
            if v.get('name') == venue_name:
                # Add to venues.yaml
                self._add_to_venues_yaml(v, tier)
                # Remove from pending
                self.new_sources.pop(i)
                self.save_new_sources()
                print(f"✅ Approved: {venue_name} added to {tier}")
                return True
        return False
    
    def _add_to_venues_yaml(self, venue: Dict, tier: str):
        """Add approved venue to configuration"""
        if VENUES_FILE.exists():
            with open(VENUES_FILE) as f:
                data = yaml.safe_load(f)
            
            # Generate key from name
            key = re.sub(r'[^a-z0-9]', '_', venue['name'].lower())[:30]
            
            # Add to appropriate tier
            if tier not in data:
                data[tier] = {}
            
            data[tier][key] = {
                'name': venue['name'],
                'location': venue.get('location', 'Karlstad'),
                'type': [venue.get('type', 'Evenemang')],
                'urls': {'main': venue.get('url')} if venue.get('url') else {},
                'scraper': {'type': 'manual'},
                'active': True
            }
            
            with open(VENUES_FILE, 'w') as f:
                yaml.dump(data, f, allow_unicode=True, sort_keys=False)


def main():
    """Entry point for discovery"""
    discovery = VenueDiscovery()
    count = discovery.run_discovery_cycle()
    
    # Show pending reviews
    pending = discovery.get_pending_reviews()
    if pending:
        print("\n📋 Pending Review:")
        for v in pending[-5:]:  # Show last 5
            print(f"  • {v.get('name')} ({v.get('location')}) - {v.get('confidence')} confidence")
    
    return count


if __name__ == "__main__":
    main()
