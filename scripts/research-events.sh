#!/bin/bash
# Enhanced Event Research for Karlstad Area
# Multi-source aggregation with AI fallback and Surge.sh deployment
# Run: ./scripts/research-events.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SURGE_DOMAIN="karlstad-events.surge.sh"
MAX_RETRIES=3
RESEARCH_SUCCESS=false

echo "🔍 Enhanced Karlstad Events Research"
echo "====================================="
echo "📁 Project: $PROJECT_DIR"
echo "🌐 Deploy: $SURGE_DOMAIN"
echo "📅 Date: $(date '+%Y-%m-%d %H:%M')"
echo ""

# Function to run research with retry and fallback
try_research() {
    local attempt=1
    local method="$1"
    
    while [ $attempt -le $MAX_RETRIES ]; do
        echo "  Attempt $attempt/$MAX_RETRIES using $method..."
        
        if [ "$method" = "automated" ]; then
            if python3 "$SCRIPT_DIR/enhanced_research.py"; then
                return 0
            fi
        elif [ "$method" = "ai-agent" ]; then
            echo "  🤖 Falling back to AI agent data fetching..."
            # Create a marker file that the AI agent will detect
            touch "$DATA_DIR/.ai-fetch-requested"
            echo "  📧 AI fetch requested - check your messages for results"
            return 0
        fi
        
        echo "  ⚠️  Attempt $attempt failed, waiting before retry..."
        sleep 5
        attempt=$((attempt + 1))
    done
    
    return 1
}

# Check dependencies
echo "📦 Checking dependencies..."
if ! python3 -c "import requests" 2>/dev/null; then
    echo "⚠️  Installing Python dependencies..."
    pip3 install -q -r "$PROJECT_DIR/requirements.txt" || true
fi

# Ensure Hugo is available for site generation
if ! command -v hugo &> /dev/null; then
    echo "⚠️  Hugo not found, installing..."
    # For Raspberry Pi ARM64
    wget -q https://github.com/gohugoio/hugo/releases/download/v0.123.0/hugo_extended_0.123.0_linux-arm64.tar.gz -O /tmp/hugo.tar.gz
    tar -xzf /tmp/hugo.tar.gz -C /tmp
    sudo mv /tmp/hugo /usr/local/bin/ 2>/dev/null || mv /tmp/hugo "$PROJECT_DIR/hugo"
fi

# Run enhanced research with fallback
echo ""
echo "🚀 Running enhanced research..."
if try_research "automated"; then
    RESEARCH_SUCCESS=true
    echo "✅ Automated research succeeded"
else
    echo "⚠️  Automated research failed after $MAX_RETRIES attempts"
    echo "🤖 Switching to AI agent fallback..."
    try_research "ai-agent"
fi

# Generate Hugo site
echo ""
echo "🏗️  Building Hugo site..."
cd "$PROJECT_DIR"
if [ -f "$PROJECT_DIR/hugo" ]; then
    "$PROJECT_DIR/hugo" --buildFuture --minify || hugo --buildFuture --minify
else
    hugo --buildFuture --minify
fi

# Commit any new content
echo ""
echo "📦 Committing changes..."
git add -A
git diff --cached --quiet || git commit -m "Auto: Event research $(date '+%Y-%m-%d')"
git push origin main || echo "⚠️  Git push failed (continuing anyway)"

# Deploy to Surge.sh
echo ""
echo "🚀 Deploying to Surge.sh..."
if surge ./public --domain "$SURGE_DOMAIN" --token "$SURGE_TOKEN" 2>/dev/null || \
   surge ./public --domain "$SURGE_DOMAIN"; then
    echo "✅ Deployed to https://$SURGE_DOMAIN"
else
    echo "⚠️  Surge deploy may have failed - check manually"
fi

# Update discovery log
echo ""
echo "🔍 Venue Discovery Status"
echo "========================="
if [ -f "$PROJECT_DIR/data/new-sources.json" ]; then
    NEW_COUNT=$(jq '.venues | length' "$PROJECT_DIR/data/new-sources.json" 2>/dev/null || echo "0")
    echo "📋 $NEW_COUNT new sources pending review"
fi

echo ""
echo "✨ Done! Visit: https://$SURGE_DOMAIN"
