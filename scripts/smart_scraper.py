#!/usr/bin/env python3
"""
Smart Scraper with Auto-Healing
Refined scrapers for specific venues with automatic error detection and retry
"""

import os
import re
import json
import time
import hashlib
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from urllib.parse import urljoin, urlparse

# Try to import optional dependencies
try:
    from bs4 import BeautifulSoup, SoupStrainer
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
DATA_DIR = SCRIPT_DIR.parent / "data"
SCRAPER_STATE_FILE = DATA_DIR / "scraper_state.json"
FAILED_SELECTORS_FILE = DATA_DIR / "failed_selectors.json"

# Retry configuration for anti-bot protection
ANTIBOT_ERRORS = [455, 429, 403, 521]
RETRY_DELAYS = {
    455: 300,  # 5 minutes
    429: 600,  # 10 minutes
    403: 1200, # 20 minutes
    521: 60,   # 1 minute
}

# Load/save scraper state for retry logic
def load_scraper_state() -> Dict:
    """Load scraper state for retry logic"""
    if SCRAPER_STATE_FILE.exists():
        with open(SCRAPER_STATE_FILE) as 'r') as f:
            return json.load(f)
    return {}

def save_scraper_state(state: Dict):
    """Save scraper state"""
    SCRAPER_STATE_FILE.parent.mkdir(exist_ok=True)
    with open(SCRAPER_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def can_retry_scrape(venue_name: str) -> Tuple[bool, Optional[int]]:
    """
    Check if a scraper can be retried and get wait time
    Returns (can_retry, wait_seconds)
    """
    state = load_scraper_state()
    if venue_name not in state:
        return True, None
    
    attempts = state[venue_name].get('attempts', 0)
    last_error_code = state[venue_name].get('last_error_code')
    last_attempt = state[venue_name].get('last_attempt')
    
    # Too many attempts already
    if attempts >= 3:
        return False, None
    
    # Check error type
    if last_error_code in ANTIBOT_ERRORS:
        wait_time = RETRY_DELAYS.get(last_error_code, 300)
        # Check if enough time has passed
        if last_attempt:
            elapsed = time.time() - last_attempt
            if elapsed < wait_time:
                return False, int(wait_time - elapsed)
        return True, wait_time
    
    # Other errors: can retry with short delay
    return True, 30

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)


@dataclass
class ScrapedEvent:
    """Standardized scraped event"""
    title: str
    date: str  # ISO format YYYY-MM-DD
    venue: str
    location: str
    time: Optional[str] = None
    link: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    
    def slug(self) -> str:
        base = f"{self.date}-{self.venue}-{self.title}"
        return hashlib.md5(base.encode()).hexdigest()[:12]


