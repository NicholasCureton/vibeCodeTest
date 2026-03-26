"""
FILE: agents/manager.py
ROLE: Agent Creation and Management

DESCRIPTION:
    Creates agent instances based on configuration.
    Manages system prompts and tool access.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from agents.config import AgentConfig, load_agent_configs
from core import LLMClientProtocol, ToolExecutorProtocol


class AgentManager:
    """
    Creates and manages agent instances.

    Agents are configured via YAML file, allowing easy modification
    without code changes.
    """

    def __init__(
        self,
        config_path: str = "agents.yaml",
        llm_client: Optional[LLMClientProtocol] = None
    ):
        """
        Initialize agent manager.

        Args:
            config_path: Path to agents.yaml
            llm_client: LLM client for agents to use
        """
        self.configs = load_agent_configs(config_path)
        self.llm_client = llm_client
        self._prompt_cache: Dict[str, str] = {}

    def set_llm_client(self, client: LLMClientProtocol) -> None:
        """Set LLM client for agents."""
        self.llm_client = client

    def create_agent(
        self,
        agent_name: str,
        override_prompt: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create an agent context for LLM interaction.

        Returns a dict with:
        - system_prompt: The agent's system prompt
        - tools: List of tool schemas
        - max_iterations: Max tool call iterations
        - context: Loaded context files

        Args:
            agent_name: Name of agent to create
            override_prompt: Override system prompt

        Returns:
            Agent context dict, or None if agent not found
        """
        config = self.configs.get(agent_name)
        if not config:
            return None

        # Load system prompt
        if override_prompt:
            system_prompt = override_prompt
        else:
            system_prompt = self._load_prompt(config.system_prompt)

        # Get tool schemas
        from tools import get_schemas
        all_schemas = get_schemas()

        # Filter to allowed tools
        if config.tools:
            tool_schemas = [
                s for s in all_schemas
                if s.get("function", {}).get("name") in config.tools
            ]
        else:
            tool_schemas = all_schemas

        # Load context files
        context_content = []
        for filepath in config.context_files:
            content = self._load_context_file(filepath)
            if content:
                context_content.append(content)

        return {
            "name": agent_name,
            "system_prompt": system_prompt,
            "tools": tool_schemas,
            "max_iterations": config.max_iterations,
            "context": "\n\n".join(context_content),
            "temperature": config.temperature,
            "think_mode": config.think_mode
        }

    def _load_prompt(self, path: str) -> str:
        """
        Load system prompt from file.

        Caches loaded prompts for efficiency.

        Args:
            path: Path to prompt file

        Returns:
            Prompt content, or default if not found
        """
        if path in self._prompt_cache:
            return self._prompt_cache[path]

        expanded = os.path.expanduser(path)

        if os.path.exists(expanded):
            try:
                with open(expanded, "r", encoding="utf-8") as f:
                    content = f.read()
                self._prompt_cache[path] = content
                return content
            except IOError:
                pass

        # Return default prompt
        from core import DEFAULT_SYSTEM_PROMPT
        return DEFAULT_SYSTEM_PROMPT

    def _load_context_file(self, path: str) -> Optional[str]:
        """Load context file content."""
        expanded = os.path.expanduser(path)

        if os.path.exists(expanded):
            try:
                with open(expanded, "r", encoding="utf-8") as f:
                    return f.read()
            except IOError:
                return None
        return None

    def list_agents(self) -> List[str]:
        """List available agent types."""
        return list(self.configs.keys())

    def get_agent_config(self, name: str) -> Optional[AgentConfig]:
        """Get config for specific agent."""
        return self.configs.get(name)
