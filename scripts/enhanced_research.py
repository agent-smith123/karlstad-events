#!/usr/bin/env python3
"""
Enhanced Event Research for Karlstad Area
Multi-source event aggregation with deduplication
"""

import os
import re
import json
import yaml
import hashlib
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from urllib.parse import urljoin, urlparse

# Try to import optional dependencies
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# Configuration
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
CONTENT_DIR = PROJECT_DIR / "content" / "events"
DATA_DIR = PROJECT_DIR / "data"
VENUES_FILE = SCRIPT_DIR / "venues.yaml"
STATE_FILE = DATA_DIR / "research_state.json"
FAILED_SCRAPES_FILE = DATA_DIR / "failed_scrapes.json"
AI_REQUEST_FILE = DATA_DIR / ".ai-fetch-requested"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
CONTENT_DIR.mkdir(exist_ok=True)


def log_failed_scrape(venue_name: str, url: str, error: str):
    """Log failed scrapes for AI fallback"""
    failed = {"timestamp": datetime.now().isoformat(), "venue": venue_name, "url": url, "error": str(error)}
    
    data = {"failed": []}
    if FAILED_SCRAPES_FILE.exists():
        with open(FAILED_SCRAPES_FILE) as f:
            data = json.load(f)
    
    data["failed"].append(failed)
    
    with open(FAILED_SCRAPES_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def request_ai_fallback():
    """Trigger AI agent fallback"""
    print("\n🤖 Triggering AI agent fallback...")
    import subprocess
    try:
        subprocess.run(["python3", str(SCRIPT_DIR / "ai_fallback.py")], check=True)
    except Exception as e:
        print(f"  ⚠️ Could not trigger AI fallback: {e}")


@dataclass
class Event:
    """Standardized event data structure"""
    title: str
    date: str  # ISO format YYYY-MM-DD
    venue: str
    location: str
    time: Optional[str] = None
    link: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    
    def slug(self) -> str:
        """Generate unique slug for deduplication"""
        base = f"{self.date}-{self.venue}-{self.title}"
        return hashlib.md5(base.encode()).hexdigest()[:12]
    
    def to_markdown(self) -> str:
        """Convert to Hugo markdown format"""
        md = f"""---
title: "{self.title}"
date: {self.date}
venue: "{self.venue}"
location: "{self.location}"
"""
        if self.time:
            md += f'time: "{self.time}"\n'
        if self.link:
            md += f'link: "{self.link}"\n'
        if self.category:
            md += f'categories: ["{self.category}"]\n'
        if self.source:
            md += f'source: "{self.source}"\n'
        md += f"---\n\n"
        if self.description:
            md += f"{self.description}\n"
        return md


class EventStore:
    """Manages event persistence and deduplication"""
    
    def __init__(self):
        self.events: Dict[str, Event] = {}
        self.load_state()
    
    def load_state(self):
        """Load previously found events"""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE) as f:
                    data = json.load(f)
                    for slug, evt_data in data.get("events", {}).items():
                        self.events[slug] = Event(**evt_data)
                print(f"📚 Loaded {len(self.events)} existing events")
            except Exception as e:
                print(f"⚠️ Could not load state: {e}")
    
    def save_state(self):
        """Save current events to state file"""
        data = {
            "last_updated": datetime.now().isoformat(),
            "events": {slug: asdict(evt) for slug, evt in self.events.items()}
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    
    def add_event(self, event: Event) -> bool:
        """Add event if not duplicate, returns True if added"""
        slug = event.slug()
        if slug in self.events:
            return False
        self.events[slug] = event
        return True
    
    def get_new_events(self, since: datetime) -> List[Event]:
        """Get events added since given date"""
        # For now, return all events not yet written to markdown
        result = []
        for slug, event in self.events.items():
            md_file = CONTENT_DIR / f"{slug}.md"
            if not md_file.exists():
                result.append(event)
        return result
    
    def write_markdown_files(self):
        """Write all new events to markdown files"""
        count = 0
        for slug, event in self.events.items():
            md_file = CONTENT_DIR / f"{slug}.md"
            if not md_file.exists():
                with open(md_file, 'w') as f:
                    f.write(event.to_markdown())
                count += 1
        return count


class BaseScraper:
    """Base class for event scrapers"""
    
    def __init__(self, config: dict):
        self.config = config
        self.name = config.get('name', 'Unknown')
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def fetch(self, url: str) -> Optional[str]:
        """Fetch URL content"""
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"  ❌ Error fetching {url}: {e}")
            return None
    
    def scrape(self) -> List[Event]:
        """Override in subclasses"""
        return []