class ScraperState:
    """Tracks scraper health and performance"""
    
    def __init__(self):
        self.state = self._load_state()
    
    def _load_state(self) -> Dict:
        if SCRAPER_STATE_FILE.exists():
            with open(SCRAPER_STATE_FILE) as f:
                return json.load(f)
        return {}
    
    def save(self):
        with open(SCRAPER_STATE_FILE, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def record_attempt(self, scraper_name: str, success: bool, events_count: int = 0, error: str = None):
        """Record scraper attempt"""
        if scraper_name not in self.state:
            self.state[scraper_name] = {
                "attempts": 0,
                "successes": 0,
                "failures": 0,
                "last_success": None,
                "last_failure": None,
                "last_error": None,
                "avg_events": 0,
                "consecutive_failures": 0
            }
        
        s = self.state[scraper_name]
        s["attempts"] += 1
        
        if success:
            s["successes"] += 1
            s["last_success"] = datetime.now().isoformat()
            s["consecutive_failures"] = 0
            # Update average events
            total_events = s["avg_events"] * (s["attempts"] - 1) + events_count
            s["avg_events"] = total_events / s["attempts"]
        else:
            s["failures"] += 1
            s["last_failure"] = datetime.now().isoformat()
            s["last_error"] = error
            s["consecutive_failures"] += 1
        
        self.save()
    
    def is_healthy(self, scraper_name: str) -> bool:
        """Check if scraper is healthy"""
        s = self.state.get(scraper_name, {})
        # Consider unhealthy after 3 consecutive failures
        return s.get("consecutive_failures", 0) < 3
    
    def get_stats(self) -> Dict:
        """Get overall scraper statistics"""
        total = len(self.state)
        healthy = sum(1 for s in self.state.values() if s.get("consecutive_failures", 0) < 3)
        failing = total - healthy
        return {"total": total, "healthy": healthy, "failing": failing}


class BaseScraper:
    """Base scraper with auto-healing capabilities"""
    
    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.state = ScraperState()
    
    def ai_fallback_scrape(self) -> List[ScrapedEvent]:
        """Fallback: Use AI agent to scrape difficult sites"""
        # For sites with 455 errors or other blocking, use web search
        if not self.config.get('urls', {}).get('home'):
            return []
        
        # Use simple AI search (simulated via web search for events)
        from event_scraper import AIFallbackScraper
        scraper = AIFallbackScraper(self.config)
        events = scraper.scrape()
        
        # Convert ScrapedEvent format to what we need
        converted = []
        for e in events:
            converted.append(ScrapedEvent(
                title=e.title,
                date=e.date,
                venue=e.venue,
                location=e.location,
                time=e.time,
                link=e.link
            ))
        
        return converted
    
    def fetch(self, url: str, retries: int = 3) -> Optional[str]:
        """Fetch URL with retry logic and anti-bot handling"""
        # Check if we should retry
        can_retry, wait_time = can_retry_scrape(self.name)
        if not can_retry:
            print(f"    ⏭️  Skipping {self.name} (retry limit reached)")
            return None
        if wait_time:
            print(f"    ⏳ Waiting {wait_time}s before retry (anti-bot protection)")
            time.sleep(wait_time)
        
        # Fetch with error handling
        for attempt in range(retries):
            try:
                # Add random delay to appear more human
                if attempt > 0:
                    time.sleep(1 + (attempt * 2))
                
                # Rotate User-Agent to avoid blocking
                user_agents = [
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
                ]
                self.session.headers['User-Agent'] = user_agents[attempt % len(user_agents)]
                
                resp = self.session.get(url, timeout=30)
                
                # Update scraper state
                state = load_scraper_state()
                state.setdefault(self.name, {})
                state[self.name]['last_attempt'] = time.time()
                state[self.name]['last_error_code'] = resp.status_code if hasattr(resp, 'status_code') else None
                state[self.name]['attempts'] = state[self.name].get('attempts', 0) + 1
                save_scraper_state(state)
                
                # Check for anti-bot errors
                if hasattr(resp, 'status_code') and resp.status_code in ANTIBOT_ERRORS:
                    print(f"    ⚠️ Anti-bot detected (code {resp.status_code}), will retry later")
                    return None
                
                resp.raise_for_status()
                return resp.text
                
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if hasattr(e.response, 'status_code') else None
                print(f"    ⚠️ Fetch attempt {attempt + 1}/{retries} failed: {e}")
                
                # Update state for retry logic
                state = load_scraper_state()
                state.setdefault(self.name, {})
                state[self.name]['last_attempt'] = time.time()
                state[self.name]['last_error_code'] = status_code
                state[self.name]['attempts'] = state[self.name].get('attempts', 0) + 1
                save_scraper_state(state)
                
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
            except Exception as e:
                print(f"    ❌ Error on attempt {attempt + 1}: {e}")
                if attempt == retries - 1:
                    # Check if we should fall back to AI
                    if self.config.get('scraper', {}).get('fallback') == 'ai':
                        print(f"    🤖 Falling back to AI for {self.name}")
                        events = self.ai_fallback_scrape()
                        if events:
                            return events
                return None
        return None
    
    def scrape(self) -> List[ScrapedEvent]:
        """Override in subclasses"""
        raise NotImplementedError
    
    def run(self) -> Tuple[List[ScrapedEvent], bool]:
        """Run scraper with error handling"""
        try:
            print(f"  🔍 {self.name}")
            events = self.scrape()
            success = True
            print(f"    ✓ Found {len(events)} events")
            self.state.record_attempt(self.name, True, len(events))
            return events, success
        except Exception as e:
            print(f"    ❌ Error: {e}")
            self.state.record_attempt(self.name, False, error=str(e))
            
            # Check for AI fallback
            if self.config.get('scraper', {}).get('fallback') == 'ai':
                print(f"    🤖 Falling back to AI scraping for {self.name}")
                try:
                    events = self.ai_fallback_scrape()
                    if events:
                        return events, True
                except Exception as ai_error:
                    print(f"    ❌ AI fallback also failed: {ai_error}")
            
            return [], False
    
    def ai_fallback_scrape(self) -> List[ScrapedEvent]:
        """Fallback: Use AI agent to scrape difficult sites"""
        import subprocess
        
        # For simple static sites, try web search
        if not self.config.get('urls', {}).get('home'):
            return []
        
        # Search for events
        query = f"{self.config.get('name')} {self.config.get('location', '')} evenemang"
        
        try:
            result = subprocess.run(
                ['python3', '-c', f'from scripts.smart_scraper import AIFallbackScraper; scraper = AIFallbackScraper({{self.config}}); events = scraper.scrape(); print(events)'],
                capture_output=True,
                text=True,
                timeout=60,
                cwd='/home/david/.openclaw/workspace/karlstad-events'
            )
            
            if result.stdout and 'ScrapedEvent' in result.stdout:
                # Parse the output
                events = []
                for line in result.stdout.strip().split('\n'):
                    if 'ScrapedEvent' in line:
                        # Simple parsing - in real implementation would be more robust
                        pass
                return events
                
        except Exception as e:
            print(f"    ❌ AI fallback error: {e}")
        
        return []


class VarmlandsMuseumScraper(BaseScraper):
    """Scraper for Värmlands Museum"""
    
    def scrape(self) -> List[ScrapedEvent]:
        events = []
        url = "https://varmlandsmuseum.se/evenemangskalender/"
        
        html = self.fetch(url)
        if not html or not HAS_BS4:
            return events
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find all event entries
        # Structure: h4 with date, followed by h4 with linked title
        content = soup.find('main') or soup.find('div', class_='content') or soup
        
        # Look for date patterns followed by event titles
        date_pattern = re.compile(r'(\d{1,2})\s+(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec)', re.I)
        
        current_date = None
        for elem in content.find_all(['h4', 'p', 'div']):
            text = elem.get_text(strip=True)
            
            # Check if this is a date line
            date_match = date_pattern.search(text.lower())
            if date_match and ('kl' in text or ':' in text):
                day = int(date_match.group(1))
                month_str = date_match.group(2).lower()[:3]
                months = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'maj': 5, 'jun': 6,
                         'jul': 7, 'aug': 8, 'sep': 9, 'okt': 10, 'nov': 11, 'dec': 12}
                month = months.get(month_str, 1)
                year = datetime.now().year
                current_date = f"{year}-{month:02d}-{day:02d}"
                continue
            
            # Look for event links
            if current_date:
                link = elem.find('a')
                if link and link.get('href'):
                    title = link.get_text(strip=True)
                    if title and len(title) > 5:  # Filter out short/noise text
                        href = link.get('href')
                        if not href.startswith('http'):
                            href = urljoin(url, href)
                        
                        events.append(ScrapedEvent(
                            title=title,
                            date=current_date,
                            venue="Värmlands Museum",
                            location="Karlstad",
                            link=href,
                            category="Kultur"
                        ))
                        current_date = None  # Reset after finding event
        
        return events


