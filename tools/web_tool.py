"""
FILE: tools/web_tool.py
ROLE: Web Search and Crawl Tools

DESCRIPTION:
    Provides web search using the original search_internet.py module.
    Uses DuckDuckGo for search results.

TOOLS:
    - search_internet: Search the web using DuckDuckGo
    - crawl_web: Crawl a website using Crawl4AI (kept from previous)

NOTE:
    search_internet uses the original search_internet.py module
    which provides formatted output with emojis and structured results.
"""
from __future__ import annotations

import os
import subprocess
from typing import Dict

from core import ToolResult
from tools.registry import register_tool
from tools import search  # Original search_internet module


# =============================================================================
# SEARCH TOOL SCHEMA
# =============================================================================

SEARCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_internet",
        "description": (
            "Search the web using DuckDuckGo. "
            "Returns formatted results with titles, URLs, and preview snippets. "
            "Use this to find current information, news, documentation, or research topics."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string"
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (default: 10, max: 20)"
                }
            },
            "required": ["query"]
        }
    }
}


# =============================================================================
# CRAWL TOOL SCHEMA
# =============================================================================

CRAWL_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "crawl_web",
        "description": (
            "Crawl a website and extract its content as markdown. "
            "Uses Crawl4AI with anti-bot protection. "
            "Use this when you need full page content from a specific URL."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to crawl (must include http:// or https://)"
                },
                "output_format": {
                    "type": "string",
                    "enum": ["markdown", "json", "markdown-fit"],
                    "description": (
                        "Output format. "
                        "markdown: raw content (default). "
                        "markdown-fit: cleaned, more readable. "
                        "json: includes metadata like links and images."
                    )
                },
                "css_selector": {
                    "type": "string",
                    "description": (
                        "Target specific content only. "
                        "Examples: 'article', '#main', '.content'."
                    )
                },
                "delay": {
                    "type": "number",
                    "description": "Wait time before capturing content (seconds, default: 2.0)"
                }
            },
            "required": ["url"]
        }
    }
}


# =============================================================================
# SEARCH IMPLEMENTATION (Using Original Module)
# =============================================================================

def search_internet(query: str, num_results: int = 10, timeout: int = 30) -> ToolResult:
    """
    Search the web using DuckDuckGo via the original search_internet module.

    Args:
        query: Search query string
        num_results: Number of results to return (1-20)
        timeout: Request timeout in seconds

    Returns:
        ToolResult with formatted search results
    """
    if not query or not query.strip():
        return ToolResult(
            success=False,
            output="",
            error="Search query cannot be empty",
            exit_code=-1
        )

    # Limit results
    num_results = min(max(1, num_results), 20)

    try:
        # Use original search module
        results = search.search_internet(query, num_results)

        if not results:
            return ToolResult(
                success=True,
                output="No results found. Try a different search query.",
                exit_code=0
            )

        # Format results using the original display function style
        output_lines = [
            "",
            "=" * 70,
            f'  Search Results for: "{query}"',
            "=" * 70,
            ""
        ]

        for i, r in enumerate(results, 1):
            title = r.get('title', 'No title')
            url = r.get('url', '')
            snippet = r.get('snippet', 'No preview available')

            output_lines.append(f"{i}. {title}")
            output_lines.append(f"   {'─' * 60}")
            output_lines.append(f"   🔗 {url}")
            output_lines.append(f"   📝 {snippet}")
            output_lines.append("")

        output_lines.append("=" * 70)
        output_lines.append(f"  Showing {len(results)} result(s)")
        output_lines.append("=" * 70)

        return ToolResult(
            success=True,
            output="\n".join(output_lines),
            exit_code=0
        )

    except ImportError:
        return ToolResult(
            success=False,
            output="",
            error="duckduckgo-search not installed. Run: pip install ddgs",
            exit_code=-1
        )
    except Exception as e:
        return ToolResult(
            success=False,
            output="",
            error=f"Search failed: {str(e)}",
            exit_code=-1
        )


