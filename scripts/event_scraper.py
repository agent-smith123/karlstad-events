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
        max_pages = self.config.get('scraper', {}).get('max_pages', 10)
        
        for url_name, url in urls.items():
            if 'events' in url_name or 'calendar' in url_name:
                try:
                    logger.info(f"Scraping {self.name} from {url}")
                    
                    # Handle pagination - scrape multiple pages
                    page_num = 1
                    while url and page_num <= max_pages:
                        response = self.session.get(url, timeout=30)
                        response.raise_for_status()
                        
                        soup = BeautifulSoup(response.content, 'html.parser')
                        venue_events = self._parse_events(soup)
                        events.extend(venue_events)
                        
                        logger.info(f"  Page {page_num}: found {len(venue_events)} events")
                        
                        # Check for next page
                        url = self._find_next_page(soup, url)
                        page_num += 1
                        
                        if not url:
                            break
                    
                except Exception as e:
                    logger.error(f"Error scraping {url}: {e}")
        
        return events
    
    def _find_next_page(self, soup: 'BeautifulSoup', current_url: str) -> Optional[str]:
        """Find next page URL from pagination links."""
        # Common pagination selectors
        pagination_selectors = [
            'a.next',
            'a[rel="next"]',
            '.pagination a.next',
            '.pager a.next',
            'a.page-next',
            '.pagination a:contains("Nästa")',
            'a:contains("Nästa")',
            'a:contains("Next")',
            'a[aria-label="Next"]',
            'button[aria-label="Next"]',
            '.pagination li.next a',
            'ul.pagination a:last-child:not([href="#"])',
        ]
        
        # Also check for ?page=X or ?p=X patterns
        parsed = urllib.parse.urlparse(current_url)
        
        for selector in pagination_selectors:
            next_link = soup.select_one(selector)
            if next_link and next_link.get('href'):
                href = next_link.get('href')
                if href.startswith('http'):
                    return href
                elif href.startswith('/'):
                    # Relative URL
                    base = f"{parsed.scheme}://{parsed.netloc}"
                    return base + href
                else:
                    return urllib.parse.urljoin(current_url, href)
        
        # Try to construct next page from query params
        query = dict(urllib.parse.parse_qsl(parsed.query))
        if 'page' in query:
            query['page'] = str(int(query['page']) + 1)
            new_query = urllib.parse.urlencode(query)
            return urllib.parse.urlunparse((
                parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment
            ))
        elif 'p' in query:
            query['p'] = str(int(query['p']) + 1)
            new_query = urllib.parse.urlencode(query)
            return urllib.parse.urlunparse((
                parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment
            ))
        
        return None
    
    def _parse_events(self, soup: 'BeautifulSoup') -> List[Event]:
        """Parse events from BeautifulSoup object. Override per site."""
        events = []
        selectors = self.config.get('scraper', {}).get('selectors', {})
        
        # Get custom selectors or use defaults
        event_selector = selectors.get('event', '.event')
        title_selector = selectors.get('title', 'h2, h3')
        date_selector = selectors.get('date', '.date, time')
        link_selector = selectors.get('link', 'a')
        category_selector = selectors.get('category', None)
        
        event_items = soup.select(event_selector)
        
        for item in event_items:
            try:
                title_elem = item.select_one(title_selector)
                date_elems = item.select(date_selector)
                link_elem = item.select_one(link_selector)
                category_elem = item.select_one(category_selector) if category_selector else None
                
                if title_elem and date_elems:
                    # Get the first date (for date ranges, use the first date)
                    first_date_elem = date_elems[0]
                    
                    # Try to get datetime attribute first, fallback to text content
                    date_value = first_date_elem.get('datetime', '').strip()
                    if not date_value:
                        date_value = first_date_elem.get_text(strip=True)
                    
                    # Get category if available
                    category = category_elem.get_text(strip=True) if category_elem else None
                    
                    # Get link - make it absolute if needed
                    link = link_elem.get('href', '') if link_elem else None
                    if link and link.startswith('/'):
                        link = f"https://www.wermlandopera.com{link}"
                    
                    # Get venue from config, fallback to name
                    venue = selectors.get('venue', self.name)
                    
                    event = Event(
                        title=title_elem.get_text(strip=True),
                        date=self._parse_date(date_value),
                        venue=venue,
                        location=self.config.get('location', 'Karlstad'),
                        link=link,
                        category=category,
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


class TicketmasterHTMLScraper(BaseScraper):
    """Scrape Ticketmaster search results pages directly (no API key needed)."""
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'sv-SE,sv;q=0.9,en;q=0.8',
        })
    
    def scrape(self) -> List[Event]:
        """Scrape events from Ticketmaster search pages."""
        events = []
        
        # Search URLs for different locations in Värmland
        search_urls = [
            ('karlstad', 'https://www.ticketmaster.se/discover/karlstad'),
            ('kristinehamn', 'https://www.ticketmaster.se/discover/kristinehamn'),
            ('arvika', 'https://www.ticketmaster.se/discover/arvika'),
            ('saffle', 'https://www.ticketmaster.se/discover/saffle'),
        ]
        
        for location, url in search_urls:
            try:
                logger.info(f"Scraping Ticketmaster: {location}")
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                page_events = self._parse_search_results(soup, location)
                events.extend(page_events)
                
            except Exception as e:
                logger.debug(f"Error scraping {location}: {e}")
        
        return events
    
    def _parse_search_results(self, soup: 'BeautifulSoup', default_location: str) -> List[Event]:
        """Parse events from Ticketmaster search results HTML."""
        events = []
        
        # Look for event cards - Ticketmaster uses various structures
        # Try multiple selectors
        event_selectors = [
            '[data-event-id]',
            '.event-listing',
            '.event-card',
            '.search-result',
            'article[data-component="event-card"]',
        ]
        
        event_items = []
        for selector in event_selectors:
            event_items = soup.select(selector)
            if event_items:
                break
        
        for item in event_items[:50]:  # Limit to 50 events
            try:
                # Extract title
                title_elem = (
                    item.select_one('h2, h3, .event-title, [data-test="event-title"], .name') or
                    item.select_one('a') if item.name == 'a' else None
                )
                title = title_elem.get_text(strip=True) if title_elem else ''
                
                if not title:
                    # Try getting title from link
                    link = item.select_one('a[href*="/event/"]')
                    if link:
                        title = link.get_text(strip=True) or link.get('aria-label', '')
                
                if not title:
                    continue
                
                # Extract date
                date_elem = (
                    item.select_one('.date, .event-date, [data-test="date"], time') or
                    item.select_one('[class*="date"]')
                )
                date_text = date_elem.get_text(strip=True) if date_elem else ''
                date_str = self._parse_date(date_text)
                
                # Extract time
                time_elem = item.select_one('.time, [data-test="time"]')
                time_str = time_elem.get_text(strip=True) if time_elem else None
                
                # Extract venue
                venue_elem = (
                    item.select_one('.venue, .event-venue, [data-test="venue"], [class*="venue"]') or
                    item.select_one('[class*="location"]')
                )
                venue = venue_elem.get_text(strip=True) if venue_elem else 'Ticketmaster'
                
                # Extract link
                link_elem = item.select_one('a[href*="/event/"]')
                link = link_elem.get('href', '') if link_elem else ''
                if link and not link.startswith('http'):
                    link = 'https://www.ticketmaster.se' + link
                
                if date_str and title:
                    events.append(Event(
                        title=title,
                        date=date_str,
                        venue=venue,
                        location=default_location.title(),
                        time=time_str,
                        link=link,
                        source='Ticketmaster'
                    ))
                    
            except Exception as e:
                logger.debug(f"Error parsing event item: {e}")
        
        # Fallback: try to extract from JSON-LD (primary method for Ticketmaster)
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                import json
                data = json.loads(script.string)
                # Handle both array and single object
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get('@type') == 'Event':
                            event = self._parse_jsonld_event(item, default_location)
                            if event:
                                events.append(event)
                elif isinstance(data, dict) and data.get('@type') == 'Event':
                    event = self._parse_jsonld_event(data, default_location)
                    if event:
                        events.append(event)
            except:
                pass
        
        return events
    
    def _parse_jsonld_event(self, data: Dict, default_location: str) -> Optional[Event]:
        """Parse event from JSON-LD structured data."""
        try:
            name = data.get('name', '')
            start_date = data.get('startDate', '')
            
            # Parse date
            date_str = ''
            if start_date:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    date_str = dt.strftime('%Y-%m-%d')
                except:
                    pass
            
            # Parse time
            time_str = None
            if start_date and 'T' in start_date:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    time_str = dt.strftime('%H:%M')
                except:
                    pass
            
            # Get venue
            location = data.get('location', {})
            if isinstance(location, dict):
                venue = location.get('name', 'Ticketmaster')
            else:
                venue = str(location) if location else 'Ticketmaster'
            
            # Get URL
            url = data.get('url', '')
            
            if date_str and name:
                return Event(
                    title=name,
                    date=date_str,
                    venue=venue,
                    location=default_location.title(),
                    time=time_str,
                    link=url,
                    source='Ticketmaster'
                )
        except Exception as e:
            logger.debug(f"Error parsing JSON-LD: {e}")
        
        return None
    
    def _parse_date(self, date_text: str) -> str:
        """Parse date from various formats."""
        date_text = date_text.strip().lower()
        
        # Swedish months
        months = {
            'januari': 1, 'februari': 2, 'mars': 3, 'april': 4,
            'maj': 5, 'juni': 6, 'juli': 7, 'augusti': 8,
            'september': 9, 'oktober': 10, 'november': 11, 'december': 12
        }
        
        # Try Swedish format: 15 mars 2026
        for month_sv, month_num in months.items():
            if month_sv in date_text:
                match = re.search(r'(\d{1,2})\s+' + month_sv + r'\s+(\d{4})', date_text)
                if match:
                    return f"{match.group(2)}-{month_num:02d}-{int(match.group(1)):02d}"
                match = re.search(r'(\d{1,2})\s+' + month_sv, date_text)
                if match:
                    return f"{datetime.now().year}-{month_num:02d}-{int(match.group(1)):02d}"
        
        # ISO format
        match = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_text)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        
        return ''


