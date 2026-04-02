"""
MEMORY MODULE - Project State and Session Management

Provides persistence for:
- Project state (PROJECT.md)
- Session history (chat_history.jsonl)
- Working memory for cross-session continuity

USAGE:
    from memory import ProjectState, ChatHistory

    # Project state
    state = ProjectState()
    state.load()
    state.update_progress("Working on sub-agents")
    state.save()

    # Chat history
    history = ChatHistory()
    history.save("user", "Hello")
    messages = history.load()
"""
from .project_state import ProjectState
from .chat_history import ChatHistory

__all__ = ["ProjectState", "ChatHistory"]
