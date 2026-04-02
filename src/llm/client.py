"""
FILE: llm/client.py
ROLE: Real LLM Client (llama.cpp server)

DESCRIPTION:
    HTTP client for llama.cpp OpenAI-compatible API.
    Handles streaming, timeout, error handling, and token counting.

STANDALONE: No dependencies on other project modules.

USAGE:
    client = LLMClient()  # Uses default localhost:8080
    response = client.call(messages, stream=True)
    tokens = client.get_token_count(messages)
    limit = client.get_context_limit()
"""
from __future__ import annotations

import json
import codecs
import requests
from typing import Any, Dict, Generator, List, Optional, Union

from .types import (
    StreamingTimeoutError,
    ChatChoice,
    OpenAIResponse,
    StreamGenerator
)
from ..core import LLMResponse
from .. import settings


class LLMClient:
    """
    HTTP client for llama.cpp server with OpenAI-compatible API.

    Attributes:
        api_url: Base URL for the API
        stream_timeout: Timeout for streaming responses
        model_name: Model name for token counting
    """

    def __init__(
        self,
        server_url: str = "http://localhost:8080",
        stream_timeout: int = 120,
        model_name: str = "model.gguf"
    ):
        """
        Initialize LLM client.

        Args:
            server_url: Base URL of llama.cpp server
            stream_timeout: Timeout for streaming in seconds
            model_name: Model name for API calls
        """
        self.api_url = f"{server_url}/v1/chat/completions"
        self.base_url = server_url
        self.stream_timeout = stream_timeout
        self.model_name = model_name

    def call(
        self,
        messages: List[Dict[str, Any]],
        params: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        server_think: bool = True,
        stream: bool = True
    ) -> Union[Optional[OpenAIResponse], StreamGenerator, None]:
        """
        Send messages to LLM and get response.

        Args:
            messages: List of chat messages [{"role": "user", "content": "..."}]
            params: Sampling parameters (temperature, top_p, etc.)
            tools: List of tool definitions (OpenAI format)
            server_think: Enable thinking/reasoning mode (model-dependent)
            stream: Return generator for streaming, or dict for complete response

        Returns:
            Generator (if stream=True) or dict (if stream=False) or None on error

        Raises:
            StreamingTimeoutError: If request times out
            requests.exceptions.RequestException: On connection errors
        """
        if params is None:
            params = {}

        payload: Dict[str, Any] = {
            "messages": messages,
            "stream": stream,
            **params
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        # Model-specific thinking control (from model_config in settings.json)
        model_config = settings.get("model_config", {})
        has_thinking = model_config.get("has_thinking_mode", False)
        
        if not server_think and has_thinking:
            thinking_disable = model_config.get("thinking_disable_payload", {})
            payload.update(thinking_disable)

        # Extra payload for model-specific customizations
        extra_payload = model_config.get("extra_payload", {})
        payload.update(extra_payload)

        try:
            response = requests.post(
                self.api_url,
                json=payload,
                stream=stream,
                timeout=(10, self.stream_timeout)
            )
            response.raise_for_status()

            if not stream:
                try:
                    return response.json()
                except json.JSONDecodeError:
                    return None

            def generate_chunks() -> StreamGenerator:
                decoder = codecs.getincrementaldecoder("utf-8")()
                try:
                    for line in response.iter_lines():
                        if not line:
                            continue
                        try:
                            line_str = decoder.decode(line, final=False).strip()
                        except UnicodeDecodeError:
                            continue
                        if line_str.startswith("data: "):
                            content = line_str[6:]
                            if content == "[DONE]":
                                break
                            try:
                                yield json.loads(content)
                            except json.JSONDecodeError:
                                continue
                except requests.exceptions.Timeout:
                    raise StreamingTimeoutError(f"Stream timed out after {self.stream_timeout} seconds")
                finally:
                    response.close()

            return generate_chunks()

        except requests.exceptions.Timeout:
            raise StreamingTimeoutError("Request timed out")
        except requests.exceptions.RequestException:
            raise

    def get_token_count(self, messages: List[Dict[str, Any]]) -> int:
        """
        Count total tokens for messages using max_tokens=0 trick.

        This sends a request with max_tokens=0 which returns token count
        without generating any output.

        Args:
            messages: Full message list including system prompt

        Returns:
            Total token count, or heuristic estimate on error
        """
        try:
            response = requests.post(
                self.api_url,
                json={
                    "model": self.model_name,
                    "messages": messages,
                    "max_tokens": 0,
                    "stream": False
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                usage = data.get("usage", {})
                tokens = usage.get("prompt_tokens")
                if tokens is not None and isinstance(tokens, int):
                    return tokens
                else:
                    print(f"[WARN] API returned non-standard token count. Using heuristic.")
                    return int(len(str(messages)) / 3.0)

        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                json.JSONDecodeError) as e:
            print(f"[WARN] Failed to get token count: {type(e).__name__}. Using heuristic.")

        # Fallback heuristic
        return int(len(str(messages)) / 3.0)

    def get_context_limit(self) -> int:
        """
        Query llama.cpp /props endpoint for context window size.

        Returns:
            Context limit in tokens, or default (8192) on error
        """
        props_url = f"{self.base_url}/props"

        try:
            response = requests.get(props_url, timeout=3)
            if response.status_code == 200:
                data: Dict[str, Any] = response.json()
                if "n_ctx" in data:
                    return int(data["n_ctx"])
                settings_data = data.get("default_generation_settings", {})
                if "n_ctx" in settings_data:
                    return int(settings_data["n_ctx"])
        except (requests.exceptions.RequestException,
                json.JSONDecodeError,
                KeyError,
                ValueError):
            pass

        return 8192  # Default fallback