class AIFallbackScraper(BaseScraper):
    """
    AI-powered fallback scraper for venues with no structured data.
    Uses web search to find upcoming events at venues.
    """
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.venue_name = config.get('name', 'Unknown')
        self.venue_location = config.get('location', 'Karlstad')
        self.venue_urls = config.get('urls', {})
    
    def scrape(self) -> List[Event]:
        """Use web search to find events at this venue."""
        events = []
        
        # Build search query
        query = f"{self.venue_name} {self.venue_location} evenemang 2026"
        
        try:
            # Use a simple web search approach
            search_url = f"https://www.google.com/search?q={requests.utils.quote(query)}&hl=sv"
            
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            
            response = self.session.get(search_url, timeout=15)
            
            if response.status_code == 200:
                # Parse results to find event-like content
                events = self._parse_search_results(response.text)
                
        except Exception as e:
            logger.debug(f"AI fallback search failed for {self.venue_name}: {e}")
        
        return events
    
    def _parse_search_results(self, html: str) -> List[Event]:
        """Parse search results to find event information."""
        events = []
        
        # Simple extraction - look for patterns that indicate events
        # Look for dates in Swedish format
        date_pattern = r'(\d{1,2})\s+(januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)\s+(\d{4})'
        
        matches = re.finditer(date_pattern, html, re.IGNORECASE)
        
        months = {
            'januari': 1, 'februari': 2, 'mars': 3, 'april': 4,
            'maj': 5, 'juni': 6, 'juli': 7, 'augusti': 8,
            'september': 9, 'oktober': 10, 'november': 11, 'december': 12
        }
        
        for match in matches[:10]:  # Limit results
            try:
                day = int(match.group(1))
                month_name = match.group(2).lower()
                year = int(match.group(3))
                
                if year >= 2026 and month_name in months:
                    date_str = f"{year}-{months[month_name]:02d}-{day:02d}"
                    
                    events.append(Event(
                        title=f"Event at {self.venue_name}",
                        date=date_str,
                        venue=self.venue_name,
                        location=self.venue_location,
                        source='AI Search'
                    ))
            except:
                continue
        
        return events


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
        for tier_name in ['tier1_major', 'tier2_cultural', 'tier3_small', 'tier4_aggregators', 'tier5_municipal']:
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
            elif scraper_type == 'ticketmaster_html':
                scraper = TicketmasterHTMLScraper(config)
            elif scraper_type == 'manual':
                # Check if AI fallback is enabled
                if config.get('scraper', {}).get('fallback') == 'ai':
                    try:
                        scraper = AIFallbackScraper(config)
                        events = scraper.scrape()
                        self._add_events(events)
                        logger.info(f"Found {len(events)} AI events from {config.get('name')}")
                    except Exception as e:
                        logger.debug(f"AI fallback failed for {config.get('name')}: {e}")
                else:
                    logger.info(f"Skipping manual venue: {config.get('name')}")
                return
            else:
                logger.warning(f"Unknown scraper type: {scraper_type}")
                return
            
            events = scraper.scrape()
            # Filter by venue if specified
            venue_filter = config.get('scraper', {}).get('venue_filter')
            if venue_filter:
                events = [e for e in events if venue_filter.upper() in e.venue.upper()]
            
            self._add_events(events)
            logger.info(f"Found {len(events)} events from {config.get('name')}")
            
        except Exception as e:
            logger.error(f"Error scraping {venue_id}: {e}")
    
    def _scrape_apis(self):
        """Scrape API-based sources."""
        # Ticketmaster
        tm_config = self.venues.get('tier4_aggregators', {}).get('ticketmaster', {})
        
        if tm_config.get('active'):
            # Try API first if key is available
            if 'ticketmaster' in self.api_keys and self.api_keys['ticketmaster']:
                try:
                    scraper = TicketmasterAPIScraper(tm_config, self.api_keys['ticketmaster'])
                    events = scraper.scrape()
                    self._add_events(events)
                    logger.info(f"Found {len(events)} events from Ticketmaster API")
                except Exception as e:
                    logger.error(f"Error with Ticketmaster API: {e}")
                    # Fall back to HTML scraping
                    self._scrape_ticketmaster_html()
            else:
                # No API key - use HTML scraping
                logger.info("No Ticketmaster API key - using HTML scraper")
                self._scrape_ticketmaster_html()
    
    def _scrape_ticketmaster_html(self):
        """Scrape Ticketmaster search pages directly."""
        try:
            config = {
                'name': 'Ticketmaster HTML',
                'location': 'Värmland',
                'urls': {}
            }
            scraper = TicketmasterHTMLScraper(config)
            events = scraper.scrape()
            self._add_events(events)
            logger.info(f"Found {len(events)} events from Ticketmaster HTML")
        except Exception as e:
            logger.error(f"Error with Ticketmaster HTML scraping: {e}")
    
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
