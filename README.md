# Karlstad Events

A comprehensive event calendar for Karlstad and surrounding areas (Forshaga, Kil, Molkom, Skattkärr, Väse, Vålberg, Deje).

**Live Site:** https://karlstad-events.surge.sh

## Features

- 🔍 **Multi-source aggregation**: APIs, venue websites, aggregators
- 🤖 **AI fallback**: Automated scraping with AI agent backup
- 🔍 **Continuous discovery**: Weekly scans for new venues
- 🔄 **Auto-deployment**: Surge.sh deployment on every update
- 📱 **Mobile-friendly**: Responsive Hugo theme

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              CRON (Weekly - Monday 03:00)               │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│              scripts/research-events.sh                 │
│  • Check dependencies                                   │
│  • Run enhanced_research.py                             │
│  • Build Hugo site                                      │
│  • Deploy to Surge.sh                                   │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│           scripts/enhanced_research.py                  │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Phase 1: Ticketmaster API                         │  │
│  │ Phase 2: Venue Websites (Static Scraping)         │  │
│  │ Phase 3: Aggregator Sites                         │  │
│  │ Fallback: AI Agent if automation fails            │  │
│  └───────────────────────────────────────────────────┘  │
│                      │                                  │
│                      ▼                                  │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Venue Discovery Module                            │  │
│  │ • Searches for new sources weekly                 │  │
│  │ • Maintains pending review list                   │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Event Sources

### Tier 1: Major Venues
- Wermland Opera
- Scalateatern
- Nöjesfabriken
- Löfbergs Arena
- Karlstad CCC

### Tier 2: Cultural Institutions
- Värmlands Museum
- Sandgrund Lars Lerin
- Bibliotekshuset
- Mariebergsskogen

### Tier 3: Small Venues
- Gränden K&B
- VERKET
- The Bishops Arms

### Tier 4: Aggregators
- Ticketmaster (API)
- Tickster
- Karlstad.com
- Stadsevent.se
- Nöje.se

See `scripts/venues.yaml` for complete configuration.

## Setup

### Prerequisites

```bash
# Install Python dependencies
pip3 install -r requirements.txt

# Install Hugo (if not present)
# For Raspberry Pi ARM64:
wget https://github.com/gohugoio/hugo/releases/download/v0.123.0/hugo_extended_0.123.0_linux-arm64.tar.gz
tar -xzf hugo_extended_0.123.0_linux-arm64.tar.gz
sudo mv hugo /usr/local/bin/

# Install Surge.sh CLI
npm install -g surge
```

### Configuration

```bash
# Optional: Add Ticketmaster API key for better coverage
export TICKETMASTER_API_KEY="your-api-key"

# Configure Surge.sh (one-time setup)
surge login
```

### First Run

```bash
# Manual research run
python3 scripts/enhanced_research.py

# Or full pipeline with deployment
bash scripts/research-events.sh
```

## Cron Job

Already configured for weekly runs. To verify:

```bash
crontab -l | grep karlstad
```

To edit:
```bash
crontab -e
```

Current schedule: `0 3 * * 1` (Mondays at 03:00)

## Venue Discovery

The system continuously searches for new event sources:

```bash
# Manual discovery run
python3 scripts/venue_discovery.py
```

New discoveries are saved to `data/new-sources.json` for review.

To approve a discovered venue:
```python
from scripts.venue_discovery import VenueDiscovery
d = VenueDiscovery()
d.approve_venue("Venue Name", tier="tier3_small")
```

## AI Fallback

When automated scraping fails, the system creates an AI agent request:

1. Failure is logged to `data/failed_scrapes.json`
2. Request marker created at `data/.ai-fetch-requested`
3. AI agent fetches events manually
4. Results saved to `data/ai-fetched-events.json`

## Project Structure

```
karlstad-events/
├── archetypes/          # Hugo templates
├── content/
│   └── events/          # Generated event markdown files
├── data/
│   ├── research_state.json      # Event deduplication state
│   ├── failed_scrapes.json      # Failed scrapes for AI
│   ├── new-sources.json         # Pending venue reviews
│   └── discovery-log.json       # Discovery activity
├── scripts/
│   ├── venues.yaml              # Venue configurations
│   ├── enhanced_research.py     # Main research coordinator
│   ├── event_scraper.py         # Scraper framework
│   ├── venue_discovery.py       # New source discovery
│   ├── ai_fallback.py           # AI agent integration
│   └── research-events.sh       # Cron entry point
├── static/              # Static assets
├── themes/              # Hugo themes
├── config.toml          # Hugo configuration
├── requirements.txt     # Python dependencies
└── CNAME                # Surge.sh domain config
```

## Error Handling

The system is designed to be resilient:

1. **Dependency failures**: Auto-install attempted
2. **Scraper failures**: Logged, doesn't stop other sources
3. **Complete failure**: AI fallback triggered
4. **Deployment failures**: Git push still attempted

## Monitoring

Check these files for system status:

```bash
# Last research run
cat data/research_state.json | jq '.last_updated'

# Failed scrapes needing attention
cat data/failed_scrapes.json

# New venues pending review
cat data/new-sources.json

# Discovery activity log
cat data/discovery-log.json
```

## Contributing New Venues

Found a new event source? Add it to `scripts/venues.yaml`:

```yaml
tier3_small:
  my_new_venue:
    name: "Venue Name"
    location: "Karlstad"
    type: ["Konserter", "Pub"]
    urls:
      events: "https://venue.com/events"
    scraper:
      type: "static"  # or "dynamic" for JS sites
      method: "beautifulsoup"
    active: true
```

## License

MIT
