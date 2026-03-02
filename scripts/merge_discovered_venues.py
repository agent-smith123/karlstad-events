#!/usr/bin/env python3
"""
Merge discovered venues from subagent results into venues.yaml
"""

import json
import yaml
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
VENUES_FILE = SCRIPT_DIR / "venues.yaml"

# Files to process
DISCOVERY_FILES = [
    "discovered_karlstad.json",
    "discovered_forshaga_kil.json",
    "discovered_molkom_skattkarr.json",
    "discovered_vase_valberg_deje.json",
    "discovered_hammaro_kristinehamn.json",
    "discovered_sunne_torsby_arjang.json",
    "discovered_saffle_arvika_grums.json",
]


def load_venues():
    """Load current venues.yaml"""
    with open(VENUES_FILE) as f:
        return yaml.safe_load(f)


def save_venues(venues):
    """Save updated venues.yaml"""
    with open(VENUES_FILE, 'w') as f:
        yaml.dump(venues, f, allow_unicode=True, sort_keys=False)


def slugify(name):
    """Create URL-friendly slug from name"""
    import re
    slug = re.sub(r'[^a-z0-9]', '_', name.lower())[:40]
    return slug.strip('_')


def determine_tier(venue_type):
    """Determine which tier a venue belongs to"""
    type_lower = venue_type.lower()
    
    if any(x in type_lower for x in ['konserthall', 'arena', 'teater', 'opera']):
        return 'tier1_major'
    elif any(x in type_lower for x in ['museum', 'kulturhus', 'bibliotek']):
        return 'tier2_cultural'
    else:
        return 'tier3_small'


def merge_discovered_venues():
    """Merge all discovered venue files into venues.yaml"""
    print("🔄 Merging Discovered Venues")
    print("=" * 50)
    
    # Load current venues
    venues = load_venues()
    existing_names = set()
    
    # Collect existing names
    for tier in venues.values():
        if isinstance(tier, dict):
            for v in tier.values():
                if isinstance(v, dict):
                    existing_names.add(v.get('name', '').lower())
    
    added_count = 0
    skipped_count = 0
    
    # Process each discovery file
    for filename in DISCOVERY_FILES:
        filepath = DATA_DIR / filename
        if not filepath.exists():
            print(f"  ⏭️  {filename} - not found yet")
            continue
        
        print(f"\n  📂 Processing {filename}...")
        
        try:
            with open(filepath) as f:
                data = json.load(f)
            
            discovered = data.get('venues', [])
            
            for venue in discovered:
                name = venue.get('name', '')
                
                # Skip if already exists
                if name.lower() in existing_names:
                    skipped_count += 1
                    continue
                
                # Determine tier
                tier = determine_tier(venue.get('type', 'other'))
                
                # Create venue entry
                key = slugify(name)
                
                venue_entry = {
                    'name': name,
                    'location': venue.get('location', 'Karlstad'),
                    'address': venue.get('address', ''),
                    'type': [venue.get('type', 'Evenemang')],
                    'urls': {},
                    'scraper': {'type': 'manual'},
                    'active': True,
                    'discovered_date': datetime.now().isoformat(),
                    'source': venue.get('source', 'subagent_discovery')
                }
                
                # Add website if available
                website = venue.get('website')
                if website:
                    venue_entry['urls']['main'] = website
                
                # Add to appropriate tier
                if tier not in venues:
                    venues[tier] = {}
                
                # Ensure unique key
                original_key = key
                counter = 1
                while key in venues[tier]:
                    key = f"{original_key}_{counter}"
                    counter += 1
                
                venues[tier][key] = venue_entry
                existing_names.add(name.lower())
                added_count += 1
                
                print(f"    ✓ Added: {name} ({venue.get('location')})")
        
        except Exception as e:
            print(f"    ❌ Error processing {filename}: {e}")
    
    # Save updated venues
    save_venues(venues)
    
    print(f"\n✅ Merge complete!")
    print(f"   Added: {added_count} new venues")
    print(f"   Skipped (duplicates): {skipped_count}")
    
    return added_count


def main():
    """Entry point"""
    count = merge_discovered_venues()
    
    if count > 0:
        print(f"\n📝 Updated {VENUES_FILE}")
        print("   Remember to commit changes to git!")


if __name__ == "__main__":
    main()
