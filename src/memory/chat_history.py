"""
FILE: memory/chat_history.py
ROLE: Conversation Persistence

DESCRIPTION:
    Saves and loads chat history in JSONL format.
    Uses file locking to prevent corruption.

FUNCTIONS:
    save(role, content, ...)  → Append message to history
    load()                    → Load all messages
    clear()                   → Wipe history
"""
from __future__ import annotations

import json
import os
import fcntl
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from ..core import Message, find_data_dir


class ChatHistory:
    """
    Manages conversation history in JSONL format.

    Thread-safe with file locking.
    """

    def __init__(self, filename: Optional[str] = None):
        """
        Initialize chat history.

        Args:
            filename: Path to history file. If None, uses data/chat_history.jsonl
        """
        if filename is None:
            self.filename = os.path.join(find_data_dir(__file__), "chat_history.jsonl")
        else:
            self.filename = filename

    def save(
        self,
        role: str,
        content: str = "",
        reasoning: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        tool_call_id: Optional[str] = None
    ) -> bool:
        """
        Append message to history.

        Args:
            role: Message role (user, assistant, tool, system)
            content: Message content
            reasoning: Reasoning content (for thinking models)
            tool_calls: Tool calls from assistant
            tool_call_id: Tool call ID (for tool role)

        Returns:
            True on success

        Raises:
            IOError: On write failure
        """
        data: Dict[str, Any] = {
            "role": role,
            "timestamp": datetime.now().isoformat()
        }

        if content:
            data["content"] = content
        else:
            data["content"] = ""

        if reasoning:
            data["reasoning_content"] = reasoning

        if tool_calls:
            data["tool_calls"] = tool_calls

        if tool_call_id:
            data["tool_call_id"] = tool_call_id

        try:
            with open(self.filename, "a", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.write(json.dumps(data) + "\n")
                    f.flush()
                    os.fsync(f.fileno())  # Force write to disk before unlocking
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            return True
        except IOError as e:
            raise IOError(f"[chat_history] Could not write: {e}") from e
        except Exception as e:
            raise IOError(f"[chat_history] Unexpected error: {e}") from e

    def load(self) -> List[Message]:
        """
        Load all messages from history.

        Returns:
            List of message dicts
        """
        messages: List[Message] = []
        corrupt_lines: int = 0

        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            msg = json.loads(line)
                            if "role" in msg:
                                messages.append(msg)
                            else:
                                corrupt_lines += 1
                        except json.JSONDecodeError:
                            corrupt_lines += 1
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            if corrupt_lines > 0:
                print(f"[chat_history] Skipped {corrupt_lines} corrupt line(s)")

        except FileNotFoundError:
            return []
        except IOError as e:
            print(f"[chat_history] Could not read: {e}")
            return []

        return messages

    def clear(self) -> bool:
        """
        Clear history file.

        Returns:
            True on success

        Raises:
            IOError: On write failure
        """
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            return True
        except IOError as e:
            raise IOError(f"[chat_history] Could not clear: {e}") from e

    def get_token_estimate(self) -> int:
        """
        Estimate token count for history.

        Uses simple heuristic: chars / 3

        Returns:
            Estimated token count
        """
        messages = self.load()
        total_chars = 0

        for msg in messages:
            content = msg.get("content", "")
            reasoning = msg.get("reasoning_content", "")
            if isinstance(content, str):
                total_chars += len(content)
            if isinstance(reasoning, str):
                total_chars += len(reasoning)

        return total_chars // 3
