#!/usr/bin/env python3
"""
FILE: chat_runner.py
ROLE: Chat Execution Engine

DESCRIPTION:
    Handles the core chat loop: send to LLM, handle tool calls, return response.
    Supports streaming, reasoning content, and tool execution.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from . import settings, ui
from .llm.types import StreamingTimeoutError
from .tools import execute, get_schemas, build_tool_result_message


class AgentMode:
    """Agent mode constants."""
    OFF: str = "off"
    ON: str = "on"


def run_chat(
    user_input: str,
    history: List[Dict[str, Any]],
    system_prompt: str,
    llm_client,
    agent_mode: str,
    agent_debug: bool,
    server_think: bool,
    context_limit: int,
    chat_history,
    enable_markdown: bool = True,
) -> None:
    """
    Execute a chat turn.

    Handles the full loop: send to LLM, handle tool calls, return response.

    Args:
        user_input: User's message
        history: Conversation history
        system_prompt: System prompt text
        llm_client: LLM client instance
        agent_mode: Agent mode setting
        agent_debug: Debug mode for tools
        server_think: Enable server-side reasoning
        context_limit: Context window size
        chat_history: Chat history handler
        enable_markdown: Enable markdown rendering (interactive mode only)
    """
    max_iterations = settings.get("max_agent_iterations", 10)
    params = settings.get_params()

    history.append({"role": "user", "content": user_input})
    chat_history.save("user", user_input)

    tool_id_counter = 0
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        messages = [{"role": "system", "content": system_prompt}] + history
        prompt_tokens = llm_client.get_token_count(messages)

        try:
            chunks = llm_client.call(
                messages=messages,
                params=params,
                tools=get_schemas(),
                server_think=server_think,
                stream=True
            )
        except StreamingTimeoutError as e:
            ui.display_error(str(e))
            return
        except Exception as e:
            ui.display_error(f"LLM error: {e}")
            return

        if chunks is None:
            ui.display_error("Failed to connect to LLM")
            return

        # Process streaming response
        full_content = ""
        full_reasoning = ""
        tool_calls: List[Dict[str, Any]] = []
        finish_reason = "stop"
        first_content = True
        currently_thinking = False
        completion_tokens = 0
        tokens_per_second = 0.0

        ui.display_assistant_label()

        try:
            for chunk in chunks:
                choices = chunk.get("choices", [])
                if not choices:
                    continue

                choice = choices[0]
                delta = choice.get("delta", {})

                fr = choice.get("finish_reason")
                if fr is not None:
                    finish_reason = fr

                timings = chunk.get("timings", {})
                if timings:
                    completion_tokens = timings.get("predicted_n", 0)
                    tokens_per_second = timings.get("predicted_per_second", 0.0)

                # Handle reasoning content
                if "reasoning_content" in delta:
                    text = delta["reasoning_content"]
                    if text:
                        full_reasoning += text
                        if not currently_thinking:
                            currently_thinking = True
                            ui.display_thinking_separator()
                        # Never render markdown in reasoning mode
                        ui.stream_chunk(text, is_reasoning=True)

                # Handle main content
                elif "content" in delta:
                    text = delta["content"]
                    if text:
                        full_content += text
                        switched = currently_thinking or first_content
                        if currently_thinking:
                            currently_thinking = False
                        if first_content:
                            first_content = False
                        # Use markdown streaming for interactive mode
                        ui.stream_markdown_chunk(
                            text,
                            is_reasoning=False,
                            has_switched=switched,
                            enable_markdown=enable_markdown
                        )

                # Handle tool calls
                if "tool_calls" in delta:
                    for tc_delta in delta["tool_calls"]:
                        idx = tc_delta.get("index", 0)
                        while len(tool_calls) <= idx:
                            tool_calls.append({
                                "id": f"call_{tool_id_counter}",
                                "type": "function",
                                "function": {"name": "", "arguments": ""}
                            })
                            tool_id_counter += 1

                        if "id" in tc_delta:
                            tool_calls[idx]["id"] = tc_delta["id"]
                        if "type" in tc_delta:
                            tool_calls[idx]["type"] = tc_delta["type"]
                        if "function" in tc_delta:
                            func = tc_delta["function"]
                            if "name" in func:
                                tool_calls[idx]["function"]["name"] += func["name"]
                            if "arguments" in func:
                                tool_calls[idx]["function"]["arguments"] += func["arguments"]

        except KeyboardInterrupt:
            ui.display_interrupted()
            # Reset markdown parser to clear any buffers
            ui.reset_markdown_parser()
            if full_content.strip() or full_reasoning.strip():
                chat_history.save("assistant", full_content, full_reasoning)
                history.append({
                    "role": "assistant",
                    "content": full_content,
                    "reasoning_content": full_reasoning
                })
            return

        # Finalize markdown streaming - flush any remaining buffers
        if enable_markdown:
            remaining = ui.finalize_markdown_stream()
            if remaining:
                # Should be empty, but print just in case
                print(remaining, end="")

        print()

        # Display stats
        total_tokens = prompt_tokens + completion_tokens
        if total_tokens > 0:
            ui.display_stats(total_tokens, tokens_per_second, context_limit)

        # Handle finish
        if finish_reason == "stop":
            if full_content.strip() or full_reasoning.strip():
                chat_history.save("assistant", full_content, full_reasoning)
                history.append({
                    "role": "assistant",
                    "content": full_content,
                    "reasoning_content": full_reasoning
                })
            return

        # Handle tool calls
        if finish_reason == "tool_calls" and tool_calls:
            chat_history.save(
                role="assistant",
                content=full_content,
                reasoning=full_reasoning,
                tool_calls=tool_calls
            )
            history.append({
                "role": "assistant",
                "content": full_content,
                "reasoning_content": full_reasoning,
                "tool_calls": tool_calls
            })

            # Execute each tool
            for tool_call in tool_calls:
                try:
                    tool_call_id = tool_call.get("id", "")
                    function = tool_call.get("function", {})
                    tool_name = function.get("name", "")
                    arguments_json = function.get("arguments", "{}")

                    try:
                        args = json.loads(arguments_json)
                    except json.JSONDecodeError:
                        args = {}

                    # Confirmation (if not in agent mode)
                    if agent_mode == AgentMode.OFF:
                        cmd = args.get("command", str(args)) if tool_name == "execute_bash" else str(args)
                        try:
                            confirm = ui.prompt_tool_confirmation(cmd)
                        except EOFError:
                            # User sent EOF during confirmation
                            ui.display_interrupted()
                            ui.reset_markdown_parser()
                            return
                        if confirm != "Y":
                            ui.display_skipped()
                            skip_msg = build_tool_result_message(
                                tool_call_id=tool_call_id,
                                result="Tool execution skipped by user. STOP and Wait for instructions. DO NOT PROCEED."
                            )
                            chat_history.save(
                                role="tool",
                                content="Tool execution skipped by user. STOP and Wait for instructions. DO NOT PROCEED.",
                                tool_call_id=tool_call_id
                            )
                            history.append(skip_msg)
                            continue

                    # Execute tool
                    result = execute(
                        tool_name,
                        arguments_json,
                        timeout=settings.get("bash_timeout", 60)
                    )

                    print()
                    ui.display_tool_call(
                        tool_name=tool_name,
                        tool_args=args,
                        output=result.output if result.output else result.error or "(no output)",
                        success=result.success,
                        exit_code=result.exit_code,
                        debug=agent_debug
                    )
                    print()

                    # Build result message
                    tool_content = result.output
                    if not result.success and result.error:
                        tool_content = f"ERROR: {result.error}\n\nOutput: {result.output}"

                    tool_result_msg = build_tool_result_message(
                        tool_call_id=tool_call_id,
                        result=tool_content
                    )

                    chat_history.save(
                        role="tool",
                        content=tool_content,
                        tool_call_id=tool_call_id
                    )
                    history.append(tool_result_msg)

                except KeyboardInterrupt:
                    # User interrupted during tool execution
                    ui.display_interrupted()
                    ui.reset_markdown_parser()
                    # Save partial progress and return to continue conversation
                    if full_content.strip() or full_reasoning.strip():
                        chat_history.save("assistant", full_content, full_reasoning)
                    return
                except Exception as e:
                    # Tool execution failed with unexpected error
                    ui.display_error(f"Tool '{tool_name}' failed: {e}")
                    # Save error to history and continue with next tool
                    error_msg = build_tool_result_message(
                        tool_call_id=tool_call.get("id", ""),
                        result=f"Tool execution error: {e}"
                    )
                    chat_history.save(
                        role="tool",
                        content=f"Tool execution error: {e}",
                        tool_call_id=tool_call.get("id", "")
                    )
                    history.append(error_msg)

            continue

        ui.display_error(f"Unknown finish_reason: {finish_reason}")
        return

    ui.display_warning(f"Reached max iterations ({max_iterations}). Stopping.")
