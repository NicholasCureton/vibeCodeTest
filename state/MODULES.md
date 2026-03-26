# MODULE MAP

Defines file ownership for independent agent work.
Each module = a cluster of related files that one agent type can handle.

## MODULE: Core
**Owner**: Main Agent (coordinating)
**Purpose**: Base types, interfaces, constants
**Files**:
- core/__init__.py - Public interface and types

**Notes**:
- No dependencies on other project modules
- Only built-in Python imports
- Change carefully - other modules depend on this


## MODULE: LLM
**Owner**: Code Editor Agent
**Purpose**: LLM communication
**Files**:
- llm/__init__.py - Public interface
- llm/client.py - Real llama.cpp client
- llm/mock_client.py - Testing mock
- llm/types.py - Type definitions

**Notes**:
- Self-contained, no project dependencies
- Can swap implementations via interface
- Mock client for testing without server


## MODULE: Tools
**Owner**: Code Editor Agent
**Purpose**: Tool definitions and execution
**Files**:
- tools/__init__.py - Public interface
- tools/registry.py - Tool registration
- tools/bash_tool.py - Bash execution
- tools/file_tool.py - File operations
- tools/web_tools.py - Search and crawl

**Notes**:
- Add new tools by creating new file and importing in __init__.py
- Each tool self-registers on import
- Never modify registry directly - use register_tool()


## MODULE: Memory
**Owner**: Code Editor Agent
**Purpose**: Persistence and state
**Files**:
- memory/__init__.py - Public interface
- memory/chat_history.py - Conversation history
- memory/project_state.py - PROJECT.md management

**Notes**:
- Chat history uses JSONL format
- Project state uses markdown for readability


## MODULE: Agents
**Owner**: Code Editor Agent (with Main Agent oversight)
**Purpose**: Agent configuration and creation
**Files**:
- agents/__init__.py - Public interface
- agents/config.py - Configuration loading
- agents/manager.py - Agent creation

**Notes**:
- Agent definitions in agents.yaml (or use defaults)
- System prompts in prompts/ directory


## MODULE: UI
**Owner**: Code Editor Agent
**Purpose**: Terminal display
**Files**:
- ui.py - All terminal output

**Notes**:
- Self-contained
- No business logic


## MODULE: Entry Point
**Owner**: Main Agent
**Purpose**: Program entry and orchestration
**Files**:
- main.py - Entry point
- settings.py - Configuration

**Notes**:
- main.py wires everything together
- Keep minimal logic here


## SHARED FILES
Anyone can read, Main Agent coordinates writes:
- state/PROJECT.md - Project state
- state/MODULES.md - This file
- settings.json - User settings
- prompts/*.md - System prompts


## DIRECTORY STRUCTURE

```
cli_chat_refactored/
├── main.py              # Entry point
├── settings.py          # Configuration
├── ui.py                # Terminal display
│
├── core/                # Base types
│   └── __init__.py
│
├── llm/                 # LLM communication
│   ├── __init__.py
│   ├── client.py
│   ├── mock_client.py
│   └── types.py
│
├── tools/               # Tool implementations
│   ├── __init__.py
│   ├── registry.py
│   ├── bash_tool.py
│   ├── file_tool.py
│   └── web_tools.py
│
├── memory/              # Persistence
│   ├── __init__.py
│   ├── chat_history.py
│   └── project_state.py
│
├── agents/              # Agent management
│   ├── __init__.py
│   ├── config.py
│   └── manager.py
│
├── prompts/             # System prompts
│   └── main_agent.md
│
└── state/               # Project state
    ├── PROJECT.md
    └── MODULES.md
```


## HOW TO ADD A NEW TOOL

1. Create `tools/my_tool.py`
2. Define schema (OpenAI format)
3. Implement handler function (returns ToolResult)
4. Call `register_tool()` at module level
5. Import in `tools/__init__.py`

No changes to main.py or any other file needed!


## HOW TO ADD A NEW AGENT TYPE

1. Add definition to `agents/config.py` DEFAULT_CONFIGS
   OR create `agents.yaml` file
2. Create prompt file in `prompts/`
3. Agent automatically available via `AgentManager`
