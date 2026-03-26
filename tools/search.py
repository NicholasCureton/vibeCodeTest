#!/usr/bin/env python3
"""
Internet Search CLI Tool

A command-line tool to search the internet and display results similar to 
popular search engines with URLs and preview snippets.

Usage:
    python search_internet.py "search query" --show-results 5

Example:
    python search_internet.py "Car" --show-results 3
"""

import argparse
import sys
from typing import Optional


def search_internet(query: str, num_results: int = 10) -> list[dict]:
    """
    Search the internet using DuckDuckGo and return results.
    
    Args:
        query: The search query string
        num_results: Number of results to return (default: 10)
    
    Returns:
        List of search results with title, url, and snippet
    """
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # Fallback to old package name
        except ImportError:
            print("Error: 'ddgs' package is not installed.")
            print("Please install it using: pip install ddgs")
            sys.exit(1)
    
    results = []
    
    try:
        with DDGS() as ddgs:
            search_results = ddgs.text(query, max_results=num_results)
            
            if search_results:
                for result in search_results:
                    results.append({
                        'title': result.get('title', 'No title'),
                        'url': result.get('href', ''),
                        'snippet': result.get('body', 'No preview available')
                    })
    except Exception as e:
        print(f"Search error: {e}")
        sys.exit(1)
    
    return results


def display_results(results: list[dict], query: str) -> None:
    """
    Display search results in a search engine-like format.
    
    Args:
        results: List of search result dictionaries
        query: The original search query
    """
    # Print header
    print("\n" + "=" * 70)
    print(f"  Search Results for: \"{query}\"")
    print("=" * 70 + "\n")
    
    if not results:
        print("No results found. Try a different search query.")
        return
    
    for i, result in enumerate(results, 1):
        # Title (bold and numbered)
        title = result['title']
        url = result['url']
        snippet = result['snippet']
        
        # Display format similar to Google/Bing
        print(f"{i}. {title}")
        print(f"   {'─' * 60}")
        
        # URL with visual indicator
        print(f"   🔗 {url}")
        
        # Preview snippet
        print(f"   📝 {snippet}")
        
        print()  # Empty line between results
    
    # Footer summary
    print("=" * 70)
    print(f"  Showing {len(results)} result(s)")
    print("=" * 70 + "\n")


def main():
    """Main entry point for the CLI tool."""
    parser = argparse.ArgumentParser(
        description='Search the internet from command line',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python search_internet.py "Car"
  python search_internet.py "Python programming" --show-results 5
  python search_internet.py "latest tech news" -n 3
        '''
    )
    
    parser.add_argument(
        'query',
        type=str,
        help='The search query string (enclose in quotes if contains spaces)'
    )
    
    parser.add_argument(
        '-n', '--show-results',
        type=int,
        default=10,
        metavar='NUM',
        help='Number of results to display (default: 10)'
    )
    
    args = parser.parse_args()
    
    # Validate inputs
    if not args.query.strip():
        print("Error: Search query cannot be empty.")
        sys.exit(1)
    
    if args.show_results < 1:
        print("Error: Number of results must be at least 1.")
        sys.exit(1)
    
    # Perform search
    results = search_internet(args.query, args.show_results)
    
    # Display results
    display_results(results, args.query)


if __name__ == '__main__':
    main()
