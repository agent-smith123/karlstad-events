#!/usr/bin/env python3
"""
Event Calendar Pipeline - Master Orchestrator
Complete flow: Fetch → Validate → Deduplicate → Quality Gate → Publish

This script orchestrates the entire event calendar workflow:
1. Fetch events from all sources (scripts + AI fallback)
2. Handle pagination completely
3. Validate events (year, links, data quality)
4. Deduplicate across sources
5. Quality gate (broken links, invalid events)
6. Publish to surge.sh
"""

import os
import re
import json
import yaml
import hashlib
import requests
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set, Tuple
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
STATE_FILE = DATA_DIR / "pipeline_state.json"
EVENTS_JSON = DATA_DIR / "events.json"
FAILED_SCRAPES_FILE = DATA_DIR / "failed_scrapes.json"
QUALITY_REPORT_FILE = DATA_DIR / "quality_report.json"

# Current year for validation
CURRENT_YEAR = datetime.now().year
VALID_YEARS = {CURRENT_YEAR, CURRENT_YEAR + 1}  # Only current and next year

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
CONTENT_DIR.mkdir(exist_ok=True)


@dataclass
class Event:
    """Standardized event data structure"""
    title: str
    date: str  # ISO format YYYY-MM-DD
    venue: str
    location: str
    time: Optional[str] = None
    link: Optional[str] = None
    ticketLink: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    soldOut: Optional[bool] = None
    
    def slug(self) -> str:
        """Generate unique slug for deduplication"""
        base = f"{self.date}-{self.venue}-{self.title}"
        return hashlib.md5(base.encode()).hexdigest()[:12]
    
    def to_dict(self) -> dict:
        """Convert to dictionary, excluding None values"""
        return {k: v for k, v in asdict(self).items() if v is not None}
    
    def is_valid_year(self) -> bool:
        """Check if event is for current or next year"""
        try:
            year = int(self.date.split('-')[0])
            return year in VALID_YEARS
        except:
            return False
    
    def is_future(self) -> bool:
        """Check if event is in the future"""
        try:
            event_date = datetime.strptime(self.date, '%Y-%m-%d').date()
            return event_date >= datetime.now().date()
        except:
            return False