# =============================================================================
# CRAWL IMPLEMENTATION (From previous refactor)
# =============================================================================

def crawl_web(
    url: str,
    output_format: str = "markdown",
    css_selector: str = "",
    delay: float = 2.0,
    timeout: int = 180
) -> ToolResult:
    """
    Crawl a website using Crawl4AI CLI.

    Args:
        url: URL to crawl
        output_format: Output format (markdown, json, markdown-fit)
        css_selector: CSS selector to target specific content
        delay: Delay before capturing content (seconds)
        timeout: Crawl timeout in seconds

    Returns:
        ToolResult with page content
    """
    if not url or not url.strip():
        return ToolResult(
            success=False,
            output="",
            error="URL cannot be empty",
            exit_code=-1
        )

    # Validate output format
    valid_formats = ["markdown", "json", "markdown-fit", "md", "md-fit"]
    if output_format not in valid_formats:
        output_format = "markdown"

    try:
        # Set up environment
        env = os.environ.copy()
        local_bin = os.path.expanduser("~/.local/bin")
        if os.path.isdir(local_bin) and local_bin not in env.get("PATH", ""):
            env["PATH"] = local_bin + os.pathsep + env.get("PATH", "")

        # Build command
        cmd_parts = ["crwl", "crawl", f'"{url}"', "-o", output_format]

        if css_selector:
            cmd_parts.extend(["-c", f"css_selector={css_selector}"])

        if delay != 2.0:
            cmd_parts.extend(["-c", f"delay_before_return_html={delay}"])

        cmd_parts.append("--bypass-cache")

        cmd = " ".join(cmd_parts)

        # Execute
        process = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env
        )

        # Get output (crawl4ai may output to stderr)
        output = process.stdout or process.stderr

        # Filter Python warnings
        def filter_warnings(text: str) -> str:
            if not text:
                return ""
            lines = []
            for line in text.split('\n'):
                if any(warn in line for warn in [
                    'UserWarning', 'DeprecationWarning',
                    'RequestsDependencyWarning', 'warnings.warn',
                    'FutureWarning', 'PendingDeprecationWarning'
                ]):
                    continue
                if line.strip():
                    lines.append(line)
            return '\n'.join(lines)

        output = filter_warnings(output)

        if process.returncode != 0:
            return ToolResult(
                success=False,
                output="",
                error=f"Crawl failed (exit {process.returncode}): {process.stderr[:200] if process.stderr else 'Unknown error'}",
                exit_code=process.returncode
            )

        if not output.strip():
            return ToolResult(
                success=False,
                output="",
                error="Crawl returned empty content. Page might require JavaScript.",
                exit_code=-1
            )

        # Limit output size
        max_chars = 100000
        if len(output) > max_chars:
            output = output[:max_chars] + "\n\n... [Content truncated due to size]"

        return ToolResult(
            success=True,
            output=output,
            exit_code=0
        )

    except subprocess.TimeoutExpired:
        return ToolResult(
            success=False,
            output="",
            error=f"Crawl timed out after {timeout} seconds",
            exit_code=-1
        )
    except FileNotFoundError:
        return ToolResult(
            success=False,
            output="",
            error="crwl not found. Install: pip install crawl4ai && playwright install chromium",
            exit_code=-1
        )
    except Exception as e:
        return ToolResult(
            success=False,
            output="",
            error=f"Crawl failed: {str(e)}",
            exit_code=-1
        )


# =============================================================================
# SELF-REGISTRATION
# =============================================================================

register_tool(
    name="search_internet",
    function=search_internet,
    schema=SEARCH_TOOL_SCHEMA,
    description="Search the web using DuckDuckGo",
    timeout=30
)

register_tool(
    name="crawl_web",
    function=crawl_web,
    schema=CRAWL_TOOL_SCHEMA,
    description="Crawl websites and extract content",
    timeout=180
)
