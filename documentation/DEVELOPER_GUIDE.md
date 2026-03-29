# Developer Guide - CLI LLM Chat Inference Program V5

This guide is designed to help you **understand the code**, **debug issues**, and **add features**. Each section explains WHAT the code does, HOW it works, and WHERE to look for problems.

---

## Table of Contents

1. [Quick Start: Understanding How Code Flows](#quick-start)
2. [Tool System Deep Dive](#tool-system)
3. [Debugging Guide](#debugging-guide)
4. [Adding New Tools](#adding-new-tools)
5. [Common Issues & Solutions](#common-issues)
6. [Code Flow Diagrams](#code-flow)

---

## Quick Start: Understanding How Code Flows

### The Big Picture

When you run `python main.py`, here's what happens:

```
1. main.py starts → loads settings, creates LLM client, chat history
2. User types message in terminal
3. Chat loop calls llm_client.call(messages) 
4. LLM returns response (text OR tool_calls)
5. If tool_calls exist: execute tools via registry
6. Tool results go back to LLM → final response
7. Response displayed in terminal
```

### Key Files and Their Responsibilities

| File | What It Does | When You'll Touch This |
|------|--------------|------------------------|
| `main.py` | **Entry point** - runs the chat loop, handles user input | Most things (90%) |
| `tools/registry.py` | **Tool manager** - stores tools, executes them | Adding new tools |
| `memory/chat_history.py` | Saves/loads conversation history | Persistent state issues |
| `ui.py` | Prints colored messages to terminal | Display/formatting bugs |
| `settings.py` | Manages LLM parameters (temperature, etc.) | Parameter validation issues |
| `llm/client.py` | Talks to llama.cpp server via HTTP | Connection/LLM bugs |

---

## Tool System Deep Dive

### How Tools Work (Step-by-Step)

Every tool has **3 parts**:

```python
# Part 1: Schema (JSON format for LLM to understand)
MY_SCHEMA = {
    "type": "function",
    "function": {
        "name": "my_tool",           # How LLM calls it
        "description": "...",         # What the tool does
        "parameters": {...}           # Input arguments
    }
}

# Part 2: Handler function (actual implementation)
def my_handler(arg1, arg2):
    return ToolResult(success=True, output="result")

# Part 3: Registration (connects schema to handler)
register_tool("my_tool", my_handler, MY_SCHEMA, "Description")
```

### Where Tools Register Themselves

When Python imports a module, code at the **bottom** runs automatically. Look for `register_tool(...)` statements:

- `tools/bash_tool.py` → registers `execute_bash` (line 112)
- `tools/lft_tool.py` → registers `lft` (line 258)
- `tools/web_tool.py` → registers `search_internet` and `crawl_web` (lines 333, 341)

### How Tools Get Called

In `main.py`, lines 466-498:

```python
# User message arrives → LLM calls execute_bash with {"command": "ls"}
tool_name = "execute_bash"
arguments_json = '{"command": "ls"}'

# Registry executes the tool
result = execute(
    tool_name="execute_bash",
    arguments=arguments_json,  # Can be string or dict
    timeout=settings.get("bash_timeout", 60)
)

# result is a ToolResult: {success, output, exit_code, error}
```

### The Tool Result Format

Every tool must return this structure (defined in `core/__init__.py`):

```python
class ToolResult:
    success: bool      # True if no errors
    output: str        # What the tool produced
    exit_code: int     # 0 = success, non-zero = error
    error: Optional[str] | None = None  # Error message if failed
```

**Example:**
```python
# Success case:
return ToolResult(
    success=True,
    output="file list",
    exit_code=0
)

# Error case:
return ToolResult(
    success=False,
    output="",
    error="File not found",
    exit_code=1
)
```

---

## Debugging Guide

### Problem: Tool doesn't work / LLM says "tool not found"

**Cause:** Tool isn't registered.

**Solution:** 
1. Check the tool file imports `register_tool` from registry
2. Make sure there's a `register_tool(...)` call at the BOTTOM of the file (after all functions defined)
3. Restart Python - tools register on import, not runtime

### Problem: Tool execution fails silently

**Cause:** Error in handler function is caught and wrapped.

**Solution:** 
1. Look at `main.py` line 485-486 - it handles errors:
   ```python
   tool_content = result.output
   if not result.success and result.error:
       tool_content = f"ERROR: {result.error}\n\nOutput: {result.output}"
   ```
2. Add print statements in your handler to see what's happening

### Problem: File operations don't work (lft tool)

**Cause:** LFT module errors are wrapped with exit code 1.

**Solution:** 
1. In `tools/lft_tool.py`, line 231-237 wraps LFTError
2. The error message includes the original LFT error + hint
3. Always check the `.bak` file - it's saved before edits

### Problem: Chat history gets corrupted

**Cause:** JSONL file format issues.

**Solution:** 
1. Check `memory/chat_history.py` line 107-129 for loading logic
2. Each line must be valid JSON with "role" field
3. Use `/clear` command in interactive mode to reset

### Problem: LLM can't see files after /read

**Cause:** File content not properly formatted or context limit reached.

**Solution:** 
1. Check `main.py` lines 208-257 - file reading logic
2. Files are wrapped with `[FILE: filename]\ncontent\n[END filename]` markers
3. Context limit is checked in LLM client (line 192 of client.py)

---

## Adding New Tools

### Step-by-Step Guide

Let's add a tool called `file_copy` that copies files using the lft tool:

**1. Create the handler function:**

```python
# In tools/new_tool.py or existing file

def copy_file(src_path: str, dest_path: str) -> ToolResult:
    """Copy a file from src to dest."""
    
    # Validate inputs
    if not src_path or not dest_path:
        return ToolResult(
            success=False,
            output="",
            error="Source and destination paths required"
        )
    
    # Check source exists (use lft tool)
    check_result = execute("lft", {
        "command": "info",
        "file_path": src_path
    })
    
    if not check_result.success:
        return ToolResult(
            success=False,
            output="",
            error=f"Source file not found: {src_path}"
        )
    
    # Check destination doesn't exist (optional)
    dest_exists = execute("lft", {
        "command": "info",
        "file_path": dest_path
    })
    
    if dest_exists.success:  # Info succeeded means file exists
        return ToolResult(
            success=False,
            output="",
            error=f"Destination already exists: {dest_path}"
        )
    
    # Use lft to copy (write content from src to dest)
    with open(src_path, 'r') as f:
        content = f.read()
    
    result = execute("lft", {
        "command": "write",
        "file_path": dest_path,
        "new_string": content
    })
    
    if result.success:
        return ToolResult(
            success=True,
            output=f"Copied {src_path} to {dest_path}",
            exit_code=0
        )
    else:
        return ToolResult(
            success=False,
            output="",
            error=f"Copy failed: {result.error}"
        )
```

**2. Create the schema:**

```python
COPY_FILE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "copy_file",
        "description": (
            "Copy a file from one location to another. "
            "Use this when you need to duplicate files."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "src_path": {
                    "type": "string",
                    "description": "Path to source file (can use ~ for home directory)"
                },
                "dest_path": {
                    "type": "string",
                    "description": "Destination path"
                }
            },
            "required": ["src_path", "dest_path"]
        }
    }
}
```

**3. Register the tool:**

```python
# At the bottom of tools/new_tool.py (after all code)
register_tool(
    name="copy_file",
    function=copy_file,
    schema=COPY_FILE_SCHEMA,
    description="Copy a file from one location to another"
)
```

**4. Test it:**

In `main.py`, you can now call:
```python
result = execute("copy_file", {
    "src_path": "/workspace/test.txt",
    "dest_path": "/workspace/copy_of_test.txt"
})
print(result.output)
```

---

## Common Issues & Solutions

### Issue 1: Tool executes but LLM doesn't see the result

**Symptom:** User sees tool output, but next response ignores it.

**Root Cause:** The result isn't being added to chat history properly.

**Fix:** Check `main.py` lines 493-498 - make sure you're calling:
```python
chat_history.save(
    role="tool",
    content=tool_content,
    tool_call_id=tool_call_id
)
history.append(tool_result_msg)
```

### Issue 2: LLM keeps asking to use a tool in loop

**Symptom:** Same tool called repeatedly without progress.

**Root Cause:** Tool is failing silently or returning vague success.

**Fix:** 
1. Make sure `ToolResult.success` is False when there's an error
2. Include detailed error messages in `.error` field
3. Check that the schema parameters match what your handler expects

### Issue 3: "Unknown tool" error at runtime

**Symptom:** Tool worked before, now says not found.

**Fix:** 
1. Tools register on **import**, not runtime
2. If you added a new tool file, restart Python or reload modules
3. Check `tools/__init__.py` imports all tool files (lines 40-42)

### Issue 4: File operations show wrong line numbers in lft output

**Symptom:** `/read` shows correct content, but `/edit` at same line fails.

**Fix:** 
1. This is expected - LFT uses 1-based line numbering
2. When editing, copy the **exact text** from read output (including whitespace)
3. Check indentation: spaces vs tabs matter! Use the `[S:N]` and `[T:N]` markers in read output

### Issue 5: Bash commands don't execute

**Symptom:** `execute_bash` tool called but no terminal output.

**Fix:** 
1. Check `tools/bash_tool.py` line 72-83 - it uses subprocess
2. Make sure the command is a valid bash command
3. Check exit_code in ToolResult - non-zero means failure
4. Look at stderr in result.output (stdout + stderr combined)

---

## Code Flow Diagrams

### Chat Loop Flow (`main.py` lines 264-506)

```
┌─────────────────────┐
│ User types message │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Add to chat history │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ LLM.call(messages)  │ ◄── Sends tools, gets response chunks
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Parse streaming     │ ◄── Extract content, reasoning, tool_calls
│ response            │
└──────────┬──────────┘
           │
    ┌──────┴──────┐
    │             │
    ▼             ▼
No tools   Has tools?
    │             │
    ▼             ▼
  Done     Execute each tool
         │        │
         ▼        ▼
   Wait      Get ToolResult
           │        │
           └───────┬┘
                   │
                   ▼
            Add result to history
            (role: "tool")
                   │
                   ▼
           Send back to LLM
                   │
                   ▼
              Final response
```

### Tool Registration Flow (`tools/registry.py`)

```
Import tools module
       │
       ├── bash_tool.py ──► register_tool("execute_bash", ...)
       ├── lft_tool.py  ──► register_tool("lft", ...)
       ├── web_tool.py  ──► register_tool("search_internet", ...)
       └── web_tool.py  ──► register_tool("crawl_web", ...)
              │
              ▼
         _tools dict populated
              │
              ▼
        Can call execute()
```

### Tool Execution Flow (`main.py` lines 465-498)

```
LLM requests tool "execute_bash" with {"command": "ls"}
       │
       ▼
registry.execute("execute_bash", arguments_json, timeout=60)
       │
       ▼
Get tool from _tools dict
       │
       ▼
Parse arguments (if string → JSON)
       │
       ▼
Call tool["function"](**args, timeout=exec_timeout)
       │
       ▼
Handler returns ToolResult(success=True/False, output, error, exit_code)
       │
       ▼
Return to main.py
```

---

## Quick Reference: Where Things Happen

### To modify how tools are displayed:
**File:** `ui.py`, lines 109-168 (`display_tool_call` function)

### To change what commands users can type:
**File:** `main.py`, lines 616-709 (command handling in interactive loop)

### To add new LLM parameters:
**File:** `settings.py`, lines 28-48 (INTEGER_PARAMS, FLOAT_PARAMS, PARAM_RANGES)

### To change system prompt location:
**File:** `main.py`, line 193 (`default_path = .../prompts/main_agent.md`)

### To add new memory features:
**File:** `memory/chat_history.py` or `memory/project_state.py`

---

## Testing Tips

### Test a tool in isolation (without running main.py):

```python
# In a test script or interactive Python session
import sys
sys.path.insert(0, '/workspace/shared/cli_LLM_chat_inference_program/Cli_Chat_Inference_V5')

from tools import execute

# Test bash tool
result = execute("execute_bash", {"command": "echo 'hello'"}, timeout=10)
print(f"Success: {result.success}")
print(f"Output: {result.output}")
print(f"Exit code: {result.exit_code}")
```

### Test with mock LLM (no real server needed):

```bash
python main.py --mock "test message"
```

This uses `llm/mock_client.py` which simulates LLM responses.

---

## When to Look at Each File

| Problem Type | First File to Check | Secondary Files |
|--------------|---------------------|-----------------|
| Tool not registered | `tools/__init__.py` imports, then tool file's `register_tool()` call | `registry.py` |
| Tool executes but wrong result | Tool handler function | `main.py` execution logic (lines 465-498) |
| Chat history issues | `memory/chat_history.py` | `main.py` save calls (lines 392, 411, 421, 493) |
| Display/formatting issues | `ui.py` | Terminal colors (ANSI codes in ui.py lines 16-28) |
| LLM connection problems | `llm/client.py` | `settings.py` server_url |
| Parameter validation errors | `settings.py` update() function (lines 148-187) | CLI args in main.py |

---

## Final Checklist Before Adding Features

Before committing code changes:

- [ ] Tool handler returns proper `ToolResult` structure
- [ ] Tool has both schema AND registration call
- [ ] Added tests if modifying existing functionality
- [ ] Checked that new tools are imported in `tools/__init__.py`
- [ ] Verified tool doesn't crash on edge cases (empty strings, None values)
- [ ] Error messages are user-friendly (not internal Python errors)

---

## Getting Help When Stuck

1. **Add print debugging:**
   ```python
   # In any function being debugged
   import sys
   print(f"[DEBUG] entering {sys._getframe().f_code.co_name}", file=sys.stderr)
   ```

2. **Check ToolResult fields:**
   Always inspect all 4 fields after tool execution:
   ```python
   print(result.success, result.output, result.exit_code, result.error)
   ```

3. **Trace through main.py chat loop:**
   Add prints at lines 285 (user message), 393 (assistant response), 493 (tool result)

---

This guide should give you a solid foundation to understand the code and make changes confidently. Start with the "Quick Start" section, then dive into specific areas as needed.