class StaticScraper(BaseScraper):
    """Scraper for static HTML sites using BeautifulSoup"""
    
    def scrape(self) -> List[Event]:
        if not HAS_BS4:
            print(f"  ⚠️ BeautifulSoup not installed, skipping {self.name}")
            return []
        
        events = []
        urls = self.config.get('urls', {})
        
        # Try each URL
        for key, url in urls.items():
            if 'scraper' in self.config and self.config['scraper'].get('type') != 'static':
                continue
                
            print(f"  🔍 Checking {key}: {url}")
            html = self.fetch(url)
            if not html:
                continue
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract events based on selectors or generic patterns
            selectors = self.config.get('scraper', {}).get('selectors', {})
            event_selector = selectors.get('event', '.event, .activity, article')
            
            for elem in soup.select(event_selector):
                try:
                    event = self._parse_event(elem, selectors, url)
                    if event:
                        events.append(event)
                except Exception as e:
                    print(f"    ⚠️ Parse error: {e}")
        
        return events
    
    def _parse_event(self, elem, selectors: dict, base_url: str) -> Optional[Event]:
        """Parse individual event element"""
        # Try to extract title
        title_sel = selectors.get('title', 'h1, h2, h3, h4, .title')
        title_elem = elem.select_one(title_sel)
        if not title_elem:
            return None
        title = title_elem.get_text(strip=True)
        
        # Try to extract date
        date_str = None
        date_sel = selectors.get('date', '.date, time, .datetime')
        date_elem = elem.select_one(date_sel)
        if date_elem:
            date_str = self._parse_date(date_elem.get_text(strip=True))
        
        if not date_str:
            return None  # Skip events without dates
        
        # Try to extract link
        link = None
        link_sel = selectors.get('link', 'a[href]')
        link_elem = elem.select_one(link_sel)
        if link_elem:
            href = link_elem.get('href', '')
            link = urljoin(base_url, href)
        
        return Event(
            title=title,
            date=date_str,
            venue=self.name,
            location=self.config.get('location', 'Karlstad'),
            link=link,
            source=self.name,
            source_url=base_url
        )
    
    def _parse_date(self, text: str) -> Optional[str]:
        """Try to parse various date formats"""
        # Common Swedish date patterns
        patterns = [
            r'(\d{4})-(\d{2})-(\d{2})',  # 2026-03-15
            r'(\d{2})\s+(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec)[\.\s]+(\d{4})',  # 15 mars 2026
            r'(\d{2})/(\d{2})-(\d{2})/(\d{2})',  # Date ranges
        ]
        
        months = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'maj': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'okt': 10, 'nov': 11, 'dec': 12
        }
        
        # Try ISO format first
        match = re.search(r'(\d{4})-(\d{2})-(\d{2})', text)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        
        # Try Swedish format
        match = re.search(r'(\d{1,2})\s+(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec)[\.\s]+(\d{4})', text.lower())
        if match:
            day = int(match.group(1))
            month = months.get(match.group(2)[:3], 1)
            year = int(match.group(3))
            return f"{year}-{month:02d}-{day:02d}"
        
        return None


class TicketmasterAPI:
    """Ticketmaster Discovery API integration"""
    
    BASE_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('TICKETMASTER_API_KEY')
    
    def search_karlstad(self, radius: int = 50) -> List[Event]:
        """Search for events near Karlstad"""
        if not self.api_key:
            print("  ⚠️ No Ticketmaster API key configured")
            return []
        
        events = []
        params = {
            'apikey': self.api_key,
            'city': 'Karlstad',
            'countryCode': 'SE',
            'radius': radius,
            'unit': 'km',
            'size': 100,
            'sort': 'date,asc'
        }
        
        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            for item in data.get('_embedded', {}).get('events', []):
                event = self._parse_api_event(item)
                if event:
                    events.append(event)
                    
        except Exception as e:
            print(f"  ❌ Ticketmaster API error: {e}")
        
        return events
    
    def _parse_api_event(self, data: dict) -> Optional[Event]:
        """Parse Ticketmaster API event object"""
        try:
            name = data.get('name', '')
            
            # Get date
            dates = data.get('dates', {}).get('start', {})
            date_str = dates.get('localDate')
            time_str = dates.get('localTime')
            
            if not date_str:
                return None
            
            # Get venue
            venues = data.get('_embedded', {}).get('venues', [])
            venue_name = venues[0].get('name', 'Unknown') if venues else 'Unknown'
            city = venues[0].get('city', {}).get('name', 'Karlstad') if venues else 'Karlstad'
            
            # Get URL
            url = data.get('url')
            
            # Get category
            classifications = data.get('classifications', [])
            category = 'Evenemang'
            if classifications:
                cat = classifications[0].get('segment', {}).get('name', '')
                if cat:
                    category = cat
            
            return Event(
                title=name,
                date=date_str,
                venue=venue_name,
                location=city,
                time=time_str,
                link=url,
                category=category,
                source='Ticketmaster',
                source_url='https://www.ticketmaster.se'
            )
        except Exception as e:
            print(f"    ⚠️ Parse error: {e}")
            return None


