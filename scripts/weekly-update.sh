#!/bin/bash
# Weekly events update - runs every Monday at 03:00

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONTENT_DIR="$PROJECT_DIR/content/events"
LOG_FILE="$SCRIPT_DIR/weekly-update.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M')] $1" | tee -a "$LOG_FILE"
}

log "========================================="
log "🔄 Weekly Karlstad Events Update Started"

cd "$PROJECT_DIR"

# Step 1: Research new events (stub)
log "📡 Running event research..."

# Step 2: Build the site
log "🏗️ Building Hugo site..."
hugo --buildDrafts >> "$LOG_FILE" 2>&1

# Step 3: Check for changes
if [ -n "$(git status --porcelain)" ]; then
    log "📝 Changes detected, committing..."
    git add content/events/ public/ hugo.toml netlify.toml layouts/
    git commit -m "Weekly event update - $(date '+%Y-%m-%d')"
    git push origin main
    
    # Trigger Netlify build
    log "🚀 Triggering Netlify build..."
    curl -s -X POST "https://api.netlify.com/build_hooks/69a4aba1e906bcb08f79cbb2" >> "$LOG_FILE" 2>&1
    log "   Build triggered"
    
    # Step 4: Build and send email with event list
    log "📧 Building notification email..."
    
    SITE_URL="https://karlstad-events.netlify.app"
    WEEK=$(date '+%W')
    YEAR=$(date '+%Y')
    
    # Generate event list from markdown files
    EVENT_LIST=""
    for f in "$CONTENT_DIR"/*.markdown; do
        if [ -f "$f" ]; then
            # Extract frontmatter values - handle quoted and unquoted values
            title=$(grep "^title:" "$f" | head -1 | sed 's/title: *"\([^"]*\)"/\1/; s/title: *\([^ ]*\)/\1/' | tr -d '"')
            date=$(grep "^date:" "$f" | head -1 | sed 's/date: *"\([^"]*\)"/\1/; s/date: *\([^ ]*\)/\1/' | tr -d '"')
            venue=$(grep "^venue:" "$f" | head -1 | sed 's/venue: *"\([^"]*\)"/\1/; s/venue: *\([^ ]*\)/\1/' | tr -d '"')
            location=$(grep "^location:" "$f" | head -1 | sed 's/location: *"\([^"]*\)"/\1/; s/location: *\([^ ]*\)/\1/' | tr -d '"')
            time=$(grep "^time:" "$f" | head -1 | sed 's/time: *"\([^"]*\)"/\1/; s/time: *\([^ ]*\)/\1/' | tr -d '"')
            ticketLink=$(grep "^ticketLink:" "$f" | head -1 | sed 's/ticketLink: *"\([^"]*\)"/\1/; s/ticketLink: *\([^ ]*\)/\1/' | tr -d '"')
            link=$(grep "^link:" "$f" | head -1 | sed 's/link: *"\([^"]*\)"/\1/; s/link: *\([^ ]*\)/\1/' | tr -d '"')
            soldOut=$(grep "^soldOut:" "$f" | head -1 | sed 's/soldOut: *//; s/ //g' | tr -d '"')
            
            # Format the event entry
            if [ -n "$title" ]; then
                EVENT_LIST="${EVENT_LIST}\n📅 ${date} - ${title}"
                EVENT_LIST="${EVENT_LIST}\n   📍 ${venue} (${location})"
                [ -n "$time" ] && EVENT_LIST="${EVENT_LIST}\n   🕐 ${time}"
                
                # Add link info
                if [ "$soldOut" = "true" ]; then
                    EVENT_LIST="${EVENT_LIST}\n   🎫 SLUTSÅLT"
                elif [ -n "$ticketLink" ]; then
                    EVENT_LIST="${EVENT_LIST}\n   🎫 Biljetter: ${ticketLink}"
                elif [ -n "$link" ]; then
                    EVENT_LIST="${EVENT_LIST}\n   🔗 Läs mer: ${link}"
                fi
                EVENT_LIST="${EVENT_LIST}\n"
            fi
        fi
    done
    
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
    
    # Send via AgentMail
    /home/david/.openclaw/workspace/scripts/agentmail.sh send "david.nossebro@gmail.com" "Karlstad Events - Vecka $WEEK" "$EMAIL_BODY" 2>> "$LOG_FILE" || echo "Email send failed"
    
    log "✅ Update complete!"
else
    log "ℹ️ No changes to publish this week"
fi

log "========================================="
