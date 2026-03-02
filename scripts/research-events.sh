#!/bin/bash
# Enhanced Event Research for Karlstad Area
# Multi-source aggregation: APIs, venue websites, aggregators
# Run: ./scripts/research-events.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_HOOK="https://api.netlify.com/build_hooks/69a4aba1e906bcb08f79cbb2"

echo "🔍 Enhanced Karlstad Events Research"
echo "====================================="
echo "📁 Project: $PROJECT_DIR"
echo "📅 Date: $(date '+%Y-%m-%d %H:%M')"
echo ""

# Check dependencies
echo "📦 Checking dependencies..."
if ! python3 -c "import requests" 2>/dev/null; then
    echo "⚠️  Installing dependencies..."
    pip3 install -q -r "$PROJECT_DIR/requirements.txt"
fi

# Run enhanced research
echo ""
echo "🚀 Running enhanced research..."
python3 "$SCRIPT_DIR/enhanced_research.py"
RESULT=$?

if [ $RESULT -eq 0 ]; then
    echo ""
    echo "✅ Research completed successfully!"
    
    # Commit any new content
    cd "$PROJECT_DIR"
    if [ -n "$(git status --porcelain)" ]; then
        echo ""
        echo "📦 Committing changes..."
        git add -A
        git commit -m "Auto: Event research $(date '+%Y-%m-%d')"
        git push origin main
    fi
    
    # Trigger Netlify build
    echo ""
    echo "🌐 Triggering Netlify build..."
    if curl -s -X POST "$BUILD_HOOK" > /dev/null; then
        echo "✅ Build triggered!"
    else
        echo "⚠️  Build hook failed (site will update on next commit)"
    fi
else
    echo ""
    echo "❌ Research failed with exit code $RESULT"
    exit $RESULT
fi

echo ""
echo "✨ Done! Visit: https://karlstad-events.netlify.app"