class PipelineState:
    """Track pipeline execution state"""
    
    def __init__(self):
        self.state = self._load()
    
    def _load(self) -> dict:
        if STATE_FILE.exists():
            with open(STATE_FILE) as f:
                return json.load(f)
        return {
            "last_run": None,
            "sources_status": {},
            "total_events": 0,
            "failed_sources": []
        }
    
    def save(self):
        with open(STATE_FILE, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def record_source(self, source: str, events_count: int, success: bool, error: str = None):
        self.state["sources_status"][source] = {
            "last_run": datetime.now().isoformat(),
            "events_count": events_count,
            "success": success,
            "error": error
        }
        if not success and source not in self.state["failed_sources"]:
            self.state["failed_sources"].append(source)
        self.save()


class EventFetcher:
    """Fetch events from multiple sources with pagination support"""
    
    def __init__(self, venues_config: dict):
        self.venues = venues_config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self.failed_sources = []
    
    def fetch_all(self) -> List[Event]:
        """Fetch events from all configured sources"""
        all_events = []
        
        # 1. API sources (Ticketmaster web scrape)
        print("\n📡 Phase 1: API Sources + Ticketmaster Web")
        api_events = self._fetch_api_sources()
        all_events.extend(api_events)
        
        # 2. Static scrapers
        print("\n🌐 Phase 2: Static Scrapers")
        static_events = self._fetch_static_sources()
        all_events.extend(static_events)
        
        # 3. Dynamic scrapers (JS-heavy sites) - with timeout
        print("\n⚡ Phase 3: Dynamic Scrapers")
        try:
            dynamic_events = self._fetch_dynamic_sources()
            all_events.extend(dynamic_events)
        except Exception as e:
            print(f"  ⚠️ Dynamic scrapers timed out: {e}")
        
        # 4. AI Fallback - only run if explicitly enabled and with timeout
        ai_enabled = os.getenv('ENABLE_AI_FALLBACK', '').lower() == 'true'
        if ai_enabled:
            print("\n🤖 Phase 4: AI Fallback for Manual Venues (enabled)")
            try:
                ai_events = self._fetch_ai_venues()
                all_events.extend(ai_events)
            except Exception as e:
                print(f"  ⚠️ AI fallback error: {e}")
        else:
            print("\n⏭️  Phase 4: AI Fallback (disabled - set ENABLE_AI_FALLBACK=true)")
        
        # 5. Handle failed sources
        if self.failed_sources:
            print(f"\n🔄 Phase 5: {len(self.failed_sources)} sources failed - logged")
            self._log_failed_sources()
        
        return all_events
    
    def _fetch_api_sources(self) -> List[Event]:
        """Fetch from API sources (Ticketmaster, etc.)"""
        events = []
        
        # Try Ticketmaster API first (if key available)
        api_key = os.getenv('TICKETMASTER_API_KEY')
        if api_key:
            print("  🎫 Using Ticketmaster API...")
            events.extend(self._fetch_ticketmaster(api_key))
        else:
            print("  ⚠️ No TICKETMASTER_API_KEY - skipping Ticketmaster")
            print("     (Set TICKETMASTER_API_KEY env var to enable)")
        
        # Ticketmaster web scraper temporarily disabled (too slow with Playwright)
        # To enable: set ENABLE_TICKETMASTER_WEB=true
        if os.getenv('ENABLE_TICKETMASTER_WEB', '').lower() == 'true':
            print("  🎫 Scraping Ticketmaster venue pages...")
            try:
                tm_events = self._fetch_ticketmaster_web()
                events.extend(tm_events)
            except Exception as e:
                print(f"    ⚠️ Ticketmaster web scrape error: {e}")
        
        return events
    
    def _fetch_ticketmaster_web(self) -> List[Event]:
        """Scrape events from Ticketmaster venue pages with timeout"""
        events = []
        
        try:
            import sys
            sys.path.insert(0, str(SCRIPT_DIR))
            from ticketmaster_scraper import scrape_all_ticketmaster_venues
            
            tm_events = scrape_all_ticketmaster_venues(self.venues)
            
            for e in tm_events:
                events.append(Event(
                    title=e['title'],
                    date=e['date'],
                    venue=e['venue'],
                    location=e['location'],
                    link=e.get('link'),
                    source='Ticketmaster Web',
                    source_url=e.get('link')
                ))
                
        except Exception as e:
            print(f"    ❌ Ticketmaster web scrape failed: {e}")
        
        return events
    
    def _log_failed_sources(self):
        """Log failed sources for later review"""
        failed_log = DATA_DIR / "failed_sources.json"
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "failed": self.failed_sources
        }
        with open(failed_log, 'w') as f:
            json.dump(log_data, f, indent=2)
    
    def _fetch_ticketmaster(self, api_key: str, max_pages: int = 10) -> List[Event]:
        """Fetch from Ticketmaster API with pagination"""
        events = []
        base_url = "https://app.ticketmaster.com/discovery/v2/events.json"
        
        page = 0
        total_events = 0
        
        while page < max_pages:
            params = {
                'apikey': api_key,
                'city': 'Karlstad',
                'countryCode': 'SE',
                'radius': 50,
                'unit': 'km',
                'size': 100,
                'page': page,
                'sort': 'date,asc'
            }
            
            try:
                resp = requests.get(base_url, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                
                page_events = data.get('_embedded', {}).get('events', [])
                if not page_events:
                    break
                
                for item in page_events:
                    event = self._parse_ticketmaster_event(item)
                    if event and event.is_valid_year() and event.is_future():
                        events.append(event)
                
                total_events += len(page_events)
                
                # Check for more pages
                total_pages = data.get('page', {}).get('totalPages', 1)
                if page >= total_pages - 1:
                    break
                
                page += 1
                
            except Exception as e:
                print(f"  ❌ Ticketmaster API error (page {page}): {e}")
                break
        
        print(f"  ✓ Ticketmaster: {len(events)} events from {page + 1} pages")
        return events
    
    def _parse_ticketmaster_event(self, data: dict) -> Optional[Event]:
        """Parse Ticketmaster API event"""
        try:
            dates = data.get('dates', {}).get('start', {})
            date_str = dates.get('localDate')
            if not date_str:
                return None
            
            venues = data.get('_embedded', {}).get('venues', [])
            venue_name = venues[0].get('name', 'Unknown') if venues else 'Unknown'
            city = venues[0].get('city', {}).get('name', 'Karlstad') if venues else 'Karlstad'
            
            classifications = data.get('classifications', [])
            category = 'Evenemang'
            if classifications:
                cat = classifications[0].get('segment', {}).get('name', '')
                if cat:
                    category = cat
            
            return Event(
                title=data.get('name', ''),
                date=date_str,
                venue=venue_name,
                location=city,
                time=dates.get('localTime'),
                link=data.get('url'),
                category=category,
                source='Ticketmaster',
                source_url='https://www.ticketmaster.se'
            )
        except Exception as e:
            return None
    
    def _fetch_static_sources(self) -> List[Event]:
        """Fetch from static HTML sources using AI-based parsing"""
        events = []
        
        try:
            import sys
            sys.path.insert(0, str(SCRIPT_DIR))
            from ai_parser_fetcher import fetch_all_venues_with_ai
            
            # Use AI-based parsing for all venues with URLs
            ai_events = fetch_all_venues_with_ai(self.venues, max_workers=5)
            
            for e in ai_events:
                events.append(Event(
                    title=e['title'],
                    date=e['date'],
                    venue=e['venue'],
                    location=e['location'],
                    link=e.get('link'),
                    source=e.get('source', 'AI Parser')
                ))
            
        except Exception as e:
            print(f"  ❌ AI fetcher error: {e}")
        
        return events
    
    def _scrape_venue(self, venue_key: str, config: dict) -> List[Event]:
        """Scrape a single venue with pagination"""
        events = []
        urls = config.get('urls', {})
        
        for url_type, url in urls.items():
            if not isinstance(url, str) or not url.startswith('http'):
                continue
            
            try:
                # Handle pagination
                max_pages = config.get('scraper', {}).get('max_pages', 5)
                page_events = self._scrape_url_with_pagination(url, config, max_pages)
                events.extend(page_events)
                
                if page_events:
                    print(f"  ✓ {config.get('name', venue_key)}: {len(page_events)} events")
                
            except Exception as e:
                error_msg = str(e)[:100]
                print(f"  ❌ {config.get('name', venue_key)}: {error_msg}")
                self.failed_sources.append({
                    'venue': venue_key,
                    'name': config.get('name', venue_key),
                    'url': url,
                    'error': error_msg
                })
        
        # Filter valid events
        valid_events = [e for e in events if e.is_valid_year() and e.is_future()]
        return valid_events
    
    def _scrape_url_with_pagination(self, url: str, config: dict, max_pages: int = 5) -> List[Event]:
        """Scrape URL with pagination support"""
        events = []
        
        for page in range(max_pages):
            # Try to construct pagination URL
            page_url = url
            if page > 0:
                # Common pagination patterns
                if '?' in url:
                    page_url = f"{url}&page={page + 1}"
                else:
                    page_url = f"{url}?page={page + 1}"
            
            html = self._fetch_html(page_url)
            if not html:
                break
            
            page_events = self._parse_html_events(html, config, url)
            if not page_events:
                break
            
            events.extend(page_events)
        
        return events
    
    def _fetch_html(self, url: str, retries: int = 3) -> Optional[str]:
        """Fetch HTML with retry logic"""
        for attempt in range(retries):
            try:
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
                return resp.text
            except Exception as e:
                if attempt < retries - 1:
                    continue
                return None
        return None
    
    def _parse_html_events(self, html: str, config: dict, base_url: str) -> List[Event]:
        """Parse events from HTML"""
        if not HAS_BS4:
            return []
        
        events = []
        soup = BeautifulSoup(html, 'html.parser')
        
        selectors = config.get('scraper', {}).get('selectors', {})
        event_selector = selectors.get('event', '.event, .activity, article, .post-item')
        
        for elem in soup.select(event_selector):
            event = self._parse_event_element(elem, selectors, base_url, config)
            if event:
                events.append(event)
        
        return events
    
    def _parse_event_element(self, elem, selectors: dict, base_url: str, config: dict) -> Optional[Event]:
        """Parse a single event element"""
        try:
            # Title
            title_sel = selectors.get('title', 'h1, h2, h3, h4, .title')
            title_elem = elem.select_one(title_sel)
            if not title_elem:
                return None
            title = title_elem.get_text(strip=True)
            
            # Skip obvious non-events
            skip_patterns = [
                r'^\d{1,2}\s+[A-Za-z]+\s+\d{4}$',  # Date-only like "15 Apr 2026"
                r'^\d{1,2}/\d{1,2}',  # Date ranges like "20/6-5/9"
                r'fakturor',  # Invoice-related
                r'avstängning',  # Road closures
                r'driftmeddelande',  # Service announcements
                r'lediga jobb',  # Job postings
            ]
            for pattern in skip_patterns:
                if re.search(pattern, title, re.IGNORECASE):
                    return None
            
            # Skip very short titles (likely noise)
            if len(title) < 5:
                return None
            
            # Date
            date_sel = selectors.get('date', '.date, time, .datetime')
            date_elem = elem.select_one(date_sel)
            date_str = None
            if date_elem:
                date_str = self._parse_date(date_elem.get_text(strip=True))
            
            if not date_str:
                # Try to find date in element text
                date_str = self._parse_date(elem.get_text())
            
            if not date_str:
                return None
            
            # Link
            link = None
            link_sel = selectors.get('link', 'a[href]')
            link_elem = elem.select_one(link_sel)
            if link_elem:
                href = link_elem.get('href', '')
                link = urljoin(base_url, href) if href else None
            
            return Event(
                title=title,
                date=date_str,
                venue=config.get('name', 'Unknown'),
                location=config.get('location', 'Karlstad'),
                link=link,
                source=config.get('name', 'Unknown'),
                source_url=base_url
            )
        except:
            return None
    
    def _parse_date(self, text: str) -> Optional[str]:
        """Parse date from various formats"""
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
        
        # Swedish format: 15 mars 2026 or 15 mars, 2026
        match = re.search(r'(\d{1,2})\s+(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec|januari|februari|mars|april|juni|juli|augusti|september|oktober|november|december)[\.\s,]+(\d{4})', text.lower())
        if match:
            day = int(match.group(1))
            month_str = match.group(2)[:3]
            month = months.get(month_str, 1)
            year = int(match.group(3))
            return f"{year}-{month:02d}-{day:02d}"
        
        return None
    
    def _fetch_ai_venues(self) -> List[Event]:
        """Fetch events from venues marked as manual with AI fallback using parallel processing"""
        events = []
        
        try:
            import sys
            sys.path.insert(0, str(SCRIPT_DIR))
            from parallel_ai_fetcher import parallel_fetch_venues
            
            # Fetch events in parallel (5 workers, 30s timeout per venue)
            ai_events = parallel_fetch_venues(self.venues, max_workers=5, timeout=30)
            
            # Convert to Event format
            for e in ai_events:
                events.append(Event(
                    title=e['title'],
                    date=e['date'],
                    venue=e['venue'],
                    location=e['location'],
                    link=e.get('link'),
                    description=e.get('description'),
                    category=e.get('category'),
                    source=e.get('source', 'AI Fallback')
                ))
            
            print(f"  ✓ AI Fallback: {len(events)} events from parallel fetch")
            
        except Exception as e:
            print(f"  ❌ AI Fallback error: {e}")
            import traceback
            traceback.print_exc()
        
        return events
    
    def _fetch_dynamic_sources(self) -> List[Event]:
        """Fetch from JS-heavy sources using Playwright"""
        events = []
        
        if not HAS_PLAYWRIGHT:
            print("  ⚠️ Playwright not available - skipping dynamic sources")
            return events
        
        # Find venues that need dynamic scraping
        for tier in ['tier1_major', 'tier2_cultural', 'tier3_small']:
            tier_venues = self.venues.get(tier, {})
            for venue_key, config in tier_venues.items():
                if not config.get('active', False):
                    continue
                
                scraper_type = config.get('scraper', {}).get('type', 'static')
                if scraper_type != 'dynamic':
                    continue
                
                venue_events = self._scrape_dynamic(venue_key, config)
                events.extend(venue_events)
        
        return events
    
    def _scrape_dynamic(self, venue_key: str, config: dict) -> List[Event]:
        """Scrape JS-heavy site with Playwright"""
        events = []
        urls = config.get('urls', {})
        
        for url_type, url in urls.items():
            if not isinstance(url, str) or not url.startswith('http'):
                continue
            
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.goto(url, wait_until='networkidle', timeout=30000)
                    page.wait_for_timeout(2000)
                    
                    html = page.content()
                    browser.close()
                    
                    if html:
                        page_events = self._parse_html_events(html, config, url)
                        events.extend(page_events)
                        
                        if page_events:
                            print(f"  ✓ {config.get('name', venue_key)} (dynamic): {len(page_events)} events")
            
            except Exception as e:
                error_msg = str(e)[:100]
                print(f"  ❌ {config.get('name', venue_key)} (dynamic): {error_msg}")
                self.failed_sources.append({
                    'venue': venue_key,
                    'name': config.get('name', venue_key),
                    'url': url,
                    'error': error_msg
                })
        
        # Filter valid events
        valid_events = [e for e in events if e.is_valid_year() and e.is_future()]
        return valid_events
    
    def _ai_fallback_fetch(self) -> List[Event]:
        """Use AI agent to fetch events from failed sources"""
        events = []
        
        # Log failed sources for AI
        with open(FAILED_SCRAPES_FILE, 'w') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "failed": self.failed_sources,
                "instructions": "Use AI agent to fetch events from these sources"
            }, f, indent=2)
        
        print(f"  📝 Logged {len(self.failed_sources)} failed sources to {FAILED_SCRAPES_FILE}")
        print("  💡 Run AI agent to fetch events from these sources manually")
        
        return events