class EnhancedResearcher:
    """Main research coordinator"""
    
    def __init__(self):
        self.store = EventStore()
        self.venues = self._load_venues()
        self.ticketmaster = TicketmasterAPI()
    
    def _load_venues(self) -> dict:
        """Load venue configuration"""
        if VENUES_FILE.exists():
            with open(VENUES_FILE) as f:
                return yaml.safe_load(f)
        return {}
    
    def run_research(self):
        """Execute full research cycle"""
        print("🔍 Enhanced Event Research for Karlstad Area")
        print("=" * 50)
        
        new_events = 0
        
        # 1. Ticketmaster API
        print("\n📡 Phase 1: Ticketmaster API")
        events = self.ticketmaster.search_karlstad()
        for evt in events:
            if self.store.add_event(evt):
                new_events += 1
                print(f"  ✓ {evt.date}: {evt.title[:50]}...")
        
        # 2. Static scrapers for Tier 1 & 2 venues
        print("\n🌐 Phase 2: Venue Websites")
        for tier in ['tier1_major', 'tier2_cultural']:
            venues = self.venues.get(tier, {})
            for key, config in venues.items():
                if not config.get('active', False):
                    continue
                scraper_type = config.get('scraper', {}).get('type')
                if scraper_type == 'static':
                    print(f"\n  📍 {config['name']}")
                    scraper = StaticScraper(config)
                    events = scraper.scrape()
                    for evt in events:
                        if self.store.add_event(evt):
                            new_events += 1
                            print(f"    ✓ {evt.date}: {evt.title[:40]}...")
        
        # 3. Aggregator sites
        print("\n📊 Phase 3: Aggregator Sites")
        aggregators = self.venues.get('tier4_aggregators', {})
        for key, config in aggregators.items():
            if config.get('scraper', {}).get('type') == 'static':
                print(f"\n  📍 {config['name']}")
                scraper = StaticScraper(config)
                events = scraper.scrape()
                for evt in events:
                    if self.store.add_event(evt):
                        new_events += 1
                        print(f"    ✓ {evt.date}: {evt.title[:40]}...")
        
        # Save results
        print(f"\n💾 Saving {new_events} new events")
        self.store.save_state()
        
        # Write markdown files
        written = self.store.write_markdown_files()
        print(f"📝 Wrote {written} new markdown files")
        
        return written


def run_venue_discovery():
    """Run venue discovery cycle"""
    print("\n🔍 Running venue discovery...")
    try:
        import subprocess
        result = subprocess.run(
            ["python3", str(SCRIPT_DIR / "venue_discovery.py")],
            capture_output=True,
            text=True,
            timeout=120
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"  ⚠️ Discovery warning: {result.stderr}")
    except Exception as e:
        print(f"  ⚠️ Could not run discovery: {e}")


def main():
    """Entry point with error handling and fallback"""
    success = False
    total_events = 0
    
    try:
        researcher = EnhancedResearcher()
        total_events = researcher.run_research()
        success = True
        print(f"\n✅ Research complete! Found {total_events} new events.")
        
    except Exception as e:
        print(f"\n❌ Research failed: {e}")
        import traceback
        traceback.print_exc()
        
        # Log failure and trigger AI fallback
        log_failed_scrape("research_cycle", "multiple", str(e))
        request_ai_fallback()
        success = False
    
    # Always try venue discovery (non-critical)
    try:
        run_venue_discovery()
    except Exception as e:
        print(f"  ⚠️ Venue discovery failed: {e}")
    
    # Return appropriate exit code
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
