"""
FILE: llm/types.py
ROLE: Type definitions for LLM module

DESCRIPTION:
    Defines types used internally by the LLM client.
    These are implementation details, not part of the public interface.
"""
from __future__ import annotations

from typing import Any, Dict, Generator, List, Optional, TypedDict


# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================

class StreamingTimeoutError(Exception):
    """Raised when streaming from LLM server times out."""
    pass


# =============================================================================
# TYPE DEFINITIONS
# =============================================================================

class ChatChoice(TypedDict, total=False):
    """A single choice in an LLM response."""
    message: Dict[str, Any]
    delta: Dict[str, Any]
    finish_reason: Optional[str]


class OpenAIResponse(TypedDict, total=False):
    """OpenAI-format response structure."""
    id: str
    choices: List[ChatChoice]
    usage: Optional[Dict[str, int]]


# Type alias for streaming generator
StreamGenerator = Generator[Dict[str, Any], None, None]
