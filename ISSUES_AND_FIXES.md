# Event Calendar Issue Fix Plan

## Critical Issues

### 1. Same Event Listed at Multiple Venues (High Priority)
**Problem:** Events like "Mendelssohn och Tjajkovskij" appear at both Karlstad CCC AND Wermland Opera
**Root Cause:** Wermland Opera site lists events for venues they're hosting/organizing
**Impact:** Users see the same event in multiple places

**Fix:**
- Add venue blacklist: If venue is in EVENT_LISTING_VENUES, extract ACTUAL venue from event data
- Use the event's `location.name` from JSON-LD, not the source venue
- Priority: Actual venue > listing venue

### 2. Title Formatting Duplicates (High Priority)
**Problem:** "CARL-EINAR HÄCKNER" vs "Carleinar Häckner" - same event, different case/title format
**Root Cause:** Different sources format titles differently
**Impact:** Same event listed multiple times

**Fix:**
- Normalize titles: uppercase → title case, remove extra punctuation
- Better title similarity detection (>80% overlap = duplicate)
- Keep the longer, more complete title

### 3. Ticketmaster vs Venue Duplicates (Medium Priority)
**Problem:** Same event appears from both venue website and Ticketmaster
**Root Cause:** Both sources list the event
**Impact:** Double entries on the site

**Fix:**
- Add "Ticketmaster" to AGGREGATOR_SOURCES
- Deduplicate by (date, normalized_title, normalized_venue)
- Prefer venue source over Ticketmaster (has better info)

### 4. Missing Venue Extraction (High Priority)
**Problem:** Some events don't have the actual venue extracted
**Root Cause:** JSON-LD location.name not always available
**Impact:** Wrong venue shown

**Fix:**
- Look for venue in multiple places:
  1. JSON-LD location.name
  2. Event title (e.g., "Event @ Venue")
  3. Event description
  4. Page breadcrumbs
- Fallback to source venue only if no better option

## Implementation Plan

### Phase 1: Improve Venue Extraction (ai_parser_fetcher.py)
```python
def extract_venue_from_event(event_data: dict, source_venue: str) -> str:
    """
    Extract actual venue from event data with multiple fallbacks
    """
    # 1. Check JSON-LD location.name
    # 2. Check title patterns (e.g., "Event @ Venue")
    # 3. Check if source is a listing venue (Wermland Opera)
    # 4. Fallback to source_venue
```

### Phase 2: Better Title Normalization
```python
def normalize_title(title: str) -> str:
    """
    Normalize title for better duplicate detection
    - Uppercase → Title case
    - Remove extra punctuation
    - Remove common variations
    """
```

### Phase 3: Enhanced Deduplication (event_pipeline.py)
```python
def deduplicate(self, events: List[Event]) -> List[Event]:
    """
    Enhanced deduplication:
    1. Group by (date, normalized_title)
    2. If same venue (normalized) → duplicate
    3. If different venues → check if one is listing venue
    4. If listing venue → use other venue's data
    """
```

### Phase 4: Venue Mapping
Create a venue mapping for events that move:
- Karlstad CCC → actual venue (if event is elsewhere)
- Wermland Opera → actual venue (if event is elsewhere)
- Extract from event name or description

## Testing Checklist

After fixes:
- [ ] No same event at multiple venues
- [ ] No uppercase/lowercase duplicates
- [ ] No Ticketmaster + venue duplicates
- [ ] All events have correct venue
- [ ] Count events on site = events.json count
- [ ] Verify with Playwright inspection

## Priority
1. **Fix venue extraction** (causes venue duplicates)
2. **Better title normalization** (causes case duplicates)
3. **Enhanced deduplication** (catch all cases)
4. **Verify with Playwright** (confirm fixes)