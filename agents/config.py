"""
FILE: agents/config.py
ROLE: Agent Configuration (YAML-based)

DESCRIPTION:
    Defines agent configurations in YAML format.
    Allows adding/modifying agents without code changes.

CONFIG FILE FORMAT (agents.yaml):
    main_agent:
      system_prompt: "prompts/main_agent.md"
      tools: ["execute_bash", "file", "search_internet", "crawl_web"]
      max_iterations: 10

    code_editor:
      system_prompt: "prompts/code_editor.md"
      tools: ["file", "execute_bash"]
      max_iterations: 5
"""
from __future__ import annotations

import os
import yaml
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentConfig:
    """Configuration for an agent."""

    name: str
    system_prompt: str = ""
    tools: List[str] = field(default_factory=list)
    max_iterations: int = 10
    context_files: List[str] = field(default_factory=list)

    # Optional settings
    temperature: Optional[float] = None
    think_mode: bool = True

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> "AgentConfig":
        """Create config from dict."""
        return cls(
            name=name,
            system_prompt=data.get("system_prompt", ""),
            tools=data.get("tools", []),
            max_iterations=data.get("max_iterations", 10),
            context_files=data.get("context_files", []),
            temperature=data.get("temperature"),
            think_mode=data.get("think_mode", True)
        )


DEFAULT_CONFIGS: Dict[str, Dict[str, Any]] = {
    "main_agent": {
        "system_prompt": "prompts/main_agent.md",
        "tools": ["execute_bash", "file", "search_internet", "crawl_web"],
        "max_iterations": 10,
        "context_files": ["state/PROJECT.md"]
    },
    "code_editor": {
        "system_prompt": "prompts/code_editor.md",
        "tools": ["file", "execute_bash"],
        "max_iterations": 5
    },
    "researcher": {
        "system_prompt": "prompts/researcher.md",
        "tools": ["search_internet", "crawl_web"],
        "max_iterations": 3
    }
}


def load_agent_configs(config_path: str = "agents.yaml") -> Dict[str, AgentConfig]:
    """
    Load agent configurations from YAML file.

    Falls back to defaults if file not found.

    Args:
        config_path: Path to agents.yaml

    Returns:
        Dict mapping agent names to configs
    """
    configs = {}

    # Try to load from file
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                data = yaml.safe_load(f) or {}

            for name, cfg_data in data.items():
                configs[name] = AgentConfig.from_dict(name, cfg_data)

        except (yaml.YAMLError, IOError) as e:
            print(f"[agents] Could not load config: {e}. Using defaults.")
            configs = _get_default_configs()
    else:
        configs = _get_default_configs()

    return configs


def _get_default_configs() -> Dict[str, AgentConfig]:
    """Get default agent configurations."""
    return {
        name: AgentConfig.from_dict(name, data)
        for name, data in DEFAULT_CONFIGS.items()
    }
