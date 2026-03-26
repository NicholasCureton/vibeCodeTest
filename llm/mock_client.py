"""
FILE: llm/mock_client.py
ROLE: Mock LLM Client for Testing

DESCRIPTION:
    Simulates llama.cpp server responses for testing without a real server.
    Returns realistic-looking data that matches the actual API format.

USAGE:
    from llm import MockLLMClient

    client = MockLLMClient()
    response = client.call(messages, stream=False)  # Returns mock response
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, Union

from llm.types import OpenAIResponse, StreamGenerator
from core import DEFAULT_CONTEXT_LIMIT


class MockLLMClient:
    """
    Mock LLM client that simulates llama.cpp server responses.

    Use this for testing without a running llama.cpp server.
    Returns realistic-looking data in the correct format.
    """

    def __init__(
        self,
        context_limit: int = 8192,
        simulate_delay: bool = False
    ):
        """
        Initialize mock client.

        Args:
            context_limit: Simulated context window size
            simulate_delay: Add realistic delays to responses
        """
        self.context_limit = context_limit
        self.simulate_delay = simulate_delay

    def call(
        self,
        messages: List[Dict[str, Any]],
        params: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        server_think: bool = True,
        stream: bool = True
    ) -> Union[Optional[OpenAIResponse], StreamGenerator, None]:
        """
        Generate mock response.

        For tool testing, if the last user message contains keywords like
        "search", "bash", "file", etc., the mock will return a tool call.
        Otherwise, returns a text response.
        """
        last_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_message = msg.get("content", "")
                break

        # Determine response type based on message content
        should_tool_call = tools and self._should_trigger_tool(last_message)

        if stream:
            return self._generate_streaming_response(
                last_message,
                should_tool_call,
                server_think,
                tools
            )
        else:
            return self._generate_non_streaming_response(
                last_message,
                should_tool_call,
                server_think,
                tools
            )

    def _should_trigger_tool(self, message: str) -> bool:
        """Determine if mock should return a tool call."""
        tool_keywords = {
            "execute_bash": ["run ", "execute ", "command ", "bash ", "terminal "],
            "lft": ["read file", "edit file", "write file", "find in file"],
            "search_internet": ["search ", "look up ", "find information", "web "],
            "crawl_web": ["crawl ", "scrape ", "fetch url", "visit "]
        }

        message_lower = message.lower()
        for tool_name, keywords in tool_keywords.items():
            for keyword in keywords:
                if keyword in message_lower:
                    return True
        return False

    def _generate_non_streaming_response(
        self,
        user_message: str,
        should_tool_call: bool,
        server_think: bool,
        tools: Optional[List[Dict[str, Any]]]
    ) -> OpenAIResponse:
        """Generate a complete non-streaming response."""

        if self.simulate_delay:
            time.sleep(0.5)

        response_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"

        if should_tool_call and tools:
            # Return tool call
            tool_name = self._pick_tool(user_message)
            tool_args = self._generate_tool_args(tool_name, user_message)

            return {
                "id": response_id,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{
                            "id": f"call_{uuid.uuid4().hex[:8]}",
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(tool_args)
                            }
                        }]
                    },
                    "finish_reason": "tool_calls"
                }],
                "usage": {
                    "prompt_tokens": 150,
                    "completion_tokens": 50,
                    "total_tokens": 200
                }
            }

        # Return text response
        reasoning = ""
        if server_think:
            reasoning = "Let me think about how to respond to this request...\nI should provide a helpful answer."

        content = self._generate_text_response(user_message)

        return {
            "id": response_id,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                    "reasoning_content": reasoning
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 80,
                "total_tokens": 180
            }
        }

    def _generate_streaming_response(
        self,
        user_message: str,
        should_tool_call: bool,
        server_think: bool,
        tools: Optional[List[Dict[str, Any]]]
    ) -> StreamGenerator:
        """Generate a streaming response chunk by chunk."""

        response_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"

        if should_tool_call and tools:
            yield from self._stream_tool_call(response_id, user_message)
            return

        # Stream text response
        if server_think:
            yield from self._stream_reasoning(response_id)
            yield from self._stream_content(response_id, user_message)
        else:
            yield from self._stream_content(response_id, user_message)

        # Final chunk with usage
        yield {
            "id": response_id,
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 80,
                "total_tokens": 180
            },
            "timings": {
                "predicted_n": 80,
                "predicted_per_second": 25.0
            }
        }

    def _stream_reasoning(self, response_id: str) -> Generator:
        """Stream reasoning content."""
        reasoning_text = "Let me think about this...\n"

        for char in reasoning_text:
            if self.simulate_delay:
                time.sleep(0.02)
            yield {
                "id": response_id,
                "choices": [{
                    "index": 0,
                    "delta": {
                        "reasoning_content": char
                    }
                }]
            }

    def _stream_content(self, response_id: str, user_message: str) -> Generator:
        """Stream main content."""
        content = self._generate_text_response(user_message)

        for char in content:
            if self.simulate_delay:
                time.sleep(0.01)
            yield {
                "id": response_id,
                "choices": [{
                    "index": 0,
                    "delta": {
                        "content": char
                    }
                }]
            }

    def _stream_tool_call(self, response_id: str, user_message: str) -> Generator:
        """Stream a tool call."""
        tool_name = self._pick_tool(user_message)
        tool_args = json.dumps(self._generate_tool_args(tool_name, user_message))
        call_id = f"call_{uuid.uuid4().hex[:8]}"

        # Stream tool call
        yield {
            "id": response_id,
            "choices": [{
                "index": 0,
                "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": ""
                        }
                    }]
                }
            }]
        }

        # Stream arguments character by character
        for char in tool_args:
            if self.simulate_delay:
                time.sleep(0.005)
            yield {
                "id": response_id,
                "choices": [{
                    "index": 0,
                    "delta": {
                        "tool_calls": [{
                            "index": 0,
                            "function": {
                                "arguments": char
                            }
                        }]
                    }
                }]
            }

        # Finish
        yield {
            "id": response_id,
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "tool_calls"
            }],
            "timings": {
                "predicted_n": 30,
                "predicted_per_second": 30.0
            }
        }

    def _pick_tool(self, message: str) -> str:
        """Pick which tool to call based on message content."""
        message_lower = message.lower()

        if any(kw in message_lower for kw in ["run ", "execute ", "command ", "bash "]):
            return "execute_bash"
        elif any(kw in message_lower for kw in ["read file", "edit file", "write file"]):
            return "lft"
        elif any(kw in message_lower for kw in ["search ", "look up ", "find information"]):
            return "search_internet"
        elif any(kw in message_lower for kw in ["crawl ", "scrape ", "fetch url"]):
            return "crawl_web"
        else:
            return "execute_bash"  # Default

    def _generate_tool_args(self, tool_name: str, message: str) -> Dict[str, Any]:
        """Generate arguments for a tool call."""
        if tool_name == "execute_bash":
            return {"command": "echo 'Mock command executed'"}
        elif tool_name == "lft":
            return {"command": "read", "file_path": "/tmp/test.txt"}
        elif tool_name == "search_internet":
            return {"query": message[:50], "num_results": 5}
        elif tool_name == "crawl_web":
            return {"url": "https://example.com", "output_format": "markdown"}
        return {}

    def _generate_text_response(self, user_message: str) -> str:
        """Generate a text response based on user message."""
        responses = [
            f"I understand you're asking about: \"{user_message[:50]}...\"\n\n"
            "This is a mock response. In a real scenario, I would provide "
            "a helpful answer based on your request.",

            f"Thank you for your message. As a mock LLM client, I'm simulating "
            f"a response to: \"{user_message[:30]}...\"\n\n"
            "To test with real responses, connect to an actual llama.cpp server.",

            "I'm a mock client running in test mode. Your message was received. "
            "This simulated response helps you test the UI and tool calling "
            "without needing a real LLM server running."
        ]

        # Simple selection based on message length
        return responses[len(user_message) % len(responses)]

    def get_token_count(self, messages: List[Dict[str, Any]]) -> int:
        """
        Estimate token count using heuristic.

        For mock, uses simple character/3 estimation.
        """
        total_chars = len(str(messages))
        return max(1, total_chars // 3)

    def get_context_limit(self) -> int:
        """Return simulated context limit."""
        return self.context_limit
