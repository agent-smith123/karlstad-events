#!/bin/bash
# Research events in Karlstad area
# Run: ./scripts/research-events.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONTENT_DIR="$PROJECT_DIR/content/events"
BUILD_HOOK="https://api.netlify.com/build_hooks/69a4aba1e906bcb08f79cbb2"

echo "🔍 Researching events in Karlstad area..."

# Track found events
EVENTS_FOUND=()

# Helper function to extract event info
extract_events() {
    local source="$1"
    local url="$2"
    
    echo "  Checking $source..."
    
    # Fetch page content
    content=$(curl -s "$url" 2>/dev/null || echo "")
    
    if [ -z "$content" ]; then
        echo "    No content fetched"
        return
    fi
    
    # Simple extraction - look for event patterns
    # This is a basic implementation - can be enhanced
    echo "    Found data from $source"
}

# Research from various sources
echo ""
echo "📡 Checking event sources..."

# 1. Wermland Opera
extract_events "Wermland Opera" "https://www.wermlandopera.com/evenemang/"

# 2. Nöjesfabriken  
extract_events "Nöjesfabriken" "https://www.nojesfabriken.se/nojeskalendern/"

# 3. Karlstad CCC
extract_events "Karlstad CCC" "https://www.karlstadccc.se/17/38/program-biljetter/"

# 4. Kulturhuset
extract_events "Kulturhuset" "https://kulturhusetstadsteatern.se/kalender"

# 5. StadsEvent
extract_events "StadsEvent" "https://stadsevent.se/karlstad/"

echo ""
echo "✅ Research complete. Found ${#EVENTS_FOUND[@]} potential events."

# For now, we'll just note the research was done
# Full automation of event extraction would require more sophisticated parsing
echo ""
echo "📝 Note: Manual event curation still needed for optimal quality."
echo "   Add new events as markdown files in content/events/"

# Commit any new content
cd "$PROJECT_DIR"
if [ -n "$(git status --porcelain)" ]; then
    echo ""
    echo "📦 Committing changes..."
    git add content/events/
    git commit -m "Add new events - $(date '+%Y-%m-%d')"
    git push origin main
    
    echo ""
    echo "🚀 Triggering Netlify build..."
    curl -s -X POST "$BUILD_HOOK" > /dev/null
    echo "   Build triggered!"
else
    echo ""
    echo "ℹ️ No new content to commit."
fi

echo ""
echo "✨ Research complete!"
