#!/usr/bin/env python3
"""
AI Event Fetcher - Fallback for manual venues
Uses web search and browser automation to fetch events from venues
that can't be scraped automatically
"""

import os
import re
import json
import time
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
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
DATA_DIR = PROJECT_DIR / "data"
CACHE_FILE = DATA_DIR / "ai_fetch_cache.json"
CACHE_DURATION_HOURS = 24

# Current year for validation
CURRENT_YEAR = datetime.now().year
VALID_YEARS = {CURRENT_YEAR, CURRENT_YEAR + 1}


@dataclass
class AIFetchedEvent:
    """Event fetched by AI agent"""
    title: str
    date: str  # ISO format YYYY-MM-DD
    venue: str
    location: str
    time: Optional[str] = None
    link: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    confidence: float = 0.5  # How confident we are in the extraction


class WebSearchClient:
    """Client for web search APIs (Brave Search)"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('BRAVE_API_KEY') or os.getenv('WEB_SEARCH_API_KEY')
        self.base_url = "https://api.search.brave.com/res/v1/web/search"
    
    def search(self, query: str, count: int = 10) -> List[Dict]:
        """Perform web search"""
        if not self.api_key:
            # Fallback to simulated search (return venue URL)
            return self._simulate_search(query)
        
        try:
            headers = {
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key
            }
            params = {
                "q": query,
                "count": count,
                "search_lang": "sv"
            }
            
            resp = requests.get(self.base_url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            results = []
            for item in data.get('web', {}).get('results', []):
                results.append({
                    'title': item.get('title', ''),
                    'url': item.get('url', ''),
                    'description': item.get('description', '')
                })
            
            return results
            
        except Exception as e:
            print(f"    ⚠️  Web search error: {e}")
            return self._simulate_search(query)
    
    def _simulate_search(self, query: str) -> List[Dict]:
        """Fallback when no API key - return likely venue URLs"""
        # Extract venue name from query
        venue_match = re.search(r'(.+?)\s+evenemang', query, re.IGNORECASE)
        if venue_match:
            venue_name = venue_match.group(1).strip()
            return [{
                'title': f'{venue_name} Evenemang',
                'url': f'https://www.google.com/search?q={query.replace(" ", "+")}',
                'description': f'Search for events at {venue_name}'
            }]
        return []


class AIEventFetcher:
    """
    AI-powered event fetcher for venues that can't be scraped automatically.
    Uses web search and browser automation to find and extract events.
    """
    
    def __init__(self, venues_config: dict):
        self.venues = venues_config
        self.search_client = WebSearchClient()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self.cache = self._load_cache()
    
    def _load_cache(self) -> Dict:
        """Load cached results"""
        if CACHE_FILE.exists():
            with open(CACHE_FILE) as f:
                return json.load(f)
        return {}
    
    def _save_cache(self):
        """Save cache to disk"""
        with open(CACHE_FILE, 'w') as f:
            json.dump(self.cache, f, indent=2)
    
    def _is_cache_valid(self, venue_key: str) -> bool:
        """Check if cached data is still valid"""
        if venue_key not in self.cache:
            return False
        
        cached = self.cache[venue_key]
        cached_time = datetime.fromisoformat(cached.get('timestamp', '2000-01-01'))
        age = datetime.now() - cached_time
        
        return age.total_seconds() < CACHE_DURATION_HOURS * 3600
    
    def fetch_manual_venues(self) -> List[AIFetchedEvent]:
        """Fetch events from all venues marked as manual with AI fallback"""
        all_events = []
        
        print("\n🤖 AI Event Fetcher - Manual Venues")
        print("=" * 50)
        
        # Find all venues with manual + AI fallback
        manual_venues = self._find_manual_venues()
        
        if not manual_venues:
            print("  ℹ️  No manual venues with AI fallback configured")
            return all_events
        
        print(f"  📋 Found {len(manual_venues)} venues to fetch\n")
        
        for venue_key, config in manual_venues:
            try:
                events = self._fetch_venue(venue_key, config)
                all_events.extend(events)
                
                # Be nice to servers
                time.sleep(1)
                
            except Exception as e:
                print(f"  ❌ Error fetching {config.get('name', venue_key)}: {e}")
        
        # Filter valid events
        valid_events = [e for e in all_events if self._is_valid_event(e)]
        
        print(f"\n  ✅ Total AI-fetched events: {len(valid_events)}")
        
        return valid_events
    
    def _find_manual_venues(self) -> List[Tuple[str, dict]]:
        """Find all venues that need AI fallback"""
        manual_venues = []
        
        for tier in ['tier1_major', 'tier2_cultural', 'tier3_small', 'tier4_aggregators', 'tier5_municipal']:
            tier_venues = self.venues.get(tier, {})
            for venue_key, config in tier_venues.items():
                if not config.get('active', False):
                    continue
                
                scraper_config = config.get('scraper', {})
                scraper_type = scraper_config.get('type', 'static')
                fallback = scraper_config.get('fallback')
                
                if scraper_type == 'manual' and fallback == 'ai':
                    manual_venues.append((venue_key, config))
        
        return manual_venues
    
    def _fetch_venue(self, venue_key: str, config: dict) -> List[AIFetchedEvent]:
        """Fetch events from a single venue using AI methods"""
        venue_name = config.get('name', venue_key)
        location = config.get('location', 'Karlstad')
        
        print(f"  🔍 {venue_name}")
        
        # Check cache first
        if self._is_cache_valid(venue_key):
            cached_events = self.cache[venue_key].get('events', [])
            print(f"    ✓ Using cached data ({len(cached_events)} events)")
            return [AIFetchedEvent(**e) for e in cached_events]
        
        events = []
        urls = config.get('urls', {})
        
        # Strategy 1: Try venue URLs directly
        if urls:
            for url_type, url in urls.items():
                if isinstance(url, str) and url.startswith('http'):
                    page_events = self._fetch_from_url(url, config)
                    events.extend(page_events)
        
        # Strategy 2: Use web search if no events found
        if not events:
            search_events = self._fetch_from_search(venue_name, location, config)
            events.extend(search_events)
        
        # Strategy 3: Use browser automation for JS-heavy sites
        if not events and HAS_PLAYWRIGHT and urls:
            for url_type, url in urls.items():
                if isinstance(url, str) and url.startswith('http'):
                    browser_events = self._fetch_with_browser(url, config)
                    events.extend(browser_events)
        
        # Cache results
        self.cache[venue_key] = {
            'timestamp': datetime.now().isoformat(),
            'events': [e.__dict__ for e in events]
        }
        self._save_cache()
        
        print(f"    ✓ Found {len(events)} events")
        
        return events
    
    def _fetch_from_url(self, url: str, config: dict) -> List[AIFetchedEvent]:
        """Fetch events from a URL using static scraping"""
        events = []
        
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            
            if not HAS_BS4:
                return events
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Look for structured data (JSON-LD)
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        if data.get('@type') == 'Event':
                            event = self._parse_jsonld_event(data, config, url)
                            if event:
                                events.append(event)
                        elif 'Event' in str(data):
                            # Check for event list
                            pass
                except:
                    pass
            
            # Look for common event patterns
            event_selectors = [
                ('article', ['event', 'program', 'forestallning']),
                ('div', ['event', 'program', 'activity', 'kalender']),
                ('li', ['event', 'program'])
            ]
            
            for tag, classes in event_selectors:
                for cls in classes:
                    elements = soup.find_all(tag, class_=re.compile(cls, re.I))
                    for elem in elements:
                        event = self._parse_event_element(elem, config, url)
                        if event:
                            events.append(event)
            
        except Exception as e:
            pass
        
        return events
    
    def _fetch_from_search(self, venue_name: str, location: str, config: dict) -> List[AIFetchedEvent]:
        """Use web search to find events at venue"""
        events = []
        
        # Construct search queries - include various event types
        queries = [
            f'"{venue_name}" {location} evenemang 2026',
            f'"{venue_name}" program kalender',
            f'"{venue_name}" konserter föreställningar',
            f'"{venue_name}" utställning marknad 2026',
            f'"{venue_name}" seminarium föreläsning 2026',
        ]
        
        for query in queries:
            results = self.search_client.search(query, count=5)
            
            for result in results:
                url = result.get('url', '')
                if not url.startswith('http'):
                    continue
                
                # Skip social media and aggregators
                skip_domains = ['facebook.com', 'instagram.com', 'twitter.com', 'youtube.com']
                domain = urlparse(url).netloc.lower()
                if any(skip in domain for skip in skip_domains):
                    continue
                
                # Try to fetch events from result URL
                try:
                    page_events = self._fetch_from_url(url, config)
                    events.extend(page_events)
                except:
                    pass
                
                if events:
                    break
            
            if events:
                break
        
        return events
    
    def _fetch_with_browser(self, url: str, config: dict) -> List[AIFetchedEvent]:
        """Fetch events using browser automation for JS-heavy sites"""
        events = []
        
        if not HAS_PLAYWRIGHT:
            return events
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, wait_until='networkidle', timeout=30000)
                page.wait_for_timeout(2000)
                
                html = page.content()
                browser.close()
                
                if not HAS_BS4:
                    return events
                
                soup = BeautifulSoup(html, 'html.parser')
                
                # Parse events from rendered HTML
                event_selectors = [
                    'article',
                    '[class*="event"]',
                    '[class*="program"]',
                    '[class*="kalender"]',
                    '.event-item',
                    '.program-item'
                ]
                
                for selector in event_selectors:
                    elements = soup.select(selector)
                    for elem in elements:
                        event = self._parse_event_element(elem, config, url)
                        if event:
                            events.append(event)
                
        except Exception as e:
            pass
        
        return events
    
    def _parse_jsonld_event(self, data: dict, config: dict, url: str) -> Optional[AIFetchedEvent]:
        """Parse JSON-LD event data"""
        try:
            name = data.get('name', '')
            start_date = data.get('startDate', '')
            
            if not name or not start_date:
                return None
            
            # Extract date
            if 'T' in start_date:
                date_str = start_date.split('T')[0]
            else:
                date_str = start_date
            
            return AIFetchedEvent(
                title=name,
                date=date_str,
                venue=config.get('name', 'Unknown'),
                location=config.get('location', 'Karlstad'),
                link=data.get('url', url),
                description=data.get('description', '')[:200],
                confidence=0.9
            )
        except:
            return None
    
    def _parse_event_element(self, elem, config: dict, base_url: str) -> Optional[AIFetchedEvent]:
        """Parse event from HTML element"""
        try:
            # Try to find title
            title_elem = elem.find(['h1', 'h2', 'h3', 'h4', 'h5'])
            if not title_elem:
                title_elem = elem.find(class_=re.compile('title|name|rubrik', re.I))
            
            if not title_elem:
                return None
            
            title = title_elem.get_text(strip=True)
            
            # Skip non-events
            skip_patterns = [
                r'^\d{1,2}\s+[A-Za-z]+\s+\d{4}$',
                r'läs mer',
                r'kontakt',
                r'^\s*$'
            ]
            
            for pattern in skip_patterns:
                if re.search(pattern, title, re.IGNORECASE):
                    return None
            
            if len(title) < 5:
                return None
            
            # Try to find date
            date_str = None
            
            # Look for time element
            time_elem = elem.find('time')
            if time_elem and time_elem.get('datetime'):
                date_str = time_elem.get('datetime')[:10]
            
            # Look for date in text
            if not date_str:
                text = elem.get_text()
                date_str = self._parse_date_from_text(text)
            
            if not date_str:
                return None
            
            # Try to find link
            link = None
            link_elem = elem.find('a', href=True)
            if link_elem:
                href = link_elem.get('href', '')
                if href.startswith('http'):
                    link = href
                elif href.startswith('/'):
                    link = urljoin(base_url, href)
            
            return AIFetchedEvent(
                title=title,
                date=date_str,
                venue=config.get('name', 'Unknown'),
                location=config.get('location', 'Karlstad'),
                link=link,
                confidence=0.6
            )
        except:
            return None
    
    def _parse_date_from_text(self, text: str) -> Optional[str]:
        """Parse date from text using various patterns"""
        months = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'maj': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'okt': 10, 'nov': 11, 'dec': 12,
            'januari': 1, 'februari': 2, 'mars': 3, 'april': 4, 'juni': 6,
            'juli': 7, 'augusti': 8, 'september': 9, 'oktober': 10, 'november': 11, 'december': 12
        }
        
        # ISO format: 2026-03-15
        match = re.search(r'(\d{4})-(\d{2})-(\d{2})', text)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        
        # Swedish format: 15 mars 2026
        match = re.search(
            r'(\d{1,2})\s+(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec|januari|februari|mars|april|juni|juli|augusti|september|oktober|november|december)[\.\s,]+(\d{4})',
            text.lower()
        )
        if match:
            day = int(match.group(1))
            month_str = match.group(2)[:3]
            month = months.get(month_str, 1)
            year = int(match.group(3))
            return f"{year}-{month:02d}-{day:02d}"
        
        return None
    
    def _is_valid_event(self, event: AIFetchedEvent) -> bool:
        """Check if event is valid"""
        if not event.title or not event.date or not event.venue:
            return False
        
        # Check year
        try:
            year = int(event.date.split('-')[0])
            if year not in VALID_YEARS:
                return False
        except:
            return False
        
        # Check if future
        try:
            event_date = datetime.strptime(event.date, '%Y-%m-%d').date()
            if event_date < datetime.now().date() - timedelta(days=30):
                return False
        except:
            return False
        
        return True


def fetch_ai_events(venues_config: dict) -> List[Dict]:
    """
    Main entry point for AI event fetching.
    Returns list of event dictionaries ready for the pipeline.
    """
    fetcher = AIEventFetcher(venues_config)
    events = fetcher.fetch_manual_venues()
    
    # Convert to dict format
    return [{
        'title': e.title,
        'date': e.date,
        'venue': e.venue,
        'location': e.location,
        'time': e.time,
        'link': e.link,
        'description': e.description,
        'category': e.category,
        'source': f"AI:{e.venue}",
        'confidence': e.confidence
    } for e in events]


if __name__ == "__main__":
    import yaml
    
    with open(SCRIPT_DIR / "venues.yaml") as f:
        venues = yaml.safe_load(f)
    
    events = fetch_ai_events(venues)
    
    print(f"\n✅ Fetched {len(events)} events via AI")
    
    for e in events[:10]:
        print(f"  • {e['date']}: {e['title'][:50]} ({e['venue']})")