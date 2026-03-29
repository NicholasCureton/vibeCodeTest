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
from tools import web_tool
from tools.search_replace_self_register import _execute_search_replace_command as search_replace
# Export the wrapper function for direct tool invocation


__all__ = [
    "register_tool",
    "execute",
    "get_schemas",
    "list_tools",
    "tool_exists",
    "build_tool_result_message",
    "build_assistant_tool_message",
    "ToolRegistry"
    "search_replace"
]
