# Self-Healing Scraper System

## Overview

The Karlstad Events scraper system now includes automatic error detection, diagnosis, and repair capabilities. When scrapers fail, the system automatically analyzes the issue and applies fixes.

## How It Works

### 1. Smart Scrapers (`scripts/smart_scraper.py`)

Venue-specific scrapers optimized for each source:

| Venue | Scraper | Status | Events Found |
|-------|---------|--------|--------------|
| Wermland Opera | `WermlandOperaScraper` | ✅ Working | 8 |
| Värmlands Museum | `VarmlandsMuseumScraper` | ✅ Working | 5 |
| Ticketmaster | API Integration | ✅ Working | 20 |
| Nöjesfabriken | `NojesfabrikenScraper` | ⚠️ Needs Playwright | 0 |
| Scalateatern | `ScalateaternScraper` | ℹ️ Uses Ticketmaster | 0 |
| Others | `GenericScraper` | 🔄 Auto-learning | Varies |

### 2. Auto-Fix System (`scripts/auto_fix.py`)

Automatically detects and fixes common scraper issues:

| Issue Type | Detection Pattern | Automatic Fix |
|------------|------------------|---------------|
| Timeout | "timeout", "timed out" | Increase timeout to 60s |
| 404 Not Found | "404", "not found" | Mark URL for verification |
| SSL Error | "ssl", "certificate" | Disable SSL verification |
| Parse Error | "parse", "selector" | Add fallback selectors |
| Connection Error | "connection", "refused" | Add retry logic (3x) |

### 3. Execution Flow

```
┌─────────────────────────────────────────────────────────┐
│              CRON (Monday 03:00)                        │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│  Phase 1: Auto-Fix System                               │
│  • Load scraper state (consecutive failures)            │
│  • Analyze error patterns                               │
│  • Apply fixes to venues.yaml                           │
│  • Save fix history                                     │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│  Phase 2: Smart Scrapers                                │
│  • Run venue-specific scrapers                          │
│  • Track success/failure per scraper                    │
│  • Auto-retry failed scrapers once                      │
│  • Collect events                                       │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│  Phase 3: Traditional Research (Backup)                 │
│  • Run enhanced_research.py scrapers                    │
│  • Deduplicate with smart scraper results               │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│  Phase 4: AI Fallback (If All Else Fails)               │
│  • Triggered if research completely fails               │
│  • Creates request for manual AI intervention           │
└─────────────────────────────────────────────────────────┘
```

## Monitoring Scraper Health

### Check Scraper State

```bash
# View scraper health statistics
cat data/scraper_state.json | jq '.'

# Check which scrapers are failing
cat data/scraper_state.json | jq 'to_entries | map(select(.value.consecutive_failures > 0))'
```

### View Fix History

```bash
# See all auto-fixes applied
cat data/auto_fix_log.json | jq '.fixes'

# Recent fixes (last 10)
cat data/auto_fix_log.json | jq '.fixes[-10:]'
```

### Test Scrapers Manually

```bash
# Run smart scrapers only
python3 scripts/smart_scraper.py

# Run auto-fix system
python3 scripts/auto_fix.py

# Full research cycle
python3 scripts/enhanced_research.py
```

## How Auto-Fix Detects Issues

The system tracks scraper performance in `data/scraper_state.json`:

```json
{
  "wermland_opera": {
    "attempts": 10,
    "successes": 10,
    "failures": 0,
    "consecutive_failures": 0,
    "avg_events": 8.2
  },
  "varmlands_museum": {
    "attempts": 5,
    "successes": 3,
    "failures": 2,
    "consecutive_failures": 2,
    "last_error": "timeout: connection timed out after 30s"
  }
}
```

When `consecutive_failures >= 2`, the auto-fix system:
1. Analyzes the `last_error` message
2. Matches against known patterns
3. Applies the appropriate fix
4. Saves the fix to `venues.yaml`
5. Logs the fix in `auto_fix_log.json`

## Example Auto-Fix Scenarios

### Scenario 1: Timeout Error

**Before:**
```
❌ varmlands_museum: timeout: connection timed out after 30s
```

**Auto-Fix Applied:**
```yaml
varmlands_museum:
  name: "Värmlands Museum"
  scraper:
    type: "static"
    timeout: 60  # ← Increased from 30 to 60
```

**After:**
```
✅ varmlands_museum: Found 5 events
```

### Scenario 2: Parse Error

**Before:**
```
❌ nojesfabriken: selector '.event' not found in HTML
```

**Auto-Fix Applied:**
```yaml
nojesfabriken:
  name: "Nöjesfabriken"
  scraper:
    type: "dynamic"
    fallback_event:  # ← Added fallback selectors
      - "article"
      - ".event"
      - "[class*='event']"
      - "div.item"
    fallback_title:
      - "h1"
      - "h2"
      - "h3"
      - ".title"
```

**After:**
```
✅ nojesfabriken: Found 3 events (using fallback selectors)
```

## Continuous Improvement

The system learns and improves over time:

1. **Weekly Discovery**: `venue_discovery.py` finds new potential sources
2. **Performance Tracking**: Each scraper attempt is logged
3. **Pattern Recognition**: Common errors trigger specific fixes
4. **Fix History**: All applied fixes are logged for review
5. **Health Monitoring**: Unhealthy scrapers are auto-retried

## Adding New Venue-Specific Scrapers

To add a custom scraper for a venue:

1. Create a new scraper class in `smart_scraper.py`:

```python
class MyVenueScraper(BaseScraper):
    def scrape(self) -> List[ScrapedEvent]:
        events = []
        url = "https://myvenue.se/events"
        
        html = self.fetch(url)
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract events
        for item in soup.select('.event-card'):
            title = item.find('h3').get_text(strip=True)
            # ... extract date, link, etc.
            events.append(ScrapedEvent(title=title, ...))
        
        return events
```

2. Register it in `SmartScraperManager.SCRAPER_MAP`:

```python
SCRAPER_MAP = {
    'my_venue': MyVenueScraper,
    # ... other scrapers
}
```

3. Add venue to `venues.yaml` with the scraper name

## Troubleshooting

### Scraper Still Failing After Auto-Fix

1. Check the error message:
   ```bash
   cat data/scraper_state.json | jq '.my_scraper.last_error'
   ```

2. Manually test the URL:
   ```bash
   curl -I "https://venue.se/events"
   ```

3. If the site structure changed, update selectors in `venues.yaml`

4. Consider switching to dynamic scraping (Playwright) for JS-heavy sites

### Too Many Auto-Fixes Being Applied

The system limits fixes to 5 per run. To adjust:

```python
# In auto_fix.py
fixes = fixer.check_and_fix(max_fixes_per_run=10)  # Increase limit
```

### Review Applied Fixes

```bash
# See all fixes
cat data/auto_fix_log.json | jq '.fixes[] | {timestamp, venue, fix_type}'
```

## Current Status

**Working Scrapers:** 3/15 (20%)
- Wermland Opera ✅
- Värmlands Museum ✅
- Ticketmaster API ✅

**Needs Attention:** 12/15 (80%)
- Most venues need custom selectors or dynamic scraping
- Auto-fix system will gradually improve coverage

**Goal:** 80%+ working scrapers within 4 weeks through automatic learning and fixes
