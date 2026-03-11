#!/bin/bash
# Weekly Event Calendar Update
# Fetches events, validates, deduplicates, quality gates, and deploys

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$SCRIPT_DIR/weekly-update.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M')] $1" | tee -a "$LOG_FILE"; }

log "🔄 Weekly Karlstad Events Update"
cd "$PROJECT_DIR"

log "📥 Fetching and processing events..."
python3 scripts/pipeline.py >> "$LOG_FILE" 2>&1

if [ $? -ne 0 ]; then
    log "❌ Pipeline failed - check logs"
    exit 1
fi

SITE_URL="https://karlstad-events.surge.sh"
WEEK=$(date '+%W')
YEAR=$(date '+%Y')

# Generate event list for email
EVENT_COUNT=$(python3 -c "
import json
with open('assets/data/events.json') as f:
    print(len(json.load(f)))
" 2>/dev/null || echo "0")

EVENT_LIST=$(python3 -c "
import json
from datetime import datetime

with open('assets/data/events.json') as f:
    events = json.load(f)

today = datetime.now().date().isoformat()
upcoming = [e for e in events if e['date'] >= today]

for e in sorted(upcoming, key=lambda x: x['date'])[:10]:  # First 10 events
    dt = datetime.strptime(e['date'], '%Y-%m-%d')
    week = dt.isocalendar()[1]
    weekday = ['Mån','Tis','Ons','Tor','Fre','Lör','Sön'][dt.weekday()]
    print(f\"📅 {e['date']} ({weekday})\")
    print(f\"   {e['title'][:50]}...\")
    print(f\"   📍 {e['venue']}, {e['location']}\")
    print()
" 2>/dev/null)

EMAIL_BODY="Hej David!

🔔 Karlstad Events - Uppdatering v${WEEK}, ${YEAR}

🌐 ${SITE_URL}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Totalt ${EVENT_COUNT} evenemang

Kommande evenemang (första 10):
${EVENT_LIST}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Se alla event på: ${SITE_URL}

// OpenClaw
"

git add -A
git commit -m "Auto: Weekly update v${WEEK}, ${YEAR} (${EVENT_COUNT} events)" 2>/dev/null || true
git push origin main 2>/dev/null || true

/home/david/.openclaw/workspace/scripts/agentmail.sh send "david.nossebro@gmail.com" "Karlstad Events - Vecka ${WEEK}" "$EMAIL_BODY" 2>> "$LOG_FILE" || true

log "✅ Klart!"
