#!/usr/bin/env python3
"""
Auto-Fix System for Broken Scrapers
Automatically detects failures, analyzes issues, and applies fixes
"""

import os
import re
import json
import yaml
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
VENUES_FILE = SCRIPT_DIR / "venues.yaml"
SCRAPER_STATE_FILE = DATA_DIR / "scraper_state.json"
FIX_LOG_FILE = DATA_DIR / "auto_fix_log.json"


class AutoFixer:
    """Automatically fixes broken scrapers"""
    
    COMMON_ISSUES = {
        'timeout': {
            'pattern': r'timeout|timed out',
            'fix': 'increase_timeout'
        },
        '404_not_found': {
            'pattern': r'404|not found',
            'fix': 'check_url'
        },
        'ssl_error': {
            'pattern': r'ssl|certificate|verify',
            'fix': 'disable_ssl_verify'
        },
        'parse_error': {
            'pattern': r'parse|selector|element not found',
            'fix': 'update_selectors'
        },
        'connection_error': {
            'pattern': r'connection|refused|reset',
            'fix': 'add_retry'
        }
    }
    
    def __init__(self):
        self.fixes_applied = []
        self.load_fix_log()
    
    def load_fix_log(self):
        """Load history of applied fixes"""
        if FIX_LOG_FILE.exists():
            with open(FIX_LOG_FILE) as f:
                data = json.load(f)
                self.fixes_applied = data.get('fixes', [])
    
    def save_fix_log(self):
        """Save fix history"""
        with open(FIX_LOG_FILE, 'w') as f:
            json.dump({
                'last_updated': datetime.now().isoformat(),
                'fixes': self.fixes_applied
            }, f, indent=2)
    
    def analyze_failure(self, scraper_name: str, error: str) -> Optional[str]:
        """Analyze error and determine fix type"""
        error_lower = error.lower()
        
        for issue_type, config in self.COMMON_ISSUES.items():
            if re.search(config['pattern'], error_lower):
                return config['fix']
        
        return None
    
    def apply_fix(self, scraper_name: str, fix_type: str, venues: dict) -> bool:
        """Apply a fix to the scraper configuration"""
        print(f"  🔧 Applying fix '{fix_type}' to {scraper_name}")
        
        # Find venue config
        venue_config = None
        venue_key = None
        for tier, venues_in_tier in venues.items():
            if scraper_name in venues_in_tier:
                venue_config = venues_in_tier[scraper_name]
                venue_key = scraper_name
                break
        
        if not venue_config:
            print(f"    ❌ Venue config not found")
            return False
        
        fix_applied = False
        
        if fix_type == 'increase_timeout':
            # Add or increase timeout setting
            if 'scraper' not in venue_config:
                venue_config['scraper'] = {}
            venue_config['scraper']['timeout'] = 60  # Increase to 60s
            fix_applied = True
            
        elif fix_type == 'add_retry':
            # Add retry configuration
            if 'scraper' not in venue_config:
                venue_config['scraper'] = {}
            venue_config['scraper']['retries'] = 3
            fix_applied = True
            
        elif fix_type == 'check_url':
            # Mark for URL verification
            venue_config['needs_url_check'] = True
            fix_applied = True
            
        elif fix_type == 'update_selectors':
            # Try alternative selectors
            current_selectors = venue_config.get('scraper', {}).get('selectors', {})
            
            # Add fallback selectors
            fallback_selectors = {
                'event': ['article', '.event', '[class*="event"]', 'div.item', '.post'],
                'title': ['h1', 'h2', 'h3', '.title', '.heading'],
                'date': ['time', '.date', '.datetime', '[class*="date"]'],
                'link': ['a[href]', 'a']
            }
            
            if 'scraper' not in venue_config:
                venue_config['scraper'] = {}
            
            # Merge with fallbacks
            for key, values in fallback_selectors.items():
                if key not in current_selectors:
                    venue_config['scraper'][f'fallback_{key}'] = values
            
            fix_applied = True
        
        if fix_applied:
            self.fixes_applied.append({
                'timestamp': datetime.now().isoformat(),
                'scraper': scraper_name,
                'fix_type': fix_type,
                'venue': venue_config.get('name', scraper_name)
            })
            
            # Save updated venues
            with open(VENUES_FILE, 'w') as f:
                yaml.dump(venues, f, allow_unicode=True, sort_keys=False)
            
            print(f"    ✓ Fix applied")
            return True
        
        return False
    
    def check_and_fix(self, max_fixes_per_run: int = 5) -> List[Dict]:
        """Check for failing scrapers and apply fixes"""
        print("🔧 Auto-Fix System")
        print("=" * 40)
        
        if not SCRAPER_STATE_FILE.exists():
            print("  ℹ️ No scraper state found - nothing to fix")
            return []
        
        # Load scraper state
        with open(SCRAPER_STATE_FILE) as f:
            state = json.load(f)
        
        # Load venues
        with open(VENUES_FILE) as f:
            venues = yaml.safe_load(f)
        
        fixes_made = []
        fix_count = 0
        
        for scraper_name, stats in state.items():
            if fix_count >= max_fixes_per_run:
                print(f"\n  ⏹️ Reached max fixes per run ({max_fixes_per_run})")
                break
            
            consecutive_failures = stats.get('consecutive_failures', 0)
            last_error = stats.get('last_error', '')
            
            # Only fix after 2 consecutive failures
            if consecutive_failures < 2:
                continue
            
            print(f"\n  📍 {scraper_name}: {consecutive_failures} failures")
            
            # Analyze error
            fix_type = self.analyze_failure(scraper_name, last_error)
            
            if fix_type:
                print(f"    Detected issue: {fix_type}")
                
                if self.apply_fix(scraper_name, fix_type, venues):
                    fixes_made.append({
                        'scraper': scraper_name,
                        'fix': fix_type,
                        'error': last_error[:100]
                    })
                    fix_count += 1
            else:
                print(f"    ⚠️ Unknown error pattern - manual intervention needed")
                print(f"    Error: {last_error[:100]}...")
        
        # Save fix log
        self.save_fix_log()
        
        print(f"\n✅ Applied {len(fixes_made)} fixes")
        return fixes_made
    
    def get_fix_report(self) -> str:
        """Generate report of recent fixes"""
        if not self.fixes_applied:
            return "No fixes have been applied yet."
        
        report = ["Recent Fixes Applied:", "=" * 40]
        
        # Show last 10 fixes
        for fix in self.fixes_applied[-10:]:
            report.append(f"• {fix['timestamp'][:10]}: {fix['venue']} - {fix['fix_type']}")
        
        return "\n".join(report)


def main():
    """Run auto-fix system"""
    fixer = AutoFixer()
    fixes = fixer.check_and_fix()
    
    if fixes:
        print("\n📋 Fix Summary:")
        for fix in fixes:
            print(f"  • {fix['scraper']}: {fix['fix']}")
    
    print("\n" + fixer.get_fix_report())


if __name__ == "__main__":
    main()
