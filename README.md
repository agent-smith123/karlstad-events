# Karlstad Events

A static site listing events and happenings in Karlstad and surrounding areas.

## 🌐 Live Site

**https://karlstad-events.netlify.app**

## 📍 Areas Covered

- Karlstad
- Forshaga
- Kil
- Molkom
- Skattkärr
- Väse
- Vålberg
- Deje

## 🔄 How It Works

1. **Weekly Research** (Monday 03:00): Scripts search for events from local venues
2. **Static Site Generation**: Hugo builds the site from markdown files
3. **Netlify Deployment**: Auto-deploys to https://karlstad-events.netlify.app
4. **Email Notification**: David gets notified with a link to the week's events

## 📂 Project Structure

```
karlstad-events/
├── content/events/     # Event markdown files
├── layouts/            # Hugo templates
├── static/             # Static assets
├── scripts/            # Automation scripts
│   ├── research-events.sh   # Event research
│   ├── fetch-events.py      # Python event fetcher
│   └── weekly-update.sh     # Weekly cron job
├── hugo.toml           # Hugo config
└── netlify.toml        # Netlify config
```

## 🛠️ Adding Events

Add a new markdown file in `content/events/`:

```markdown
---
title: "Event Title"
date: 2026-03-14
venue: "Venue Name"
location: "Karlstad"
time: "19:00"
link: "https://example.com"
categories: ["Musik"]
---

Event description here...
```

## 🔧 Commands

```bash
# Build site
hugo

# Build and serve locally
hugo server

# Run weekly update manually
./scripts/weekly-update.sh

# Test research
./scripts/research-events.sh
```

## 📅 Cron Schedule

```
0 3 * * 1  # Every Monday at 03:00
```

## Technologies

- **Static Site Generator**: Hugo
- **Hosting**: Netlify
- **Source**: GitHub
- **Automation**: Shell scripts + cron