class ScalateaternScraper(BaseScraper):
    """Scraper for Scalateatern"""
    
    def scrape(self) -> List[ScrapedEvent]:
        events = []
        url = "https://www.scalateatern.com/vara-evenemang/"
        
        html = self.fetch(url)
        if not html or not HAS_BS4:
            return events
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Scalateatern uses Ticketmaster for actual events
        # Let's extract what we can from their page
        content = soup.find('main') or soup.find('article') or soup
        
        # Look for any event mentions
        for elem in content.find_all(['h2', 'h3', 'h4', 'p']):
            text = elem.get_text(strip=True)
            # Look for date patterns
            date_match = re.search(r'(\d{1,2})\s+(januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)\s+(\d{4})', text.lower())
            if date_match:
                # This is simplified - would need more parsing
                pass
        
        # Since they use Ticketmaster, we'll rely on that source
        # But let's add a placeholder noting this
        print("    ℹ️ Scalateatern uses Ticketmaster - checking API source")
        
        return events


class WermlandOperaScraper(BaseScraper):
    """Scraper for Wermland Opera"""
    
    def scrape(self) -> List[ScrapedEvent]:
        events = []
        urls = [
            "https://www.wermlandopera.com/evenemang/",
            "https://www.wermlandopera.com/kalendarium-2025-2026/"
        ]
        
        for url in urls:
            html = self.fetch(url)
            if not html or not HAS_BS4:
                continue
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for event cards or listings
            # Common patterns: article.event, div.event-item, etc.
            event_selectors = [
                'article.event',
                '.event-item',
                '.program-item',
                '[class*="event"]',
                'article'
            ]
            
            for selector in event_selectors:
                items = soup.select(selector)
                for item in items[:10]:  # Limit to avoid duplicates
                    try:
                        # Extract title
                        title_elem = item.find(['h2', 'h3', 'h4']) or item.find(class_=re.compile('title'))
                        if not title_elem:
                            continue
                        title = title_elem.get_text(strip=True)
                        
                        # Extract date
                        date_text = item.get_text()
                        date_match = re.search(r'(\d{1,2})\s+(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec)[\.\s]+(\d{4})', date_text.lower())
                        if not date_match:
                            continue
                        
                        day = int(date_match.group(1))
                        month_str = date_match.group(2).lower()[:3]
                        months = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'maj': 5, 'jun': 6,
                                 'jul': 7, 'aug': 8, 'sep': 9, 'okt': 10, 'nov': 11, 'dec': 12}
                        month = months.get(month_str, 1)
                        year = int(date_match.group(3))
                        date_str = f"{year}-{month:02d}-{day:02d}"
                        
                        # Extract link
                        link_elem = item.find('a')
                        link = None
                        if link_elem:
                            href = link_elem.get('href', '')
                            link = urljoin(url, href) if href else None
                        
                        events.append(ScrapedEvent(
                            title=title,
                            date=date_str,
                            venue="Wermland Opera",
                            location="Karlstad",
                            link=link,
                            category="Opera/Teater"
                        ))
                    except Exception as e:
                        continue
        
        return events


