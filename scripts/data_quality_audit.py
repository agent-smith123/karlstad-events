#!/usr/bin/env python3
"""
Deep Data Quality Audit
Analyzes events for quality issues, potential duplicates, and verification needs
"""

import os
import re
import json
import yaml
import requests
from pathlib import Path
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from urllib.parse import urlparse
from collections import defaultdict

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
CONTENT_DIR = PROJECT_DIR / "content" / "events"
DATA_DIR = PROJECT_DIR / "data"
QUALITY_REPORT = DATA_DIR / "quality_report.json"

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
            data['content'] = content
            events.append(data)
        except Exception as e:
            print(f"  ⚠️  Error parsing {md_file}: {e}")
    
    return events

def normalize_title(title):
    """Normalize title for comparison"""
    if not title:
        return ""
    # Lowercase, remove punctuation, extra spaces
    normalized = title.lower()
    normalized = re.sub(r'[^\w\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized

def find_similar_events(events, threshold=0.85):
    """Find events with similar titles (potential duplicates)"""
    similar_groups = []
    checked = set()
    
    for i, evt1 in enumerate(events):
        if i in checked:
            continue
            
        title1 = normalize_title(evt1.get('title', ''))
        if not title1:
            continue
            
        group = [evt1]
        checked.add(i)
        
        for j, evt2 in enumerate(events[i+1:], start=i+1):
            if j in checked:
                continue
                
            title2 = normalize_title(evt2.get('title', ''))
            if not title2:
                continue
            
            # Check similarity
            similarity = SequenceMatcher(None, title1, title2).ratio()
            
            # Also check if dates are the same or close
            date1 = str(evt1.get('date', ''))
            date2 = str(evt2.get('date', ''))
            same_date = date1 == date2
            
            if similarity >= threshold or (similarity >= 0.7 and same_date):
                group.append(evt2)
                checked.add(j)
        
        if len(group) > 1:
            similar_groups.append({
                'similarity': similarity,
                'events': group
            })
    
    return similar_groups

def check_ticket_links(events):
    """Check which events have ticket links"""
    no_tickets = []
    has_tickets = []
    
    for evt in events:
        link = evt.get('link')
        title = evt.get('title', 'Unknown')
        
        if link and ('ticket' in link.lower() or 'biljett' in link.lower()):
            has_tickets.append({
                'title': title,
                'link': link,
                'filename': evt['filename']
            })
        else:
            no_tickets.append({
                'title': title,
                'link': link,
                'filename': evt['filename'],
                'venue': evt.get('venue', '')
            })
    
    return has_tickets, no_tickets

def verify_event_exists(event):
    """Try to verify an event exists by checking its source"""
    link = event.get('link')
    venue = event.get('venue', '')
    title = event.get('title', '')
    
    if not link:
        return {
            'verifiable': False,
            'reason': 'No link provided',
            'confidence': 'low'
        }
    
    # Skip known auth-required sites
    domain = urlparse(link).netloc.lower()
    auth_sites = ['ticketmaster.se', 'facebook.com', 'fb.me']
    if any(site in domain for site in auth_sites):
        return {
            'verifiable': True,
            'reason': f'Link to {domain} (auth required)',
            'confidence': 'medium'
        }
    
    # Try to fetch the page
    try:
        resp = requests.head(link, timeout=10, allow_redirects=True)
        if resp.status_code == 200:
            return {
                'verifiable': True,
                'reason': 'Page accessible',
                'confidence': 'high'
            }
        elif resp.status_code == 404:
            return {
                'verifiable': False,
                'reason': 'Page not found (404)',
                'confidence': 'high'
            }
        else:
            return {
                'verifiable': False,
                'reason': f'HTTP {resp.status_code}',
                'confidence': 'medium'
            }
    except Exception as e:
        return {
            'verifiable': False,
            'reason': f'Error: {str(e)[:50]}',
            'confidence': 'low'
        }

def analyze_data_quality(events):
    """Perform comprehensive data quality analysis"""
    report = {
        'timestamp': datetime.now().isoformat(),
        'total_events': len(events),
        'issues': []
    }
    
    # Find similar events (potential duplicates)
    print("\n🔍 Checking for similar events...")
    similar = find_similar_events(events)
    if similar:
        print(f"   ⚠️  Found {len(similar)} groups of similar events:")
        for group in similar:
            evts = group['events']
            print(f"\n   Similarity: {group['similarity']:.2f}")
            for evt in evts:
                print(f"      • {evt.get('date')} | {evt.get('title')[:50]}")
                print(f"        File: {evt['filename']}")
        report['similar_events'] = [
            {
                'similarity': g['similarity'],
                'count': len(g['events']),
                'titles': [e.get('title') for e in g['events']],
                'files': [e['filename'] for e in g['events']]
            }
            for g in similar
        ]
    else:
        print("   ✅ No similar events found")
    
    # Check ticket links
    print("\n🎫 Checking ticket links...")
    has_tickets, no_tickets = check_ticket_links(events)
    print(f"   Events with tickets: {len(has_tickets)}")
    print(f"   Events without tickets: {len(no_tickets)}")
    
    if no_tickets:
        print("\n   Events missing ticket links:")
        for evt in no_tickets[:5]:
            print(f"      • {evt['title'][:50]} ({evt['venue']})")
    
    report['ticket_links'] = {
        'with_tickets': len(has_tickets),
        'without_tickets': len(no_tickets),
        'missing_ticket_list': [
            {'title': e['title'], 'venue': e['venue'], 'file': e['filename']}
            for e in no_tickets
        ]
    }
    
    # Verify events
    print("\n✅ Verifying events...")
    unverified = []
    verified = []
    
    for evt in events[:10]:  # Check first 10 to avoid rate limiting
        result = verify_event_exists(evt)
        if result['verifiable']:
            verified.append({
                'title': evt.get('title'),
                'confidence': result['confidence']
            })
        else:
            unverified.append({
                'title': evt.get('title'),
                'reason': result['reason'],
                'filename': evt['filename']
            })
    
    report['verification'] = {
        'verified_sample': len(verified),
        'unverified_sample': len(unverified),
        'unverified_list': unverified
    }
    
    return report

def generate_recommendations(report):
    """Generate recommendations based on audit results"""
    recommendations = []
    
    if 'similar_events' in report:
        recommendations.append({
            'priority': 'high',
            'issue': 'Potential duplicates detected',
            'action': 'Review similar event groups and merge or remove duplicates',
            'count': len(report['similar_events'])
        })
    
    missing_tickets = report.get('ticket_links', {}).get('without_tickets', 0)
    if missing_tickets > 0:
        recommendations.append({
            'priority': 'medium',
            'issue': 'Events missing ticket links',
            'action': f'Research and add ticket links for {missing_tickets} events',
            'count': missing_tickets
        })
    
    unverified = report.get('verification', {}).get('unverified_list', [])
    if unverified:
        recommendations.append({
            'priority': 'high',
            'issue': 'Unverified events',
            'action': 'Verify events exist at their source URLs',
            'count': len(unverified)
        })
    
    return recommendations

def main():
    """Run comprehensive data quality audit"""
    print("🔬 Deep Data Quality Audit")
    print("=" * 60)
    
    events = load_all_events()
    print(f"📊 Loaded {len(events)} events")
    
    report = analyze_data_quality(events)
    recommendations = generate_recommendations(report)
    
    report['recommendations'] = recommendations
    
    # Save report
    with open(QUALITY_REPORT, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print("\n" + "=" * 60)
    print("📋 Recommendations")
    print("=" * 60)
    
    for rec in sorted(recommendations, key=lambda x: x['priority']):
        print(f"\n[{rec['priority'].upper()}] {rec['issue']}")
        print(f"   Action: {rec['action']}")
        print(f"   Affected: {rec['count']} events")
    
    print(f"\n💾 Full report saved to: {QUALITY_REPORT}")
    
    return len(recommendations)

if __name__ == "__main__":
    exit(main())
