#!/usr/bin/env python3
"""
FILE: main.py
ROLE: Entry Point

DESCRIPTION:
    Main entry point for the CLI chat application.
    Delegates to cli module for actual execution.

USAGE:
    python main.py                                # Interactive mode
    python main.py "message"                      # One-shot mode (loads history)
    python main.py "message" --no-history         # One-shot fresh start
    python main.py --mock                         # Use mock LLM (testing)
    python main.py --system-prompt prompts/coder.md   # Custom system prompt
    python main.py "task" --system-prompt /path/to/researcher.md  # Sub-agent mode

CHAT HISTORY:
    When --system-prompt is used, chat history is saved alongside the prompt:
        /path/to/coder_system_prompt.md → /path/to/coder_chat_history.jsonl
        /path/to/researcher.md → /path/to/researcher_chat_history.jsonl

    One-shot mode loads previous history by default. Use --no-history to start fresh.
    History includes: user/assistant/tool messages, reasoning_content, tool_calls.
"""
import sys

from . import settings, ui
from .llm import LLMClient, MockLLMClient
from .llm.types import StreamingTimeoutError
from .prompt_loader import load_system_prompt
from .cli import parse_args, run_interactive_mode, run_one_shot_mode
from .commands.read import setup_tab_completion


def main() -> None:
    """Main entry point."""
    args = parse_args()

    is_one_shot: bool = bool(args.message)
    server_think: bool = True

    # Create LLM client
    if args.mock:
        llm_client = MockLLMClient()
    else:
        llm_client = LLMClient(
            server_url=settings.get("server_url", "http://localhost:8080"),
            stream_timeout=settings.get("stream_timeout", 120),
            model_name=settings.get("model_name", "model.gguf")
        )

    # Load system prompt
    system_prompt, custom_history_path = load_system_prompt(args.system_prompt)
    context_limit = llm_client.get_context_limit()

    if not is_one_shot:
        ui.display_startup_banner(context_limit)
        # Setup tab completion for interactive mode
        setup_tab_completion()

    try:
        if is_one_shot:
            # One-shot mode
            run_one_shot_mode(
                message=args.message,
                system_prompt=system_prompt,
                custom_history_path=custom_history_path,
                llm_client=llm_client,
                context_limit=context_limit,
                no_history=args.no_history,
                server_think=server_think,
            )
        else:
            # Interactive mode
            run_interactive_mode(
                system_prompt=system_prompt,
                custom_history_path=custom_history_path,
                llm_client=llm_client,
                context_limit=context_limit,
                show_ui_reasoning=args.show_reasoning,
            )
    except KeyboardInterrupt:
        ui.display_closed_by_user()
        sys.exit(0)


if __name__ == "__main__":
    main()
