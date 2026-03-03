#!/usr/bin/env python3
"""
Pipeline Entry Point
Thin wrapper that imports and runs the main pipeline
"""

import sys
from pathlib import Path

# Add scripts directory to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

# Import and run the pipeline
from event_pipeline import main

if __name__ == "__main__":
    sys.exit(main())