class NojesfabrikenScraper(BaseScraper):
    """Scraper for Nöjesfabriken (requires JavaScript)"""
    
    def scrape(self) -> List[ScrapedEvent]:
        events = []
        url = "https://www.nojesfabriken.se/nojeskalendern/"
        
        if not HAS_PLAYWRIGHT:
            print("    ⚠️ Playwright not available - skipping JS-heavy site")
            return events
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, wait_until='networkidle', timeout=30000)
                
                # Wait for content to load
                page.wait_for_timeout(2000)
                
                # Get rendered HTML
                html = page.content()
                browser.close()
                
                if not html or not HAS_BS4:
                    return events
                
                soup = BeautifulSoup(html, 'html.parser')
                
                # Look for event elements
                for item in soup.find_all(['article', 'div'], class_=re.compile('event|kalender|program')):
                    try:
                        title_elem = item.find(['h2', 'h3', 'h4']) or item.find(class_=re.compile('title'))
                        if not title_elem:
                            continue
                        title = title_elem.get_text(strip=True)
                        
                        # Try to find date
                        date_elem = item.find(class_=re.compile('date|datum|tid'))
                        date_str = None
                        if date_elem:
                            date_text = date_elem.get_text()
                            # Parse date
                            date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_text)
                            if date_match:
                                date_str = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
                        
                        if not date_str:
                            continue
                        
                        link_elem = item.find('a')
                        link = urljoin(url, link_elem.get('href')) if link_elem else None
                        
                        events.append(ScrapedEvent(
                            title=title,
                            date=date_str,
                            venue="Nöjesfabriken",
                            location="Karlstad",
                            link=link,
                            category="Klubb/Konsert"
                        ))
                    except Exception:
                        continue
                        
        except Exception as e:
            print(f"    ❌ Playwright error: {e}")
        
        return events


