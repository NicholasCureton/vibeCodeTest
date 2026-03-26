"""
TOOLS MODULE - Tool Registry and Execution

Public interface for tool management. Uses registry pattern so tools
can be added/removed without modifying core code.

USAGE:
    from tools import register_tool, execute, get_schemas, list_tools

    # Register a new tool
    register_tool("my_tool", my_function, schema, description)

    # Execute a tool
    result = execute("my_tool", {"arg": "value"})

    # Get tool schemas for LLM
    schemas = get_schemas()

    # List available tools
    tools = list_tools()

AVAILABLE TOOLS:
    - execute_bash: Run terminal commands
    - lft: Powerful file operations (read/write/edit/find/info/multiedit)
    - search_internet: Web search via DuckDuckGo
    - crawl_web: Website crawling via Crawl4AI
"""
from tools.registry import (
    register_tool,
    execute,
    get_schemas,
    list_tools,
    tool_exists,
    build_tool_result_message,
    build_assistant_tool_message,
    ToolRegistry
)

# Import tool implementations (they self-register)
from tools import bash_tool
from tools import lft_tool
from tools import web_tool

__all__ = [
    "register_tool",
    "execute",
    "get_schemas",
    "list_tools",
    "tool_exists",
    "build_tool_result_message",
    "build_assistant_tool_message",
    "ToolRegistry"
]
