"""
AGENTS MODULE - Agent Definitions and Orchestration

Provides:
- AgentConfig: Configuration for individual agents
- AgentManager: Creates and manages agents
- Orchestrator: Coordinates main agent and sub-agents

This module is designed for future expansion of sub-agent capabilities.

USAGE:
    from agents import AgentConfig, AgentManager

    # Create agent from config
    manager = AgentManager()
    main_agent = manager.create_agent("main")
"""
from .config import AgentConfig, load_agent_configs
from .manager import AgentManager

__all__ = ["AgentConfig", "AgentManager", "load_agent_configs"]