class EventDeduplicator:
    """Deduplicate events across sources"""
    
    # Aggregator sources that shouldn't be used as venue names
    AGGREGATOR_SOURCES = {'Ticketmaster', 'Tickster', 'Stadsevent', 'Karlstad.com', 
                          'Ticketmaster Web', 'Nöje.se', 'Visit Värmland'}
    
    def deduplicate(self, events: List[Event]) -> List[Event]:
        """Remove duplicate events, preferring venue-specific over aggregator sources
        
        Uses case-insensitive comparison for titles and venues
        """
        # Group events by (date, normalized_title, normalized_venue)
        from collections import defaultdict
        groups = defaultdict(list)
        
        for event in events:
            # Normalize title and venue for grouping (case-insensitive)
            norm_title = self._normalize_title(event.title)
            norm_venue = self._normalize_venue(event.venue)
            key = (event.date, norm_title, norm_venue)
            groups[key].append(event)
        
        unique_events = []
        duplicates_found = 0
        
        for key, group in groups.items():
            if len(group) == 1:
                unique_events.append(group[0])
            else:
                # Multiple events with same date + title + venue - pick the best one
                best = self._pick_best_event(group)
                unique_events.append(best)
                duplicates_found += len(group) - 1
        
        print(f"\n🔄 Deduplication: {duplicates_found} duplicates removed, {len(unique_events)} unique events")
        return unique_events
    
    def _normalize_title(self, title: str) -> str:
        """Normalize title for comparison (case-insensitive)"""
        t = title.lower().strip()
        # Remove common variations
        t = re.sub(r'\s+', ' ', t)
        t = re.sub(r'[-–—]', '-', t)
        return t
    
    def _normalize_venue(self, venue: str) -> str:
        """Normalize venue name for comparison (case-insensitive)"""
        v = venue.lower().strip()
        # Common venue name variations
        v = re.sub(r'\s+', ' ', v)
        # Handle common abbreviations/variations
        v = v.replace('wermlands', 'wermland')
        v = v.replace('operan', 'opera')
        return v
    
    def _pick_best_event(self, events: List[Event]) -> Event:
        """Pick the best event from a group of duplicates
        
        Prefers:
        1. Non-aggregator venues (actual venue name)
        2. Events with more complete info (link, time, etc.)
        """
        # Score each event
        scored = []
        for e in events:
            score = 0
            
            # Prefer non-aggregator venues
            if e.venue not in self.AGGREGATOR_SOURCES:
                score += 100
            
            # Prefer events with links
            if e.link:
                score += 10
            
            # Prefer events with time
            if e.time:
                score += 5
            
            # Prefer events with description
            if e.description:
                score += 3
            
            scored.append((score, e))
        
        # Sort by score descending, return best
        scored.sort(key=lambda x: -x[0])
        return scored[0][1]


