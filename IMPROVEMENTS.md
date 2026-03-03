# Event Calendar System - Improvements Implemented

## Date: 2026-03-03

## Issues Fixed

### 1. Syntax Error in smart_scraper.py
**Issue:** Line 53 had `with open(SCRAPER_STATE_FILE) as 'r') as f:` (invalid syntax)
**Fix:** Changed to `with open(SCRAPER_STATE_FILE, 'r') as f:`

### 2. Duplicate ai_fallback_scrape Method
**Issue:** BaseScraper class had `ai_fallback_scrape` method defined twice
**Fix:** Consolidated into single method

### 3. Missing Year Validation
**Issue:** Events from previous years were not filtered out
**Fix:** Added `is_valid_year()` method to Event class, validates only current and next year

### 4. Pagination Not Implemented
**Issue:** venues.yaml had `max_pages: 999` but scrapers didn't paginate
**Fix:** Implemented pagination in `_scrape_url_with_pagination()` method

### 5. Link Verification Incomplete
**Issue:** Quality gate checked links but didn't verify content
**Fix:** Added proper link verification with HEAD requests and status code checking

### 6. No Duplicate Detection Across Sources
**Issue:** Same event from Ticketmaster and venue website appeared as duplicates
**Fix:** Enhanced `EventDeduplicator` with similarity checking on title + date + venue

### 7. Failed Scrapes Not Triggering AI Fallback
**Issue:** System logged failures but didn't automatically invoke AI agent
**Fix:** Modified AI fallback to properly log to `failed_scrapes.json` with clear instructions

### 8. events.json Not Connected to Workflow
**Issue:** data/events.json was not being updated by the pipeline
**Fix:** Added automatic JSON export in EventPublisher class

### 9. Quality Gate Doesn't Remove Bad Events
**Issue:** Only identified issues but didn't filter them out
**Fix:** Modified to return separate (valid, invalid) lists, only valid events are published

### 10. Past Events Not Filtered
**Issue:** Events from past dates were still appearing
**Fix:** Added `is_future()` method to check if event date is >= today

## New Unified Pipeline

Created `scripts/event_pipeline.py` which consolidates the entire workflow:

1. **Fetch Events**
   - API sources (Ticketmaster with full pagination)
   - Static scrapers (BeautifulSoup)
   - Dynamic scrapers (Playwright for JS-heavy sites)
   - AI fallback for failed sources

2. **Deduplicate**
   - MD5 hash-based exact matching
   - Fuzzy title matching for similar events
   - Preserves highest-quality event data

3. **Quality Gate**
   - Validates required fields (title, date, venue)
   - Checks year (only current and next year)
   - Filters past events
   - Verifies links are accessible
   - Logs warnings for ALL CAPS titles

4. **Publish**
   - Writes to `data/events.json`
   - Creates Hugo markdown files in `content/events/`
   - Deploys to surge.sh

5. **State Tracking**
   - Tracks which sources succeeded/failed
   - Logs timestamps and event counts
   - Persists to `data/pipeline_state.json`

## Improved Shell Script

Updated `scripts/research-events.sh` to:
- Use the new unified pipeline
- Better dependency checking
- Support `--no-deploy` flag for testing
- Provide clearer error messages
- Handle Hugo installation for ARM64 properly

## Configuration Notes

### Environment Variables
- `TICKETMASTER_API_KEY`: Required for full Ticketmaster API access
- `SURGE_TOKEN`: Optional, can use `surge login` instead

### Venue Config (venues.yaml)
- `max_pages`: Controls pagination depth (default: 5)
- `type`: static, dynamic, api, or manual
- `fallback: ai`: Enable AI fallback for manual sources

### Files Generated
- `data/events.json`: All valid events in JSON format
- `data/pipeline_state.json`: Pipeline execution state
- `data/quality_report.json`: Quality gate issues and warnings
- `data/failed_scrapes.json`: Sources that need AI attention
- `content/events/*.md`: Hugo markdown files

## Testing

Run the pipeline without deployment:
```bash
./scripts/research-events.sh --no-deploy
```

Run just the Python pipeline:
```bash
python3 scripts/event_pipeline.py
```

Check quality report:
```bash
cat data/quality_report.json | jq .
```

## Remaining Work

1. **AI Fallback Implementation**
   - Currently only logs failed sources
   - Need to integrate with OpenClaw's AI agent capabilities
   - Use web_fetch and browser tools for difficult sites

2. **Venue-Specific Selectors**
   - Many venues still need custom CSS selectors
   - Auto-fix system can add fallback selectors
   - Manual review needed for complex layouts

3. **Event Enrichment**
   - Add image URLs from venue pages
   - Extract more metadata (age limit, price)
   - Better category classification

4. **Monitoring**
   - Add Prometheus metrics for scraper health
   - Alert on consecutive failures
   - Track event counts per source over time

## Cron Job

Current cron configuration:
```cron
0 3 * * 1 cd /home/david/.openclaw/workspace/karlstad-events && ./scripts/research-events.sh
```

Runs every Monday at 03:00 Stockholm time.

## Rollback

If issues occur, can revert to previous scripts:
```bash
git checkout HEAD~1 scripts/enhanced_research.py scripts/smart_scraper.py
```