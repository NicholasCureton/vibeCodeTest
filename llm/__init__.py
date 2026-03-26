"""
LLM MODULE - LLM Client Interface

Public interface for LLM communication. Import from here, not from internal files.

USAGE:
    from llm import LLMClient, MockLLMClient

    # Real client
    client = LLMClient(server_url="http://localhost:8080")
    response = client.call(messages)

    # Mock client for testing
    mock = MockLLMClient()
    response = mock.call(messages)
"""
from llm.client import LLMClient
from llm.mock_client import MockLLMClient
from llm.types import (
    ChatChoice,
    OpenAIResponse,
    StreamGenerator,
    StreamingTimeoutError
)

__all__ = [
    "LLMClient",
    "MockLLMClient",
    "ChatChoice",
    "OpenAIResponse",
    "StreamGenerator",
    "StreamingTimeoutError"
]