class QualityGate:
    """Validate events before publishing"""
    
    def __init__(self):
        self.issues = []
        self.warnings = []
    
    def validate_all(self, events: List[Event]) -> Tuple[List[Event], List[Event]]:
        """Validate all events, return (valid, invalid)"""
        valid = []
        invalid = []
        
        print("\n🔒 Quality Gate")
        print("=" * 50)
        
        for event in events:
            issues = self._validate_event(event)
            if issues:
                invalid.append((event, issues))
                self.issues.extend(issues)
            else:
                valid.append(event)
        
        # Verify links
        print("  🔗 Verifying links...")
        link_issues = self._verify_links(valid)
        
        print(f"  ✅ Valid events: {len(valid)}")
        print(f"  ❌ Invalid events: {len(invalid)}")
        print(f"  ⚠️  Warnings: {len(self.warnings)}")
        
        return valid, invalid
    
    def _validate_event(self, event: Event) -> List[dict]:
        """Validate a single event"""
        issues = []
        
        # Check required fields
        if not event.title:
            issues.append({'type': 'missing_title', 'severity': 'high'})
        
        if not event.date:
            issues.append({'type': 'missing_date', 'severity': 'high'})
        
        if not event.venue:
            issues.append({'type': 'missing_venue', 'severity': 'medium'})
        
        # Check year validity
        if not event.is_valid_year():
            issues.append({'type': 'invalid_year', 'severity': 'high', 'detail': f"Year: {event.date[:4]}"})
        
        # Check if event is in the past
        if not event.is_future():
            issues.append({'type': 'past_event', 'severity': 'medium'})
        
        # Check for ALL CAPS titles
        if event.title and event.title.isupper() and len(event.title) > 10:
            self.warnings.append({'event': event.title, 'type': 'all_caps_title'})
        
        return issues
    
    def _verify_links(self, events: List[Event]) -> List[dict]:
        """Verify event links are valid"""
        issues = []
        checked_urls = set()
        
        # Sites that block automated requests
        skip_domains = ['ticketmaster.se', 'ticketmaster.com', 'facebook.com', 'fb.me', 'tickster.com']
        
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        for event in events:
            link = event.link or event.ticketLink
            if not link:
                continue
            
            if link in checked_urls:
                continue
            checked_urls.add(link)
            
            domain = urlparse(link).netloc.lower()
            if any(skip in domain for skip in skip_domains):
                continue
            
            try:
                resp = session.head(link, timeout=10, allow_redirects=True)
                if resp.status_code >= 400:
                    issues.append({
                        'event': event.title,
                        'url': link,
                        'status': resp.status_code
                    })
            except Exception as e:
                issues.append({
                    'event': event.title,
                    'url': link,
                    'error': str(e)[:50]
                })
        
        if issues:
            print(f"    ⚠️  Found {len(issues)} link issues")
        
        return issues
    
    def save_report(self):
        """Save quality report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'issues': self.issues,
            'warnings': self.warnings,
            'summary': {
                'total_issues': len(self.issues),
                'total_warnings': len(self.warnings)
            }
        }
        
        with open(QUALITY_REPORT_FILE, 'w') as f:
            json.dump(report, f, indent=2)


class EventPublisher:
    """Publish events to files and surge.sh"""
    
    def __init__(self):
        self.content_dir = CONTENT_DIR
        self.data_dir = DATA_DIR
    
    def publish(self, events: List[Event]) -> dict:
        """Publish events to markdown files and JSON"""
        print("\n📝 Publishing Events")
        print("=" * 50)
        
        # Write JSON
        events_data = [e.to_dict() for e in events]
        with open(EVENTS_JSON, 'w') as f:
            json.dump(events_data, f, indent=2, ensure_ascii=False)
        print(f"  ✓ Wrote {len(events)} events to events.json")
        
        # Get list of new slugs
        new_slugs = {event.slug() for event in events}
        
        # Clear old markdown files that are no longer in events.json
        cleared = 0
        for md_file in self.content_dir.glob("*.md"):
            if md_file.name == "_index.md":
                continue
            slug = md_file.stem
            if slug not in new_slugs:
                md_file.unlink()
                cleared += 1
        
        if cleared > 0:
            print(f"  🗑️  Removed {cleared} old markdown files")
        
        # Write markdown files (overwrite existing to ensure fresh content)
        written = 0
        for event in events:
            md_file = self.content_dir / f"{event.slug()}.md"
            with open(md_file, 'w') as f:
                f.write(self._to_markdown(event))
            written += 1
        
        print(f"  ✓ Wrote {written} markdown files")
        
        return {
            'json_events': len(events),
            'markdown_files': written,
            'cleared_old': cleared
        }
    
    def _to_markdown(self, event: Event) -> str:
        """Convert event to Hugo markdown"""
        # Escape quotes in YAML values
        def yaml_escape(s: str) -> str:
            if not s:
                return ""
            # Escape backslashes and double quotes
            s = s.replace('\\', '\\\\').replace('"', '\\"')
            return s
        
        md = f"""---
