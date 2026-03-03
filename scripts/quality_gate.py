#!/usr/bin/env python3
"""
Quality Gate - Pre-publication event verification
Ensures high data quality before events are published
"""

import os
import re
import json
import yaml
import hashlib
import requests
from pathlib import Path
from datetime import datetime, timedelta, timedelta
from difflib import SequenceMatcher
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
CONTENT_DIR = PROJECT_DIR / "content" / "events"
DATA_DIR = PROJECT_DIR / "data"
QUALITY_LOG = DATA_DIR / "quality_gate_log.json"

class QualityGate:
    """Pre-publication quality verification"""
    
    def __init__(self):
        self.existing_events = self._load_existing_events()
        self.issues = []
        self.verified = []
        self.rejected = []
    
    def _load_existing_events(self):
        """Load all existing events for duplicate checking"""
        events = {}
        
        for md_file in CONTENT_DIR.glob("*.md"):
            if md_file.name == "_index.md":
                continue
            
            with open(md_file) as f:
                content = f.read()
            
            frontmatter_match = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
            if not frontmatter_match:
                continue
            
            try:
                data = yaml.safe_load(frontmatter_match.group(1))
                # Create normalized key
                key = self._normalize_key(
                    data.get('title', ''),
                    data.get('date', ''),
                    data.get('venue', '')
                )
                events[key] = {
                    'title': data.get('title'),
                    'date': data.get('date'),
                    'venue': data.get('venue'),
                    'filename': md_file.name
                }
            except Exception as e:
                print(f"  ⚠️  Error loading {md_file}: {e}")
        
        return events
    
    def _normalize_key(self, title, date, venue):
        """Create normalized key for duplicate detection"""
        title_norm = re.sub(r'[^\w\s]', '', str(title).lower()).strip()
        venue_norm = re.sub(r'[^\w\s]', '', str(venue).lower()).strip()
        return f"{title_norm}|{date}|{venue_norm}"
    
    def check_duplicate(self, title, date, venue, current_filename=None):
        """Check if event is a duplicate (excluding itself)"""
        key = self._normalize_key(title, date, venue)
        
        if key in self.existing_events:
            existing = self.existing_events[key]
            # Don't flag as duplicate if it's the same file
            if existing['filename'] == current_filename:
                return {'is_duplicate': False}
            
            return {
                'is_duplicate': True,
                'existing_file': existing['filename'],
                'similarity': 1.0
            }
        
        # Check for similar titles on same date (excluding self)
        for existing_key, existing in self.existing_events.items():
            if existing['filename'] == current_filename:
                continue
            if str(existing.get('date')) == str(date):
                title_sim = SequenceMatcher(None, 
                    str(title).lower(), 
                    str(existing.get('title', '')).lower()
                ).ratio()
                
                if title_sim >= 0.85:
                    return {
                        'is_duplicate': True,
                        'existing_file': existing['filename'],
                        'similarity': title_sim,
                        'reason': f"Similar title ({title_sim:.0%}) on same date"
                    }
        
        return {'is_duplicate': False}
    
    def verify_link(self, link):
        """Verify that a link is accessible"""
        if not link:
            return {
                'valid': False,
                'reason': 'No link provided'
            }
        
        # Skip known auth-required sites
        domain = urlparse(link).netloc.lower()
        auth_sites = ['ticketmaster.se', 'facebook.com', 'fb.me', 'tickster.com']
        cultural_sites = ['wermlandopera.com', 'karlstadccc.se', 'varmlandsmuseum.se']
        
        if any(site in domain for site in auth_sites):
            return {
                'valid': True,
                'reason': f'Link to {domain} (auth site - assumed valid)',
                'confidence': 'medium'
            }
        
        # Try to fetch
        try:
            resp = requests.head(link, timeout=10, allow_redirects=True)
            if resp.status_code == 200:
                return {
                    'valid': True,
                    'reason': 'Page accessible',
                    'confidence': 'high'
                }
            elif resp.status_code == 403:
                # Some sites block automated requests but links are valid
                if any(site in domain for site in cultural_sites):
                    return {
                        'valid': True,
                        'reason': f'Link to {domain} (blocked but likely valid)',
                        'confidence': 'medium'
                    }
                return {
                    'valid': False,
                    'reason': 'Access denied (403)',
                    'confidence': 'low'
                }
            elif resp.status_code == 404:
                return {
                    'valid': False,
                    'reason': 'Page not found (404)',
                    'confidence': 'high'
                }
            else:
                return {
                    'valid': False,
                    'reason': f'HTTP {resp.status_code}',
                    'confidence': 'medium'
                }
        except Exception as e:
            return {
                'valid': False,
                'reason': f'Error: {str(e)[:50]}',
                'confidence': 'low'
            }
    
    def validate_event(self, event_data, filename=None):
        """Validate a single event"""
        issues = []
        warnings = []
        
        title = event_data.get('title', '')
        date = event_data.get('date', '')
        venue = event_data.get('venue', '')
        link = event_data.get('link') or event_data.get('ticketLink')
        
        # Get current year for validation
        current_year = datetime.now().year
        current_date = datetime.now().date()
        
        # Check for duplicates (pass filename to exclude self)
        dup_check = self.check_duplicate(title, date, venue, filename)
        if dup_check['is_duplicate']:
            issues.append({
                'type': 'duplicate',
                'severity': 'high',
                'message': f"Duplicate of {dup_check['existing_file']} ({dup_check.get('similarity', 1.0):.0%} match)",
                'existing_file': dup_check['existing_file']
            })
        
        # Check for year validation - reject events from previous years
        if date:
            try:
                event_date = datetime.strptime(str(date), '%Y-%m-%d').date()
                event_year = event_date.year
                
                # Reject events from previous years
                if event_year < current_year:
                    issues.append({
                        'type': 'old_year',
                        'severity': 'high',
                        'message': f"Event is from year {event_year} (current: {current_year}) - should be removed"
                    })
                
                # Warn about events too far in the past (but same year)
                elif event_date < current_date - timedelta(days=30):
                    warnings.append({
                        'type': 'past_event',
                        'severity': 'medium',
                        'message': f"Event date {event_date} is more than 30 days in the past"
                    })
            except Exception as e:
                issues.append({
                    'type': 'invalid_date',
                    'severity': 'medium',
                    'message': f"Could not parse date: {date}"
                })
        
        # Check for link
        if not link:
            warnings.append({
                'type': 'missing_link',
                'severity': 'medium',
                'message': 'No ticket/info link provided'
            })
        else:
            # Verify link
            link_check = self.verify_link(link)
            if not link_check['valid']:
                issues.append({
                    'type': 'invalid_link',
                    'severity': 'high',
                    'message': f"Link verification failed: {link_check['reason']}"
                })
            elif link_check['confidence'] == 'low':
                warnings.append({
                    'type': 'unverified_link',
                    'severity': 'low',
                    'message': f"Link could not be verified: {link_check['reason']}"
                })
        
        # Check for required fields
        if not title:
            issues.append({
                'type': 'missing_field',
                'severity': 'high',
                'message': 'Missing title'
            })
        
        if not date:
            issues.append({
                'type': 'missing_field',
                'severity': 'high',
                'message': 'Missing date'
            })
        
        # Check for ALL CAPS titles (poor quality)
        if title and title.isupper() and len(title) > 10:
            warnings.append({
                'type': 'formatting',
                'severity': 'low',
                'message': 'Title is ALL CAPS - consider normalizing'
            })
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings
        }
    
    def process_new_events(self, event_files):
        """Process and validate new event files"""
        results = {
            'processed': 0,
            'approved': 0,
            'rejected': 0,
            'warnings': 0,
            'details': []
        }
        
        for filepath in event_files:
            results['processed'] += 1
            
            with open(filepath) as f:
                content = f.read()
            
            frontmatter_match = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
            if not frontmatter_match:
                continue
            
            try:
                event_data = yaml.safe_load(frontmatter_match.group(1))
                validation = self.validate_event(event_data, filepath.name)
                
                if validation['valid']:
                    results['approved'] += 1
                    self.verified.append({
                        'file': filepath.name,
                        'title': event_data.get('title'),
                        'warnings': len(validation['warnings'])
                    })
                else:
                    results['rejected'] += 1
                    self.rejected.append({
                        'file': filepath.name,
                        'title': event_data.get('title'),
                        'issues': validation['issues']
                    })
                
                if validation['warnings']:
                    results['warnings'] += 1
                
                results['details'].append({
                    'file': filepath.name,
                    'title': event_data.get('title'),
                    'valid': validation['valid'],
                    'issues': validation['issues'],
                    'warnings': validation['warnings']
                })
                
            except Exception as e:
                results['rejected'] += 1
                self.rejected.append({
                    'file': filepath.name,
                    'error': str(e)
                })
        
        return results
    
    def save_log(self):
        """Save quality gate log"""
        log = {
            'timestamp': datetime.now().isoformat(),
            'verified': self.verified,
            'rejected': self.rejected,
            'summary': {
                'total_verified': len(self.verified),
                'total_rejected': len(self.rejected)
            }
        }
        
        with open(QUALITY_LOG, 'w') as f:
            json.dump(log, f, indent=2)
        
        return log


