#!/bin/bash
# Event Calendar Pipeline - Main Entry Point
# Orchestrates: Fetch → Validate → Deduplicate → Quality Gate → Publish
# Run: ./scripts/research-events.sh [--no-deploy]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PROJECT_DIR/data"
SURGE_DOMAIN="karlstad-events.surge.sh"
DEPLOY=true

# Parse arguments
for arg in "$@"; do
    if [ "$arg" = "--no-deploy" ]; then
        DEPLOY=false
    fi
done

echo "🎯 Karlstad Events Pipeline"
echo "====================================="
echo "📁 Project: $PROJECT_DIR"
echo "🌐 Deploy: $SURGE_DOMAIN"
echo "📅 Date: $(date '+%Y-%m-%d %H:%M')"
echo ""

# Check dependencies
echo "📦 Checking dependencies..."
if ! python3 -c "import requests" 2>/dev/null; then
    echo "⚠️  Installing Python dependencies..."
    pip3 install -q -r "$PROJECT_DIR/requirements.txt" || true
fi

if ! python3 -c "import yaml" 2>/dev/null; then
    echo "⚠️  Installing PyYAML..."
    pip3 install -q pyyaml || true
fi

# Check Hugo
if ! command -v hugo &> /dev/null; then
    echo "⚠️  Hugo not found"
    if [ "$(uname -m)" = "aarch64" ]; then
        echo "   Installing Hugo for ARM64..."
        wget -q https://github.com/gohugoio/hugo/releases/download/v0.123.0/hugo_extended_0.123.0_linux-arm64.tar.gz -O /tmp/hugo.tar.gz
        tar -xzf /tmp/hugo.tar.gz -C /tmp
        sudo mv /tmp/hugo /usr/local/bin/ 2>/dev/null || mv /tmp/hugo "$PROJECT_DIR/hugo"
    fi
fi

# Run the new unified pipeline
echo ""
echo "🚀 Running unified pipeline..."
python3 "$SCRIPT_DIR/pipeline.py" || {
    echo "❌ Pipeline failed"
    
    # Log failure for AI fallback
    echo "📝 Logging failure for AI fallback..."
    python3 "$SCRIPT_DIR/ai_fallback.py"
    
    exit 1
}

# Git commit
echo ""
echo "📦 Committing changes..."
cd "$PROJECT_DIR"
git add -A
git diff --cached --quiet || git commit -m "Auto: Event pipeline $(date '+%Y-%m-%d %H:%M')"
git push origin main 2>/dev/null || echo "⚠️  Git push failed (continuing anyway)"

# Deploy to Surge.sh
if [ "$DEPLOY" = true ]; then
    echo ""
    echo "🚀 Deploying to Surge.sh..."
    if surge ./public --domain "$SURGE_DOMAIN" 2>/dev/null; then
        echo "✅ Deployed to https://$SURGE_DOMAIN"
    else
        echo "⚠️  Surge deploy may have failed - check manually"
    fi
else
    echo ""
    echo "⏭️  Skipping deployment (--no-deploy)"
fi

# Summary
echo ""
echo "✨ Pipeline Complete!"
echo "   📊 Events: $(jq length "$DATA_DIR/events.json" 2>/dev/null || echo '?')"
echo "   🔗 URL: https://$SURGE_DOMAIN"
