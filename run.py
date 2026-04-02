#!/usr/bin/env python3
"""
Run script for CLI Chat Inference.

Usage:
    ./run.sh [args]           # Run with arguments
    ./run.sh --help           # Show help
    ./run.sh "message"        # One-shot mode
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.main import main

if __name__ == "__main__":
    main()