def main():
    """Run quality gate on all events"""
    print("🔒 Quality Gate - Pre-publication Verification")
    print("=" * 60)
    
    gate = QualityGate()
    
    # Get all event files
    event_files = list(CONTENT_DIR.glob("*.md"))
    event_files = [f for f in event_files if f.name != "_index.md"]
    
    print(f"\n📂 Processing {len(event_files)} events...")
    
    results = gate.process_new_events(event_files)
    log = gate.save_log()
    
    print(f"\n✅ Approved: {results['approved']}")
    print(f"❌ Rejected: {results['rejected']}")
    print(f"⚠️  With warnings: {results['warnings']}")
    
    if gate.rejected:
        print(f"\n🚫 Rejected Events:")
        for rej in gate.rejected:
            print(f"   • {rej.get('file', 'unknown')}: {rej.get('title', 'unknown')}")
            for issue in rej.get('issues', []):
                print(f"      - [{issue['severity']}] {issue['message']}")
    
    if gate.verified:
        print(f"\n✅ Verified Events:")
        for ver in gate.verified[:5]:  # Show first 5
            print(f"   • {ver['file']}: {ver['title'][:50]}")
        if len(gate.verified) > 5:
            print(f"   ... and {len(gate.verified) - 5} more")
    
    print(f"\n💾 Log saved to: {QUALITY_LOG}")
    
    return 0 if results['rejected'] == 0 else 1


if __name__ == "__main__":
    exit(main())
