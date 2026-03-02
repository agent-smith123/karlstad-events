#!/usr/bin/env python3
"""
Enhanced Event Scraper for Karlstad Events
Supports multiple sources: APIs, static scraping, and dynamic (Playwright) scraping
"""

import os
import re
import json
import yaml
import hashlib
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict, field
from urllib.parse import urljoin, urlparse
import logging

# Swedish-specific title case exceptions (keep lowercase in titles)
SWEDISH_LOWER_WORDS = {
    'och', 'eller', 'i', 'på', 'med', 'för', 'av', 'till', 'från', 'under',
    'över', 'utan', 'inom', 'om', 'efter', 'före', 'mellan', 'genom',
    'en', 'ett', 'den', 'det', 'de', 'är', 'var', 'är', 'blir', 'får',
    'kan', 'ska', 'vill', 'skall', 'borde', 'måste', 'haft', 'varit',
    'sen', 'så', 'bara', 'än', 'då', 'nu', 'idag', 'igår', 'imorgon'
}

def normalize_title_case(title: str) -> str:
    """
    Convert title to proper title case.
    - Detects ALL CAPS and converts to title case
    - Preserves existing mixed case
    - Handles Swedish characters (å, ä, ö, etc.)
    """
    if not title:
        return title
    
    # Check if title is ALL CAPS (or mostly caps with some lowercase like Swedish chars)
    upper_count = sum(1 for c in title if c.isupper())
    alpha_count = sum(1 for c in title if c.isalpha())
    
    # If less than 30% lowercase letters, treat as ALL CAPS
    if alpha_count > 0 and (alpha_count - upper_count) / alpha_count < 0.3:
        # Convert to title case using Python's title() with Swedish handling
        words = title.split()
        title_cased = []
        
        for i, word in enumerate(words):
            # Clean punctuation from word for checking
            clean_word = re.sub(r'[^\wåäöÅÄÖ]', '', word)
            if not clean_word:
                title_cased.append(word)
                continue
            
            # Preserve original punctuation positions
            prefix = ''
            suffix = ''
            for j, c in enumerate(word):
                if c.isalpha():
                    prefix = word[:j]
                    break
            
            # Find suffix (trailing non-alpha)
            for j in range(len(word) - 1, -1, -1):
                if word[j].isalpha():
                    suffix = word[j+1:]
                    break
            
            clean_word_lower = clean_word.lower()
            
            # Always capitalize first and last word
            if i == 0 or i == len(words) - 1:
                title_cased.append(prefix + clean_word_lower.capitalize() + suffix)
            # Keep short common words lowercase in middle
            elif clean_word_lower in SWEDISH_LOWER_WORDS:
                title_cased.append(prefix + clean_word_lower + suffix)
            else:
                title_cased.append(prefix + clean_word_lower.capitalize() + suffix)
        
        return ' '.join(title_cased)
    
    # Title already has mixed case - return as-is
    return title

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try importing optional dependencies
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    logger.warning("BeautifulSoup not installed. Static scraping disabled.")

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    logger.warning("Playwright not installed. Dynamic scraping disabled.")


@dataclass
class Event:
    """Represents a single event."""
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
    
    def __post_init__(self):
        """Normalize title case on creation."""
        self.title = normalize_title_case(self.title)
    
    def to_markdown(self) -> str:
        """Convert to Hugo markdown format."""
        md = f"""---
title: "{self.title}"
date: {self.date}
venue: "{self.venue}"
location: "{self.location}"""
        if self.time:
            md += f'\ntime: "{self.time}"'
        if self.link:
            md += f'\nlink: "{self.link}"'
        if self.category:
            md += f'\ncategories: ["{self.category}"]'
        else:
            md += '\ncategories: ["Evenemang"]'
        md += f"""
source: "{self.source or 'unknown'}"
---

{self.description or ''}
"""
        return md
    
    def get_id(self) -> str:
        """Generate unique ID for deduplication."""
        key = f"{self.title}|{self.date}|{self.venue}"
        return hashlib.md5(key.encode()).hexdigest()[:12]