title: "{yaml_escape(event.title)}"
date: {event.date}
venue: "{yaml_escape(event.venue)}"
location: "{yaml_escape(event.location)}"
"""
        if event.time:
            md += f'time: "{yaml_escape(event.time)}"\n'
        if event.link:
            md += f'link: "{yaml_escape(event.link)}"\n'
        if event.ticketLink:
            md += f'ticketLink: "{yaml_escape(event.ticketLink)}"\n'
        if event.category:
            md += f'categories: ["{yaml_escape(event.category)}"]\n'
        if event.source:
            md += f'source: "{yaml_escape(event.source)}"\n'
        if event.soldOut:
            md += f'soldOut: true\n'
        md += "---\n\n"
        if event.description:
            md += f"{yaml_escape(event.description)}\n"
        return md
    
    def deploy_to_surge(self) -> bool:
        """Deploy to surge.sh"""
        print("\n🚀 Deploying to Surge.sh")
        print("=" * 50)
        
        try:
            # Build Hugo site
            print("  🏗️  Building Hugo site...")
            result = subprocess.run(
                ['hugo', '--buildFuture', '--minify'],
                cwd=PROJECT_DIR,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print(f"  ❌ Hugo build failed: {result.stderr}")
                return False
            
            # Deploy to surge
            print("  📤 Deploying...")
            surge_result = subprocess.run(
                ['surge', './public', 'karlstad-events.surge.sh'],
                cwd=PROJECT_DIR,
                capture_output=True,
                text=True
            )
            
            if surge_result.returncode != 0:
                print(f"  ⚠️  Surge deploy: {surge_result.stdout}")
                return False
            
            print("  ✅ Deployed to https://karlstad-events.surge.sh")
            return True
            
        except Exception as e:
            print(f"  ❌ Deploy failed: {e}")
            return False


def main():
    """Main pipeline execution"""
    print("=" * 60)
    print("🎯 Karlstad Events Pipeline")
    print("=" * 60)
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # Load venues config
    with open(VENUES_FILE) as f:
        venues = yaml.safe_load(f)
    
    # Initialize state
    state = PipelineState()
    
    try:
        # Phase 1: Fetch events
        print("\n📥 Phase 1: Fetching Events")
        fetcher = EventFetcher(venues)
        all_events = fetcher.fetch_all()
        print(f"\n📊 Total fetched: {len(all_events)} events")
        
        # Phase 2: Deduplicate
        print("\n🔄 Phase 2: Deduplication")
        deduplicator = EventDeduplicator()
        unique_events = deduplicator.deduplicate(all_events)
        
        # Phase 3: Quality Gate
        print("\n🔒 Phase 3: Quality Gate")
        quality = QualityGate()
        valid_events, invalid_events = quality.validate_all(unique_events)
        quality.save_report()
        
        # Phase 4: Publish
        print("\n📤 Phase 4: Publishing")
        publisher = EventPublisher()
        publish_result = publisher.publish(valid_events)
        
        # Phase 5: Deploy
        deploy_success = publisher.deploy_to_surge()
        
        # Update state
        state.state["last_run"] = datetime.now().isoformat()
        state.state["total_events"] = len(valid_events)
        state.save()
        
        # Summary
        print("\n" + "=" * 60)
        print("✅ Pipeline Complete!")
        print(f"   Fetched: {len(all_events)} events")
        print(f"   After dedup: {len(unique_events)} events")
        print(f"   Valid: {len(valid_events)} events")
        print(f"   Invalid: {len(invalid_events)} events")
        print(f"   Deploy: {'✅ Success' if deploy_success else '❌ Failed'}")
        print("=" * 60)
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())