#!/usr/bin/env python3
"""
Event Validation Script
Checks for duplicates, broken links, and old events
"""

import os
import re
import yaml
import requests
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urlparse
from collections import defaultdict

# Configuration
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
CONTENT_DIR = PROJECT_DIR / "content" / "events"
VENUES_FILE = SCRIPT_DIR / "venues.yaml"

def load_all_events():
    """Load all event markdown files"""
    events = []
    
    for md_file in CONTENT_DIR.glob("*.md"):
        if md_file.name == "_index.md":
            continue
            
        with open(md_file) as f:
            content = f.read()
        
        # Extract frontmatter
        frontmatter_match = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
        if not frontmatter_match:
            continue
            
        try:
            data = yaml.safe_load(frontmatter_match.group(1))
            data['filename'] = md_file.name
            data['filepath'] = str(md_file)
            events.append(data)
        except Exception as e:
            print(f"  ⚠️  Error parsing {md_file}: {e}")
    
    return events

def check_duplicates(events):
    """Check for duplicate events based on title + date + venue"""
    seen = defaultdict(list)
    duplicates = []
    
    for evt in events:
        key = f"{evt.get('title', '')}|{evt.get('date', '')}|{evt.get('venue', '')}"
        seen[key].append(evt)
    
    for key, evts in seen.items():
        if len(evts) > 1:
            duplicates.append({
                'key': key,
                'count': len(evts),
                'files': [e['filename'] for e in evts]
            })
    
    return duplicates

def check_old_events(events):
    """Check for events from previous years or far past"""
    today = datetime.now().date()
    old_events = []
    
    for evt in events:
        date_str = evt.get('date', '')
        if not date_str:
            continue
            
        try:
            if isinstance(date_str, datetime):
                evt_date = date_str.date()
            else:
                evt_date = datetime.strptime(str(date_str), '%Y-%m-%d').date()
            
            # Check if event is more than 30 days in the past
            if (today - evt_date).days > 30:
                old_events.append({
                    'title': evt.get('title', 'Unknown'),
                    'date': date_str,
                    'filename': evt['filename'],
                    'days_past': (today - evt_date).days
                })
        except Exception as e:
            print(f"  ⚠️  Error parsing date {date_str}: {e}")
    
    return old_events

def check_links(events, timeout=10):
    """Check if event links are valid (skips known auth-required sites)"""
    broken_links = []
    checked_urls = set()
    
    # Sites that block automated requests (401 expected)
    AUTH_REQUIRED_SITES = [
        'ticketmaster.se',
        'ticketmaster.com',
        'facebook.com',
        'fb.me'
    ]
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    
    for evt in events:
        link = evt.get('link')
        if not link:
            continue
            
        # Skip already checked URLs
        if link in checked_urls:
            continue
        checked_urls.add(link)
        
        # Skip sites known to require authentication
        domain = urlparse(link).netloc.lower()
        if any(auth_site in domain for auth_site in AUTH_REQUIRED_SITES):
            continue
        
        try:
            resp = session.head(link, timeout=timeout, allow_redirects=True)
            # Only report actual errors (not 401 from auth-required sites)
            if resp.status_code >= 400 and resp.status_code != 401:
                broken_links.append({
                    'title': evt.get('title', 'Unknown'),
                    'url': link,
                    'status': resp.status_code,
                    'filename': evt['filename']
                })
        except Exception as e:
            broken_links.append({
                'title': evt.get('title', 'Unknown'),
                'url': link,
                'status': 'ERROR',
                'error': str(e)[:50],
                'filename': evt['filename']
            })
    
    return broken_links

def remove_duplicate_files(duplicates, dry_run=True):
    """Remove duplicate event files, keeping the first one"""
    removed = []
    
    for dup in duplicates:
        files = dup['files']
        # Keep the first file, remove others
        for filename in files[1:]:
            filepath = CONTENT_DIR / filename
            if filepath.exists():
                if not dry_run:
                    filepath.unlink()
                removed.append(filename)
    
    return removed

def remove_old_event_files(old_events, dry_run=True):
    """Remove old event files"""
    removed = []
    
    for evt in old_events:
        filename = evt['filename']
        filepath = CONTENT_DIR / filename
        if filepath.exists():
            if not dry_run:
                filepath.unlink()
            removed.append({
                'filename': filename,
                'title': evt['title'],
                'date': evt['date']
            })
    
    return removed

def main():
    """Run all validations"""
    print("🔍 Event Validation")
    print("=" * 60)
    
    # Load all events
    print("\n📂 Loading events...")
    events = load_all_events()
    print(f"   Found {len(events)} event files")
    
    # Check for duplicates
    print("\n🔍 Checking for duplicates...")
    duplicates = check_duplicates(events)
    if duplicates:
        print(f"   ❌ Found {len(duplicates)} duplicate groups:")
        for dup in duplicates:
            print(f"      • {dup['key'][:60]}... ({dup['count']} copies)")
            for f in dup['files']:
                print(f"        - {f}")
    else:
        print("   ✅ No duplicates found")
    
    # Check for old events
    print("\n📅 Checking for old events...")
    old_events = check_old_events(events)
    if old_events:
        print(f"   ❌ Found {len(old_events)} old events:")
        for evt in old_events[:10]:  # Show first 10
            print(f"      • {evt['date']}: {evt['title'][:50]} ({evt['days_past']} days past)")
        if len(old_events) > 10:
            print(f"        ... and {len(old_events) - 10} more")
    else:
        print("   ✅ No old events found")
    
    # Check links
    print("\n🔗 Checking links (this may take a while)...")
    broken_links = check_links(events)
    if broken_links:
        print(f"   ❌ Found {len(broken_links)} broken links:")
        for link in broken_links[:10]:
            print(f"      • {link['status']}: {link['url'][:60]}")
        if len(broken_links) > 10:
            print(f"        ... and {len(broken_links) - 10} more")
    else:
        print("   ✅ All links working")
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Validation Summary")
    print("=" * 60)
    print(f"Total events: {len(events)}")
    print(f"Duplicates: {len(duplicates)}")
    print(f"Old events: {len(old_events)}")
    print(f"Broken links: {len(broken_links)}")
    
    issues = len(duplicates) + len(old_events) + len(broken_links)
    
    if issues == 0:
        print("\n✅ All checks passed!")
        return 0
    else:
        print(f"\n⚠️  Found {issues} issues")
        
        # Auto-fix option
        print("\n🔧 Auto-fix options:")
        print("1. Remove duplicate files")
        print("2. Remove old event files")
        print("3. Both")
        print("4. Skip (manual review)")
        
        return 1

if __name__ == "__main__":
    exit(main())
