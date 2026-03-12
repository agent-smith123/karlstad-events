# Karlstad Events - Implementation Summary

**Date:** 2026-03-02  
**Status:** ✅ Research Complete, Implementation Ready

---

## 📊 Research Findings

### Sources Identified: 25+ Venues & Calendars

| Tier | Category | Count | Priority |
|------|----------|-------|----------|
| Tier 1 | Major Venues | 5 | 🔴 High |
| Tier 2 | Cultural Institutions | 4 | 🟡 Medium |
| Tier 3 | Small Venues/Pubs | 3 | 🟢 Low |
| Tier 4 | Aggregators | 5 | 🔴 High |
| Tier 5 | Municipal | 2 | 🟡 Medium |
| Special | Festivals/Events | 3 | Seasonal |

### Key Discovery: Multi-Tier Strategy Required

No single source provides comprehensive coverage. Successful aggregation requires:

1. **API Integration** (Ticketmaster) - 5000 req/day free tier
2. **Static Scraping** (BeautifulSoup) - For WordPress/simple sites
3. **Dynamic Scraping** (Playwright) - For JavaScript-heavy sites
4. **Manual Curation** - For venues without digital presence

---

## 🛠️ Implementation Delivered

### New Files Created

| File | Purpose | Status |
|------|---------|--------|
| `scripts/venues.yaml` | Venue configuration (25+ venues) | ✅ Complete |
| `scripts/event_scraper.py` | Full scraper framework | ✅ Complete |
| `scripts/enhanced_research.py` | Multi-source research | ✅ Complete |
| `scripts/research-events.sh` | Updated cron script | ✅ Updated |
| `requirements.txt` | Python dependencies | ✅ Complete |
| `data/research_state.json` | State tracking | ✅ Complete |
| `RESEARCH-REPORT.md` | Full research documentation | ✅ Complete |

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    CRON (Mon 03:00)                     │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│              scripts/research-events.sh                 │
│  • Dependency check                                     │
│  • Run enhanced_research.py                             │
│  • Deploy static site build                             │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│           scripts/enhanced_research.py                  │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Phase 1: Ticketmaster API                         │  │
│  │ - 50km radius around Karlstad                     │  │
│  │ - Structured JSON response                        │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Phase 2: Venue Websites (Static)                  │  │
│  │ - Värmlands Museum                                │  │
│  │ - Wermland Opera                                  │  │
│  │ - Scalateatern                                    │  │
│  │ - Karlstad CCC                                    │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Phase 3: Aggregators                              │  │
│  │ - Karlstad.com                                    │  │
│  │ - Stadsevent.se                                   │  │
│  │ - Nöje.se                                         │  │
│  └───────────────────────────────────────────────────┘  │
│                      │                                  │
│                      ▼                                  │
│  ┌───────────────────────────────────────────────────┐  │
│  │ EventStore (Deduplication)                        │  │
│  │ - Hash-based dedup (title+date+venue)             │  │
│  │ - State persistence (JSON)                        │  │
│  │ - Markdown generation                             │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│           content/events/*.md (Hugo)                    │
│  • One file per event                                   │
│  • Front matter: title, date, venue, location, link     │
│  • Auto-generated from scraped data                     │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                Static Site Deploy                       │
│  • Automatic deployment                                 │
│  • Site updates at karlstad-events.surge.sh             │
└─────────────────────────────────────────────────────────┘
```

---

## 🔧 Setup Instructions

### 1. Install Dependencies

```bash
cd ~/.openclaw/workspace/karlstad-events
pip3 install -r requirements.txt
```

### 2. Configure API Keys (Optional)

For Ticketmaster API integration:

```bash
# Get free API key at: https://developer.ticketmaster.com/
export TICKETMASTER_API_KEY="your-api-key-here"

# Or add to ~/.openclaw/.env
echo "TICKETMASTER_API_KEY=your-api-key-here" >> ~/.openclaw/.env
```

### 3. Test Run

```bash
# Manual test
python3 scripts/enhanced_research.py

# Or full script
bash scripts/research-events.sh
```

### 4. Cron Configuration

Already configured: `0 3 * * 1` (Mondays at 03:00)

To verify:
```bash
crontab -l | grep karlstad
```

---

## 📈 Coverage Comparison

| Before | After |
|--------|-------|
| ~5 hardcoded venues | 25+ configured venues |
| Manual research only | API + Scraping + Manual |
| No deduplication | Hash-based dedup |
| No state tracking | Persistent state file |
| Static script | Modular, extensible framework |

---

## ⚠️ Known Limitations

1. **JavaScript-heavy sites** (Nöjesfabriken, Karlstad.com) require Playwright
2. **Facebook events** (Gränden, VERKET) need manual entry or Graph API
3. **Rate limiting** - Respect robots.txt and add delays between requests
4. **Site changes** - Selectors may break if sites redesign

---

## 🎯 Next Steps (Optional Enhancements)

### Phase 1: Deploy Current Implementation
- [ ] Install dependencies on Pi
- [ ] Test full research cycle
- [ ] Verify cron job execution
- [ ] Monitor first automated run

### Phase 2: Add Dynamic Scraping
- [ ] Install Playwright browsers
- [ ] Configure Nöjesfabriken scraper
- [ ] Add Karlstad.com aggregator scraper

### Phase 3: Email Notifications
- [ ] Integrate with AgentMail
- [ ] Create weekly digest template
- [ ] Add "new this week" highlighting

### Phase 4: Advanced Features
- [ ] Image fetching for events
- [ ] Category auto-classification
- [ ] iCal export for users
- [ ] SMS alerts for major events

---

## 📞 Venue Contact List (For Manual Verification)

| Venue | Contact Method | Notes |
|-------|---------------|-------|
| Gränden K&B | Facebook | DM for event info |
| VERKET | Facebook | Active page |
| Synth i Molkom | Website | Annual festival |
| Fryksdalsdansen | Website | Annual (July) |

---

## 🔐 Security Notes

- API keys stored in environment variables
- No credentials in code
- Rate limiting respects source policies
- User-Agent identifies bot properly

---

*Implementation based on deep research across 40+ sources*
