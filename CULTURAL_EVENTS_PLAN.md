# Cultural Events Implementation Plan

## Missing Event Types
- Utställningar (Exhibitions)
- Marknader (Markets)
- Seminarium (Seminars)
- Föreläsningar (Lectures)

## Venues That Should Have These Events

### Museums (Utställningar)
- Värmlands Museum - https://varmlandsmuseum.se/utstallningar/
- Sandgrund Lars Lerin - Konsthall
- Kristinehamns Konstmuseum
- Rackstadmuseet

### Libraries (Föreläsningar, Seminarium)
- Bibliotekshuset (Stadsbiblioteket Karlstad)
- Arvika bibliotek
- Forshaga bibliotek
- Kristinehamns bibliotek
- Säffle bibliotek

### Markets (Marknader)
- Stora Torget (Karlstad)
- Various seasonal markets

## Implementation Steps

1. ✅ Added multi-day event support (end_date field)
2. ✅ Updated Hugo template to show date ranges
3. Need to: Add specific URLs for cultural venues
4. Need to: Update AI search queries to include cultural keywords
5. Need to: Handle JS-heavy sites with Playwright

## Technical Challenges

- Many cultural sites use JavaScript calendars
- Exhibitions often don't have specific dates (ongoing/seasonal)
- Need to distinguish between permanent exhibitions and timed events
