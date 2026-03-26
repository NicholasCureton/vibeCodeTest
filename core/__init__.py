"""
CORE MODULE - Base Types and Interfaces

This module defines the foundational types and protocols that other
modules depend on. It has NO dependencies on other project modules.

EXPORTS:
    - ToolResult: Dataclass for tool execution results
    - Message: TypedDict for chat messages
    - LLMClientProtocol: Protocol defining LLM client interface
    - ToolExecutorProtocol: Protocol defining tool executor interface
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, TypedDict, Union


# =============================================================================
# MESSAGE TYPES
# =============================================================================

class Message(TypedDict, total=False):
    """A single chat message in OpenAI format."""
    role: str
    content: str
    reasoning_content: Optional[str]
    tool_calls: Optional[List[Dict[str, Any]]]
    tool_call_id: Optional[str]


class ToolCall(TypedDict):
    """A tool call from the LLM."""
    id: str
    type: str
    function: Dict[str, str]


class ToolCallFunction(TypedDict):
    """Function part of a tool call."""
    name: str
    arguments: str


# =============================================================================
# RESULT TYPES
# =============================================================================

@dataclass
class ToolResult:
    """Result of executing a tool."""
    success: bool
    output: str
    exit_code: int = 0
    error: Optional[str] = None


@dataclass
class LLMResponse:
    """Parsed response from LLM."""
    content: str
    reasoning: str = ""
    tool_calls: List[ToolCall] = None
    finish_reason: str = "stop"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tokens_per_second: float = 0.0

    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []


# =============================================================================
# PROTOCOLS (Interfaces)
# =============================================================================

class LLMClientProtocol(Protocol):
    """Protocol defining what an LLM client must provide.
    
    This allows swapping implementations (real server, mock, etc.)
    without changing any code that uses the client.
    """

    def call(
        self,
        messages: List[Message],
        params: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        server_think: bool = True,
        stream: bool = True
    ) -> Union[LLMResponse, Any]:
        """Send messages to LLM and get response."""
        ...

    def get_token_count(self, messages: List[Message]) -> int:
        """Count tokens for messages."""
        ...

    def get_context_limit(self) -> int:
        """Get context window size."""
        ...


class ToolExecutorProtocol(Protocol):
    """Protocol defining what a tool executor must provide."""

    def execute(
        self,
        name: str,
        arguments: Union[str, Dict[str, Any]],
        **kwargs
    ) -> ToolResult:
        """Execute a tool by name."""
        ...

    def get_schemas(self) -> List[Dict[str, Any]]:
        """Get OpenAI-format tool schemas."""
        ...

    def list_tools(self) -> Dict[str, str]:
        """List available tools with descriptions."""
        ...


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_CONTEXT_LIMIT: int = 8192
DEFAULT_SYSTEM_PROMPT: str = """You are a helpful AI assistant with access to a Linux terminal.

You have access to tools for file operations, web search, and command execution.
Use these tools to help the user accomplish their tasks.

Always explain what you're doing before running commands or making changes."""
