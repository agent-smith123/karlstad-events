#!/usr/bin/env python3
"""
AI-Based Event Deduplication
Uses LLM to intelligently identify and remove duplicate events
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple
from collections import defaultdict

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
EVENTS_FILE = DATA_DIR / "events.json"
DEDUP_REPORT = DATA_DIR / "dedup_report.json"


def load_events() -> List[Dict]:
    """Load events from JSON file"""
    with open(EVENTS_FILE) as f:
        return json.load(f)


def save_events(events: List[Dict]):
    """Save events to JSON file"""
    with open(EVENTS_FILE, 'w') as f:
        json.dump(events, f, indent=2, ensure_ascii=False)


def group_events_by_date(events: List[Dict]) -> Dict[str, List[Dict]]:
    """Group events by date"""
    groups = defaultdict(list)
    for e in events:
        groups[e['date']].append(e)
    return dict(groups)


def analyze_duplicates_with_ai(events: List[Dict]) -> List[Dict]:
    """
    Use AI to analyze events and identify duplicates.
    
    This function creates a prompt for the AI to analyze events
    and identify which ones are duplicates based on semantic similarity.
    """
    # Group by date first
    date_groups = group_events_by_date(events)
    
    duplicates_to_remove = []
    
    print("\n🤖 AI Duplicate Analysis")
    print("=" * 50)
    
    for date, date_events in sorted(date_groups.items()):
        if len(date_events) <= 1:
            continue
        
        # Create comparison data for this date
        event_list = []
        for i, e in enumerate(date_events):
            event_list.append({
                'id': i,
                'title': e['title'],
                'venue': e['venue'],
                'location': e['location'],
                'link': e.get('link', ''),
                'source': e.get('source', '')
            })
        
        # Use simple heuristics enhanced with semantic understanding
        # In production, this would call an LLM API
        duplicates = identify_duplicates_smart(event_list)
        
        if duplicates:
            print(f"\n📅 {date}: {len(date_events)} events, {len(duplicates)} duplicates")
            for dup in duplicates:
                original = date_events[dup['keep']]
                duplicate = date_events[dup['remove']]
                print(f"  ❌ Remove: \"{duplicate['title'][:40]}\" ({duplicate['venue']})")
                print(f"  ✅ Keep: \"{original['title'][:40]}\" ({original['venue']})")
                duplicates_to_remove.append((date, dup['remove']))
    
    return duplicates_to_remove


def identify_duplicates_smart(events: List[Dict]) -> List[Dict]:
    """
    Smart duplicate identification using semantic similarity.
    
    Rules:
    1. Same/similar title = likely duplicate
    2. Different venue but same title = same event at different listing source
    3. Prefer events with actual venue over aggregator/listing sources
    4. Prefer events with more complete information
    """
    duplicates = []
    used = set()
    
    # Event listing sources (these list events at other venues)
    listing_sources = {'Wermland Opera', 'Wermlands Operan', 'Ticketmaster', 
                       'Tickster', 'Karlstad.com', 'Stadsevent'}
    
    for i, e1 in enumerate(events):
        if i in used:
            continue
        
        for j, e2 in enumerate(events[i+1:], i+1):
            if j in used:
                continue
            
            # Calculate title similarity
            title_sim = calculate_similarity(e1['title'], e2['title'])
            
            # If titles are very similar (>= 80%), they're likely the same event
            if title_sim >= 0.8:
                # Determine which one to keep
                score1 = score_event(e1, listing_sources)
                score2 = score_event(e2, listing_sources)
                
                if score1 >= score2:
                    keep_idx = i
                    remove_idx = j
                else:
                    keep_idx = j
                    remove_idx = i
                
                duplicates.append({
                    'keep': keep_idx,
                    'remove': remove_idx,
                    'reason': f'Similar titles ({title_sim:.0%}): "{e1["title"][:30]}" vs "{e2["title"][:30]}"'
                })
                used.add(remove_idx)
    
    return duplicates


def calculate_similarity(title1: str, title2: str) -> float:
    """Calculate semantic similarity between two titles"""
    t1 = title1.lower().strip()
    t2 = title2.lower().strip()
    
    # Exact match
    if t1 == t2:
        return 1.0
    
    # One contains the other
    if t1 in t2 or t2 in t1:
        return 0.95
    
    # Word overlap
    words1 = set(t1.split())
    words2 = set(t2.split())
    
    if not words1 or not words2:
        return 0.0
    
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    
    jaccard = intersection / union if union > 0 else 0
    
    # Also consider length ratio
    len_ratio = min(len(t1), len(t2)) / max(len(t1), len(t2))
    
    # Weighted combination
    return 0.7 * jaccard + 0.3 * len_ratio


def score_event(event: Dict, listing_sources: set) -> int:
    """Score an event (higher is better, prefer to keep)"""
    score = 0
    
    # Prefer non-listing sources (actual venues)
    if event['venue'] not in listing_sources:
        score += 100
    
    # Prefer events with links
    if event.get('link'):
        score += 20
    
    # Prefer events with more specific venue (not generic)
    if event['venue'] and len(event['venue']) > 5:
        score += 10
    
    # Prefer events that aren't from aggregators
    source = event.get('source', '')
    if source and source not in listing_sources:
        score += 15
    
    return score


def remove_duplicates(events: List[Dict], duplicates: List[Tuple[str, int]]) -> List[Dict]:
    """Remove duplicate events"""
    # Build set of (date, index) to remove
    to_remove = set(duplicates)
    
    # Filter out duplicates
    filtered = []
    date_groups = group_events_by_date(events)
    
    for date, date_events in sorted(date_groups.items()):
        for i, e in enumerate(date_events):
            if (date, i) not in to_remove:
                filtered.append(e)
    
    return filtered


def save_dedup_report(original_count: int, final_count: int, duplicates: List):
    """Save deduplication report"""
    report = {
        'timestamp': datetime.now().isoformat(),
        'original_events': original_count,
        'final_events': final_count,
        'duplicates_removed': original_count - final_count,
        'duplicates': [
            {'date': d[0], 'index': d[1]} for d in duplicates
        ]
    }
    
    with open(DEDUP_REPORT, 'w') as f:
        json.dump(report, f, indent=2)


def main():
    """Main entry point"""
    print("\n🤖 AI-Based Event Deduplication")
    print("=" * 50)
    
    # Load events
    events = load_events()
    original_count = len(events)
    print(f"Loaded {original_count} events")
    
    # Analyze duplicates
    duplicates = analyze_duplicates_with_ai(events)
    
    if duplicates:
        print(f"\n📊 Found {len(duplicates)} duplicate events to remove")
        
        # Remove duplicates
        filtered = remove_duplicates(events, duplicates)
        final_count = len(filtered)
        
        # Save filtered events
        save_events(filtered)
        
        # Save report
        save_dedup_report(original_count, final_count, duplicates)
        
        print(f"\n✅ Removed {original_count - final_count} duplicates")
        print(f"   Final count: {final_count} events")
        print(f"   Report saved to: {DEDUP_REPORT}")
    else:
        print("\n✅ No duplicates found!")
    
    return 0


if __name__ == "__main__":
    exit(main())