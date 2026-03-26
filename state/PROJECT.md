# CLI Chat Inference Client

## STATUS
State: In Progress
Last Updated: 2024-03-26

## GOAL
Build a CLI chat client with tool-calling capabilities that supports
sub-agent architecture for independent agent work on specific modules.

## ROADMAP
- [x] Basic CLI interface
- [x] Tool calling system
- [x] Chat history persistence
- [x] Modular architecture refactoring
- [ ] Sub-agent architecture
- [ ] Project state tracking (PROJECT.md)
- [ ] Memory management for long projects
- [ ] Agent handoff system

## WHAT'S DONE
- [x] Core module with base types and interfaces
- [x] LLM module with real and mock clients
- [x] Tools module with registry pattern
- [x] Memory module for history and project state
- [x] Agents module configuration

## WHAT'S IN PROGRESS
- [ ] Testing refactored codebase
- [ ] Documentation for adding new tools
- [ ] Documentation for adding new agents

## WHAT'S NEXT
1. Test with mock LLM client
2. Test with real llama.cpp server
3. Add more tool types
4. Implement sub-agent orchestration

## DECISIONS LOG
| Decision | Choice | Reason |
|----------|--------|--------|
| Module structure | Feature-based | Each module handles one concern |
| Tool registration | Registry pattern | Add tools without touching core code |
| LLM client | Protocol/interface | Easy to swap real/mock clients |
| Settings | JSON file | Simple, human-readable config |

## KNOWN ISSUES / BLOCKERS
- None currently

## WHAT TO AVOID
- Don't put business logic in main.py
- Don't hardcode tool schemas in multiple places
- Don't create circular imports between modules
- Don't skip the registry when adding tools

## FILES CHANGED THIS SESSION
- core/__init__.py - New base types
- llm/__init__.py - LLM module interface
- llm/client.py - Real LLM client
- llm/mock_client.py - Mock for testing
- tools/__init__.py - Tools module interface
- tools/registry.py - Tool registry
- tools/bash_tool.py - Bash execution
- tools/file_tool.py - File operations
- tools/web_tools.py - Search and crawl
- memory/__init__.py - Memory module
- memory/chat_history.py - Chat persistence
- memory/project_state.py - PROJECT.md management
- agents/__init__.py - Agents module
- agents/config.py - Agent configs
- agents/manager.py - Agent creation
- main.py - Entry point
- settings.py - Configuration
- ui.py - Terminal display
