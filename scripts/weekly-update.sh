#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$SCRIPT_DIR/weekly-update.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M')] $1" | tee -a "$LOG_FILE"; }

log "🔄 Weekly Karlstad Events Update"
cd "$PROJECT_DIR"

log "🏗️ Building..."
hugo >> "$LOG_FILE" 2>&1

log "🚀 Deploying..."
cd public && surge . karlstad-events.surge.sh >> "$LOG_FILE" 2>&1 && cd "$PROJECT_DIR"

SITE_URL="https://karlstad-events.surge.sh"
WEEK=$(date '+%W')
YEAR=$(date '+%Y')

EVENT_LIST=$(python3 -c "
import json
from datetime import datetime

with open('data/events.json') as f:
    events = json.load(f)

today = '2026-03-02'
for e in sorted(events, key=lambda x: x['date']):
    if e['date'] >= today:
        dt = datetime.strptime(e['date'], '%Y-%m-%d')
        week = dt.isocalendar()[1]
        weekday = ['Mån','Tis','Ons','Tor','Fre','Lör','Sön'][dt.weekday()]
        print(f\"📅 v{week} {e['date']} ({weekday})\")
        print(f\"   {e['title']}\")
        print(f\"   📍 {e['venue']}, {e['location']}\")
        if 'time' in e:
            print(f\"   🕐 {e['time']}\")
        if e.get('soldOut'):
            print(f\"   🎫 SLUTSÅLT\")
        elif 'ticketLink' in e:
            print(f\"   🎫 Biljetter: {e['ticketLink']}\")
        elif 'link' in e:
            print(f\"   🔗 {e['link']}\")
        print()
" 2>/dev/null)

EMAIL_BODY="Hej David!

🔔 Nya evenemang i Karlstad

📅 Vecka $WEEK, $YEAR
🌐 ${SITE_URL}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
$EVENT_LIST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📍 Områden: Karlstad, Forshaga, Kil, Munkfors, Molkom, Skattkärr, Väse, Vålberg, Deje, Ransäter, Sunne, Torsby, Grums, Säffle, Filipstad, Kristinehamn

// OpenClaw
"

git add data/events.json layouts/ hugo.toml
git commit -m "Update events - $(date '+%Y-%m-%d')" 2>/dev/null || true
git push origin main 2>/dev/null || true

/home/david/.openclaw/workspace/scripts/agentmail.sh send "david.nossebro@gmail.com" "Karlstad Events - Vecka $WEEK" "$EMAIL_BODY" 2>> "$LOG_FILE" || true

log "✅ Klart!"
