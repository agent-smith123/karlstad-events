#!/bin/bash
# Weekly events update - runs every Monday at 03:00

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$SCRIPT_DIR/weekly-update.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M')] $1" | tee -a "$LOG_FILE"
}

log "========================================="
log "🔄 Weekly Karlstad Events Update Started"

cd "$PROJECT_DIR"

# Step 1: Research new events (manual step - update data/events.json)
log "📡 Manual research required - update data/events.json"

# Step 2: Build the site
log "🏗️ Building Hugo site..."
hugo >> "$LOG_FILE" 2>&1

# Deploy to surge
log "🚀 Deploying to surge.sh..."
cd public
surge . karlstad-events.surge.sh >> "$LOG_FILE" 2>&1
cd "$PROJECT_DIR"

# Step 3: Send email
log "📧 Building notification email..."

SITE_URL="https://karlstad-events.surge.sh"
WEEK=$(date '+%W')
YEAR=$(date '+%Y')

# Build event list from data file
EVENT_LIST=$(cat data/events.json | python3 -c "
import json, sys
from datetime import datetime
events = json.load(sys.stdin)
today = '2026-03-02'
for e in sorted(events, key=lambda x: x['date']):
    if e['date'] >= today:
        print(f\"📅 {e['date']} - {e['title']}\")
        print(f\"   📍 {e['venue']} ({e['location']})\")
        if 'time' in e:
            print(f\"   🕐 {e['time']}\")
        if 'ticketLink' in e and e.get('soldOut'):
            print(f\"   🎫 SLUTSÅLT\")
        elif 'ticketLink' in e:
            print(f\"   🎫 Biljetter: {e['ticketLink']}\")
        elif 'link' in e:
            print(f\"   🔗 Läs mer: {e['link']}\")
        print()
" 2>/dev/null || echo "Could not parse events")

EMAIL_BODY="Hej David!

🔔 Ny veckas evenemang är nu live!

📅 Vecka $WEEK, $YEAR
🌐 ${SITE_URL}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 Kommande evenemang:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
${EVENT_LIST}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📍 Täckta områden:
• Karlstad • Forshaga • Kil • Molkom • Skattkärr • Väse • Vålberg • Deje

// Din OpenClaw-agent
"

# Commit changes to git
git add data/events.json layouts/ hugo.toml
git commit -m "Update events - $(date '+%Y-%m-%d')" 2>/dev/null || true
git push origin main 2>/dev/null || true

# Send email
/home/david/.openclaw/workspace/scripts/agentmail.sh send "david.nossebro@gmail.com" "Karlstad Events - Vecka $WEEK" "$EMAIL_BODY" 2>> "$LOG_FILE" || echo "Email send failed"

log "✅ Update complete!"
log "========================================="