class BaseScraper:
    """Base class for all scrapers."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.name = config.get('name', 'Unknown')
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def scrape(self) -> List[Event]:
        """Override in subclasses."""
        raise NotImplementedError


class StaticScraper(BaseScraper):
    """Scraper for static HTML sites using BeautifulSoup."""
    
    def scrape(self) -> List[Event]:
        """Scrape events from static HTML."""
        if not HAS_BS4:
            logger.error("BeautifulSoup required for static scraping")
            return []
        
        events = []
        urls = self.config.get('urls', {})
        
        for url_name, url in urls.items():
            if 'events' in url_name or 'calendar' in url_name:
                try:
                    logger.info(f"Scraping {self.name} from {url}")
                    response = self.session.get(url, timeout=30)
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.content, 'html.parser')
                    venue_events = self._parse_events(soup)
                    events.extend(venue_events)
                    
                except Exception as e:
                    logger.error(f"Error scraping {url}: {e}")
        
        return events
    
    def _parse_events(self, soup: 'BeautifulSoup') -> List[Event]:
        """Parse events from BeautifulSoup object. Override per site."""
        # Generic implementation - override for specific sites
        events = []
        selectors = self.config.get('scraper', {}).get('selectors', {})
        
        event_items = soup.select(selectors.get('event', '.event'))
        
        for item in event_items[:10]:  # Limit to first 10 for safety
            try:
                title_elem = item.select_one(selectors.get('title', 'h2, h3'))
                date_elem = item.select_one(selectors.get('date', '.date, time'))
                link_elem = item.select_one(selectors.get('link', 'a'))
                
                if title_elem and date_elem:
                    event = Event(
                        title=title_elem.get_text(strip=True),
                        date=self._parse_date(date_elem.get_text()),
                        venue=self.name,
                        location=self.config.get('location', 'Karlstad'),
                        link=link_elem.get('href') if link_elem else None,
                        source=self.name
                    )
                    events.append(event)
            except Exception as e:
                logger.debug(f"Error parsing event item: {e}")
        
        return events
    
    def _parse_date(self, date_text: str) -> str:
        """Parse various date formats to ISO format."""
        date_text = date_text.strip().lower()
        
        # Swedish month names
        months = {
            'januari': 1, 'februari': 2, 'mars': 3, 'april': 4,
            'maj': 5, 'juni': 6, 'juli': 7, 'augusti': 8,
            'september': 9, 'oktober': 10, 'november': 11, 'december': 12,
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'sept': 9, 'okt': 10, 'nov': 11, 'dec': 12
        }
        
        # Try various patterns
        patterns = [
            r'(\d{1,2})\s+(\w+)\s+(\d{4})',  # 15 mars 2026
            r'(\d{4})-(\d{2})-(\d{2})',       # 2026-03-15
            r'(\d{2})/(\d{2})/(\d{4})',       # 15/03/2026
        ]
        
        for pattern in patterns:
            match = re.search(pattern, date_text)
            if match:
                try:
                    if pattern == patterns[0]:  # Swedish format
                        day, month_str, year = match.groups()
                        month = months.get(month_str, 1)
                        return f"{year}-{month:02d}-{int(day):02d}"
                    elif pattern == patterns[1]:  # ISO format
                        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                    elif pattern == patterns[2]:  # European format
                        day, month, year = match.groups()
                        return f"{year}-{month}-{day}"
                except:
                    pass
        
        # Default to today + 7 days if parsing fails
        future = datetime.now() + timedelta(days=7)
        return future.strftime('%Y-%m-%d')


class DynamicScraper(BaseScraper):
    """Scraper for JavaScript-heavy sites using Playwright."""
    
    def scrape(self) -> List[Event]:
        """Scrape events using Playwright browser automation."""
        if not HAS_PLAYWRIGHT:
            logger.error("Playwright required for dynamic scraping")
            return []
        
        events = []
        urls = self.config.get('urls', {})
        scraper_config = self.config.get('scraper', {})
        wait_for = scraper_config.get('wait_for', 'body')
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            
            for url_name, url in urls.items():
                if 'events' in url_name or 'calendar' in url_name:
                    try:
                        logger.info(f"Dynamic scraping {self.name} from {url}")
                        page = browser.new_page()
                        page.goto(url, wait_until='networkidle')
                        page.wait_for_selector(wait_for, timeout=10000)
                        
                        content = page.content()
                        soup = BeautifulSoup(content, 'html.parser')
                        venue_events = self._parse_events(soup)
                        events.extend(venue_events)
                        
                        page.close()
                    except Exception as e:
                        logger.error(f"Error dynamic scraping {url}: {e}")
            
            browser.close()
        
        return events
    
    def _parse_events(self, soup: 'BeautifulSoup') -> List[Event]:
        """Parse events - uses same logic as StaticScraper."""
        scraper = StaticScraper(self.config)
        return scraper._parse_events(soup)


class TicketmasterAPIScraper(BaseScraper):
    """Scraper using Ticketmaster Discovery API."""
    
    API_BASE = "https://app.ticketmaster.com/discovery/v2"
    
    def __init__(self, config: Dict, api_key: Optional[str] = None):
        super().__init__(config)
        self.api_key = api_key or os.getenv('TICKETMASTER_API_KEY')
        if not self.api_key:
            logger.warning("No Ticketmaster API key provided")
    
    def scrape(self) -> List[Event]:
        """Fetch events from Ticketmaster API."""
        if not self.api_key:
            logger.error("Ticketmaster API key required")
            return []
        
        events = []
        
        # Search for Karlstad events
        params = {
            'apikey': self.api_key,
            'city': 'Karlstad',
            'countryCode': 'SE',
            'radius': 50,  # km
            'unit': 'km',
            'size': 100,
            'sort': 'date,asc'
        }
        
        try:
            url = f"{self.API_BASE}/events.json"
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            for event_data in data.get('_embedded', {}).get('events', []):
                try:
                    event = self._parse_api_event(event_data)
                    if event:
                        events.append(event)
                except Exception as e:
                    logger.debug(f"Error parsing API event: {e}")
                    
        except Exception as e:
            logger.error(f"Error fetching from Ticketmaster API: {e}")
        
        return events
    
    def _parse_api_event(self, data: Dict) -> Optional[Event]:
        """Parse Ticketmaster API event data."""
        try:
            name = data.get('name', '')
            
            # Get date
            dates = data.get('dates', {}).get('start', {})
            date_str = dates.get('localDate', '')
            time_str = dates.get('localTime', '')
            
            # Get venue
            venues = data.get('_embedded', {}).get('venues', [])
            venue_name = venues[0].get('name', 'Unknown') if venues else 'Unknown'
            city = venues[0].get('city', {}).get('name', 'Karlstad') if venues else 'Karlstad'
            
            # Get URL
            url = data.get('url', '')
            
            # Get category
            classifications = data.get('classifications', [])
            category = classifications[0].get('segment', {}).get('name', 'Evenemang') if classifications else 'Evenemang'
            
            return Event(
                title=name,
                date=date_str,
                venue=venue_name,
                location=city,
                time=time_str[:5] if time_str else None,  # HH:MM
                link=url,
                category=category,
                source='Ticketmaster'
            )
        except Exception as e:
            logger.debug(f"Error parsing event data: {e}")
            return None


class EventAggregator:
    """Main aggregator that coordinates all scrapers."""
    
    def __init__(self, venues_file: Path, api_keys: Optional[Dict] = None):
        self.venues_file = venues_file
        self.api_keys = api_keys or {}
        self.venues = self._load_venues()
        self.all_events: List[Event] = []
        self.seen_ids: set = set()
    
    def _load_venues(self) -> Dict:
        """Load venue configuration from YAML."""
        with open(self.venues_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def run_all(self) -> List[Event]:
        """Run all enabled scrapers."""
        logger.info("Starting event aggregation...")
        
        # Process each tier
        for tier_name in ['tier1_major', 'tier2_cultural', 'tier3_small']:
            tier = self.venues.get(tier_name, {})
            for venue_id, venue_config in tier.items():
                if venue_config.get('active', False):
                    self._scrape_venue(venue_id, venue_config)
        
        # Process API sources
        self._scrape_apis()
        
        logger.info(f"Total unique events found: {len(self.all_events)}")
        return self.all_events
    
    def _scrape_venue(self, venue_id: str, config: Dict):
        """Scrape a single venue based on its configuration."""
        scraper_type = config.get('scraper', {}).get('type', 'static')
        
        try:
            if scraper_type == 'static':
                scraper = StaticScraper(config)
            elif scraper_type == 'dynamic':
                scraper = DynamicScraper(config)
            elif scraper_type == 'manual':
                logger.info(f"Skipping manual venue: {config.get('name')}")
                return
            else:
                logger.warning(f"Unknown scraper type: {scraper_type}")
                return
            
            events = scraper.scrape()
            self._add_events(events)
            logger.info(f"Found {len(events)} events from {config.get('name')}")
            
        except Exception as e:
            logger.error(f"Error scraping {venue_id}: {e}")
    
    def _scrape_apis(self):
        """Scrape API-based sources."""
        # Ticketmaster
        tm_config = self.venues.get('tier4_aggregators', {}).get('ticketmaster', {})
        if tm_config.get('active') and 'ticketmaster' in self.api_keys:
            try:
                scraper = TicketmasterAPIScraper(tm_config, self.api_keys['ticketmaster'])
                events = scraper.scrape()
                self._add_events(events)
                logger.info(f"Found {len(events)} events from Ticketmaster API")
            except Exception as e:
                logger.error(f"Error with Ticketmaster API: {e}")
    
    def _add_events(self, events: List[Event]):
        """Add events with deduplication."""
        for event in events:
            event_id = event.get_id()
            if event_id not in self.seen_ids:
                self.seen_ids.add(event_id)
                self.all_events.append(event)
    
    def save_to_hugo(self, output_dir: Path):
        """Save events as Hugo markdown files."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for event in self.all_events:
            filename = f"{event.date}-{event.get_id()}.md"
            filepath = output_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(event.to_markdown())
        
        logger.info(f"Saved {len(self.all_events)} events to {output_dir}")
    
    def export_to_json(self, output_file: Path):
        """Export all events to JSON."""
        events_data = [asdict(e) for e in self.all_events]
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(events_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Exported to {output_file}")


def main():
    """Main entry point."""
    script_dir = Path(__file__).parent
    project_dir = script_dir.parent
    
    venues_file = script_dir / "venues.yaml"
    content_dir = project_dir / "content" / "events"
    
    # API keys from environment
    api_keys = {
        'ticketmaster': os.getenv('TICKETMASTER_API_KEY')
    }
    
    # Run aggregation
    aggregator = EventAggregator(venues_file, api_keys)
    events = aggregator.run_all()
    
    # Save results
    if events:
        aggregator.save_to_hugo(content_dir)
        aggregator.export_to_json(project_dir / "events.json")
    else:
        logger.warning("No events found")
    
    return events


if __name__ == "__main__":
    main()