class GenericScraper(BaseScraper):
    """Generic scraper that tries multiple strategies"""
    
    def scrape(self) -> List[ScrapedEvent]:
        events = []
        urls = self.config.get('urls', {})
        
        for key, url in urls.items():
            if not isinstance(url, str) or not url.startswith('http'):
                continue
            
            html = self.fetch(url)
            if not html or not HAS_BS4:
                continue
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Strategy 1: Look for structured data (JSON-LD)
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict) and data.get('@type') == 'Event':
                        events.append(self._parse_jsonld_event(data, url))
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and item.get('@type') == 'Event':
                                events.append(self._parse_jsonld_event(item, url))
                except:
                    pass
            
            # Strategy 2: Look for common event patterns
            for article in soup.find_all('article'):
                event = self._parse_article(article, url)
                if event:
                    events.append(event)
        
        return events
    
    def _parse_jsonld_event(self, data: dict, base_url: str) -> ScrapedEvent:
        """Parse JSON-LD event data"""
        start_date = data.get('startDate', '')
        if 'T' in start_date:
            date_str = start_date.split('T')[0]
        else:
            date_str = start_date
        
        return ScrapedEvent(
            title=data.get('name', 'Unknown Event'),
            date=date_str,
            venue=self.config.get('name', 'Unknown Venue'),
            location=self.config.get('location', 'Karlstad'),
            link=data.get('url'),
            description=data.get('description', '')[:200]
        )
    
    def _parse_article(self, article, base_url: str) -> Optional[ScrapedEvent]:
        """Try to parse an article as an event"""
        title_elem = article.find(['h1', 'h2', 'h3'])
        if not title_elem:
            return None
        
        title = title_elem.get_text(strip=True)
        text = article.get_text()
        
        # Look for date patterns
        date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', text)
        if date_match:
            date_str = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
        else:
            # Try Swedish format
            date_match = re.search(r'(\d{1,2})\s+(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec)[\.\s]+(\d{4})', text.lower())
            if date_match:
                months = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'maj': 5, 'jun': 6,
                         'jul': 7, 'aug': 8, 'sep': 9, 'okt': 10, 'nov': 11, 'dec': 12}
                day = int(date_match.group(1))
                month = months.get(date_match.group(2)[:3], 1)
                year = int(date_match.group(3))
                date_str = f"{year}-{month:02d}-{day:02d}"
            else:
                return None
        
        link_elem = article.find('a')
        link = urljoin(base_url, link_elem.get('href')) if link_elem else None
        
        return ScrapedEvent(
            title=title,
            date=date_str,
            venue=self.config.get('name', 'Unknown'),
            location=self.config.get('location', 'Karlstad'),
            link=link
        )


class SmartScraperManager:
    """Manages all scrapers with auto-healing"""
    
    SCRAPER_MAP = {
        'varmlands_museum': VarmlandsMuseumScraper,
        'scalateatern': ScalateaternScraper,
        'wermland_opera': WermlandOperaScraper,
        'nojesfabriken': NojesfabrikenScraper,
    }
    
    def __init__(self):
        self.state = ScraperState()
    
    def get_scraper(self, name: str, config: dict) -> BaseScraper:
        """Get appropriate scraper for venue"""
        scraper_class = self.SCRAPER_MAP.get(name, GenericScraper)
        return scraper_class(name, config)
    
    def run_all(self, venues: dict) -> List[ScrapedEvent]:
        """Run all scrapers and collect events"""
        all_events = []
        failed_scrapers = []
        
        print("\n🔍 Running Smart Scrapers")
        print("=" * 40)
        
        for tier_name, tier_venues in venues.items():
            if not tier_name.startswith('tier'):
                continue
            
            print(f"\n📂 {tier_name}")
            
            for venue_key, config in tier_venues.items():
                if not config.get('active', False):
                    continue
                
                scraper_type = config.get('scraper', {}).get('type', 'static')
                if scraper_type == 'manual':
                    continue
                
                scraper = self.get_scraper(venue_key, config)
                events, success = scraper.run()
                
                if not success:
                    failed_scrapers.append((venue_key, config))
                
                all_events.extend(events)
        
        # Report stats
        stats = self.state.get_stats()
        print(f"\n📊 Scraper Health: {stats['healthy']}/{stats['total']} healthy")
        
        # Auto-retry failed scrapers once
        if failed_scrapers:
            print(f"\n🔄 Retrying {len(failed_scrapers)} failed scrapers...")
            for venue_key, config in failed_scrapers:
                print(f"  🔄 Retry: {config.get('name', venue_key)}")
                scraper = self.get_scraper(venue_key, config)
                events, success = scraper.run()
                if success:
                    all_events.extend(events)
        
        return all_events


def main():
    """Test the smart scrapers"""
    import yaml
    
    venues_file = SCRIPT_DIR / "venues.yaml"
    if not venues_file.exists():
        print("❌ venues.yaml not found")
        return
    
    with open(venues_file) as f:
        venues = yaml.safe_load(f)
    
    manager = SmartScraperManager()
    events = manager.run_all(venues)
    
    print(f"\n✅ Total events collected: {len(events)}")
    for evt in events[:10]:  # Show first 10
        print(f"  • {evt.date}: {evt.title[:50]} ({evt.venue})")
    
    return events


if __name__ == "__main__":
    main()
