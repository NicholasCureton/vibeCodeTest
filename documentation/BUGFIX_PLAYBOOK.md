# Bug Fix Playbook - CLI LLM Chat Inference Program V5

This playbook provides **step-by-step procedures** for fixing common bugs. Each section tells you exactly what to do, where to look, and how to verify the fix worked.

---

## Quick Reference: What Problem → Where to Look

| Symptom | Location | Section Below |
|---------|----------|---------------|
| Tool not found / "Unknown tool" | `tools/__init__.py` imports or tool registration | [Tool Registration Issues](#tool-registration-issues) |
| Tool executes but returns wrong result | Handler function implementation | [Wrong Tool Behavior](#wrong-tool-behavior) |
| LLM can't connect to server | `llm/client.py`, network settings | [LLM Connection Problems](#llm-connection-problems) |
| Chat history corrupt / loading fails | `memory/chat_history.py` | [Chat History Corruption](#chat-history-corruption) |
| File operations show wrong lines | LFT tool, line numbers | [File Operation Issues](#file-operation-issues) |
| Bash commands don't run | `tools/bash_tool.py`, subprocess | [Bash Tool Not Working](#bash-tool-not-working) |
| Web search/crawl fails | `tools/web_tool.py`, dependencies | [Web Tools Failing](#web-tools-failing) |
| Parameters out of range / validation errors | `settings.py` | [Parameter Validation Issues](#parameter-validation-issues) |
| UI shows wrong colors/formatting | `ui.py`, ANSI codes | [Display/Formatting Issues](#display-formatting-issues) |

---

## Tool Registration Issues

### Symptom: LLM says "tool not found" or "Unknown tool: <name>"

**Cause:** Tool isn't in the registry (not imported or not registered).

### Step-by-Step Fix:

#### Step 1: Verify the tool file exists and has correct structure
```bash
# Check tools directory
ls /workspace/shared/cli_LLM_chat_inference_program/Cli_Chat_Inference_V5/tools/

# Look for your new tool or check existing ones
cat tools/bash_tool.py | grep -A 20 "register_tool"
```

**Expected output:** The file should end with `register_tool(...)` call.

#### Step 2: Check that the tool imports registry correctly
Open the tool file and verify line ~18-19:
```python
from tools.registry import register_tool
# OR
from tools import register_tool
```

**Fix:** If missing, add the import at the top of the file.

#### Step 3: Check that `register_tool()` is called at module level (bottom of file)
Look for this pattern at the END of the tool file (after all function definitions):
```python
register_tool(
    name="tool_name",           # Must match schema's "name" field exactly!
    function=handler_function,  # The handler defined above
    schema=TOL_SCHEMA_VAR_NAME, # Schema variable defined earlier
    description="..."           # Human-readable description
)
```

**Fix:** If missing, add it at the bottom of the file. Make sure `name` matches exactly what's in the schema.

#### Step 4: Verify tools/__init__.py imports all tool files
Open `tools/__init__.py`, check lines 40-42:
```python
from tools import bash_tool
from tools import lft_tool
from tools import web_tool
```

**Fix:** If you added a new tool file, add an import here too.

#### Step 5: Restart Python
Tools register on **import**, not at runtime. You MUST restart the interpreter after adding/modifying tools.

---

### Verification:
```python
# In main.py or test script
from tools import list_tools, get_schemas

print("Available tools:", list_tools())
print("\nTool schemas count:", len(get_schemas()))
```

If your tool appears in the output, registration is working.

---

## Wrong Tool Behavior

### Symptom: Tool executes but returns incorrect/wrong result

**Cause:** Handler function logic is wrong, or ToolResult fields are set incorrectly.

### Step-by-Step Fix:

#### Step 1: Add debug prints to see what's happening
In your handler function, add these at key points:
```python
def my_handler(arg1: str) -> ToolResult:
    import sys
    
    # Log entry
    print(f"[DEBUG] Handler called with arg1='{arg1}'", file=sys.stderr)
    
    # Your logic here...
    result = ...
    
    # Log before return
    print(f"[DEBUG] Returning success={True}, output='test'", file=sys.stderr)
    
    return ToolResult(success=True, output="result")
```

#### Step 2: Check all four ToolResult fields are correct
Every tool must return this structure:
```python
return ToolResult(
    success=bool,        # True = no errors, False = error occurred
    output=str,          # What the tool produced (or empty string on failure)
    exit_code=int,       # 0 = success, non-zero = error type
    error=str or None    # Error message if success=False
)
```

**Common mistakes:**
- Setting `success=True` but with an error in `.error` → LLM thinks it worked
- Returning empty output without setting `success=False` → User sees nothing
- Wrong exit code (should be 0 for success, non-zero for different error types)

#### Step 3: Verify the tool is being called with correct arguments
In `main.py`, look at lines 465-470 where tools are executed. The arguments come from LLM's tool call.

Add debug to see what arguments your tool receives:
```python
def my_handler(arg1: str, timeout: int = 60) -> ToolResult:
    print(f"[DEBUG] Received args: arg1='{arg1}', timeout={timeout}", file=sys.stderr)
    # ... rest of handler
```

#### Step 4: Check for type mismatches
If your schema says `"type": "string"` but you expect a number, Python will pass it as string.

**Fix:** Either:
- Convert in the handler: `value = int(arg1)`  
- Or update schema to match actual usage

#### Step 5: Test tool in isolation (bypassing LLM)
```python
from tools import execute

result = execute("my_tool", {"arg1": "test_value"}, timeout=30)
print(f"Result: {result}")
print(f"Success: {result.success}, Output: '{result.output}', Error: '{result.error}'")
```

If this works but LLM calling fails, the issue is in how you're formatting arguments.

---

### Verification:
Run your tool and check that:
1. Debug prints show expected input values
2. ToolResult fields have correct types (bool, str, int)
3. Output matches what you expect

---

## LLM Connection Problems

### Symptom: "Connection refused", "Request timed out", or similar errors

**Cause:** Can't connect to llama.cpp server, or wrong URL/port.

### Step-by-Step Fix:

#### Step 1: Check if llama.cpp server is running
```bash
# Check what's listening on port 8080
netstat -tlnp | grep 8080

# Or try connecting manually
curl http://localhost:8080/v1/chat/completions

# If nothing, start the server
cd /path/to/llama.cpp
python3 llama-server -c model.gguf -l 8192 --host 0.0.0.0
```

#### Step 2: Verify server_url in settings.py
Open `settings.py` line 59-60 and line 170 of main.py (load_system_prompt):
```python
"server_url": "http://localhost:8080",  # Default value
```

If your llama.cpp is on a different port/host, change this.

#### Step 3: Check that model.gguf file exists
Open `settings.py` line 61 and verify the path to your model file is correct.

#### Step 4: Test connection manually from Python
```python
import requests

url = "http://localhost:8080/v1/chat/completions"
response = requests.get(url, timeout=5)
print(f"Status: {response.status_code}")
print(f"Response: {response.text[:200]}")
```

#### Step 5: Check firewall/network settings
If server is on remote machine:
```bash
# Allow connections to port 8080
sudo ufw allow 8080/tcp
# Or check firewall rules
sudo iptables -L | grep 8080
```

---

### Verification:
- `curl` returns JSON (not connection error)
- Python test script gets response with status 200
- Can call `/props` endpoint to get context limit

---

## Chat History Corruption

### Symptom: "Could not read chat history", corrupted file, or messages missing

**Cause:** Invalid JSON in history file, or file got modified while open.

### Step-by-Step Fix:

#### Step 1: Check the history file format
```bash
# Find where chat_history.jsonl is
find /workspace -name "chat_history.jsonl" 2>/dev/null

# Open and check first few lines
cat ~/chat_history.jsonl | head -5
```

**Expected format:** Each line must be valid JSON:
```json
{"role": "user", "content": "..."}
{"role": "assistant", "content": "...", "tool_calls": [...]}
```

#### Step 2: Validate each line is proper JSON
```bash
# Check for malformed lines
python3 -c "
import json, sys
with open('chat_history.jsonl', 'r') as f:
    for i, line in enumerate(f, 1):
        try:
            json.loads(line.strip())
        except Exception as e:
            print(f'Line {i} invalid JSON: {e}')
"
```

#### Step 3: Fix the file manually
If you find bad lines:
```bash
# Create a clean version, skipping bad lines
python3 -c "
import json
with open('chat_history.jsonl', 'r') as f:
    valid = []
    for line in f:
        try:
            msg = json.loads(line.strip())
            if 'role' in msg:  # Skip empty or invalid lines
                valid.append(msg)
        except:
            pass

with open('chat_history.jsonl.new', 'w') as f:
    for msg in valid:
        f.write(json.dumps(msg) + '\n')
"

# Replace original
mv chat_history.jsonl.new chat_history.jsonl
```

#### Step 4: Clear history and start fresh (easiest fix)
In interactive mode, type:
```
/clear
```

Or delete the file entirely - it will be recreated automatically.

---

### Verification:
- Can load history without errors
- Messages appear in chat when you run `/read` or continue chatting
- File passes JSON validation test

---

## File Operation Issues

### Symptom: LFT tool says "No match found", wrong line numbers, or edit fails

**Cause:** Text doesn't match exactly (whitespace differences), or using wrong line numbers.

### Step-by-Step Fix:

#### Step 1: Always read first, then copy EXACT text
```bash
# WRONG - editing without reading
lft command=edit file_path=/path/file.py old_string="some_text" new_string="new_text"

# RIGHT - always read first to see exact whitespace
lft command=read file_path=/path/file.py
```

The read output shows:
- `[T:N]` = N tab characters
- `[S:N]` = N space characters

**Example:**
```
Line 10: [S:4]def my_function():  ← 4 spaces before "def"
Line 15: [T:2]if condition:      ← 2 tabs before "if"
```

#### Step 2: Copy the EXACT whitespace from read output
When editing, copy the text INCLUDING all spaces/tabs. Don't paste from browser - it strips whitespace!

**Best practice:** Use terminal copy/paste (Ctrl+Shift+C/V), not mouse selection.

#### Step 3: Verify old_string matches exactly before editing
```bash
# Preview what will be replaced (dry run)
lft command=edit file_path=/path/file.py old_string="exact text with whitespace" new_string="" dry_run=true
```

If it says "No match found", your `old_string` doesn't match the file.

#### Step 4: For edits that span multiple lines, use multiedit
Single-line edits require exact match. Use multiedit for complex changes:

```bash
# Create a file with your changes (OLD/NEW format)
cat > /tmp/multiedits.txt << 'EOF'
OLD: [S:4]def my_function():[S:8]    pass[NEW: [S:4]def my_function():[S:8]    # TODO: implement[NEW: [S:12]    pass
EOF

lft command=multiedit file_path=/path/file.py multiedit_content="$(cat /tmp/multiedits.txt)" backup=true dry_run=true
```

#### Step 5: After editing, verify the change
Always do a second read to confirm:
```bash
lft command=read file_path=/path/file.py start_line=10 end_line=20
```

---

### Verification:
- `dry_run=true` shows what will be changed (and nothing changes)
- After actual edit, read again and see the new content
- Check `.bak` file exists if backup was created

---

## Bash Tool Not Working

### Symptom: execute_bash tool called but no output or command fails silently

**Cause:** Subprocess issues, command syntax errors, or security restrictions.

### Step-by-Step Fix:

#### Step 1: Check the actual command being executed
Add debug to bash_tool.py (lines 72-83):
```python
try:
    print(f"[DEBUG] Executing command: {command}", file=sys.stderr)
    process = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout
    )
    
    output = process.stdout
    if process.stderr:
        print(f"[DEBUG] Stderr: {process.stderr}", file=sys.stderr)
        output += "\n" + process.stderr
    
    return ToolResult(
        success=process.returncode == 0,
        output=output.strip() if output.strip() else "(no output)",
        exit_code=process.returncode
    )
```

#### Step 2: Test the command directly in terminal
```bash
# Run exact same command manually
command

# Check if it works at shell level
echo $?  # Exit code
```

If it doesn't work manually, fix the command itself.

#### Step 3: Check for permission issues
Some commands need sudo or special permissions:
```python
# Bad - might fail silently
result = execute("execute_bash", {"command": "rm /tmp/file"})

# Good - check error output
print(result.error)  # Should show permission denied if applicable
```

#### Step 4: Verify timeout isn't cutting off long commands
If command takes >60 seconds, it times out. Adjust in `settings.py`:
```python
"bash_timeout": 120,  # Increase from default 60
```

Or pass different timeout per command (though tools don't support this yet).

#### Step 5: Check if shell=True is causing issues
If your command has special characters that need escaping:
```python
# This might fail due to shell interpretation
result = execute("execute_bash", {"command": "echo $HOME/test"})

# Try without shell (safer, but needs proper quoting)
# Not directly supported - would require custom tool implementation
```

---

### Verification:
- Debug prints show the command being executed
- `process.returncode` is 0 for success commands
- Output contains expected content
- No timeout errors in stderr

---

## Web Tools Failing

### Symptom: search_internet or crawl_web returns error about missing packages

**Cause:** Required Python packages not installed.

### Step-by-Step Fix:

#### For search_internet tool:

```bash
# Install the package (note: ddgs is newer name)
pip install ddgs

# Or if that doesn't work, try old name
pip install duckduckgo_search
```

Then verify:
```python
from tools import execute
result = execute("search_internet", {"query": "test"}, timeout=30)
print(result.output[:500])  # Should show search results
```

#### For crawl_web tool:

```bash
# Install Crawl4AI
pip install crawl4ai

# Install Playwright browser (required by crawl4ai)
playwright install chromium

# Verify installation
python3 -c "import crawl4ai; print('OK')"
```

The error message in `web_tool.py` line 317 tells you exactly what to run:
```
"crwl not found. Install: pip install crawl4ai && playwright install chromium"
```

---

### Verification:
- Search returns results with titles and URLs
- Crawl returns markdown content from website
- No ImportError or AttributeError in error messages

---

## Parameter Validation Issues

### Symptom: "Parameter out of range", "Invalid value for <param>", etc.

**Cause:** Trying to set parameter outside valid range, or wrong type (string vs number).

### Step-by-Step Fix:

#### Step 1: Check valid ranges in settings.py
Lines 39-48 define all parameter ranges:
```python
PARAM_RANGES = {
    "temperature": (0.0, 2.0),        # Must be between 0 and 2
    "top_p": (0.0, 1.0),              # Must be between 0 and 1
    "max_agent_iterations": (1.0, 200.0),  # Integer, 1 to 200
}
```

#### Step 2: Check parameter type requirements
- INTEGER_PARAMS (line 28): `top_k`, `max_agent_iterations` - must be int
- FLOAT_PARAMS (line 30): temperature, top_p, etc. - will convert to float
- STRING_PARAMS (line 34): system_prompt_path, server_url, model_name - keep as string

#### Step 3: Use correct update syntax in interactive mode
```
# WRONG - missing value
/temp

# RIGHT - provide the value
/temp 0.8

# WRONG - out of range
/temp 5.0

# RIGHT - within range
/temp 1.5
```

#### Step 4: Check settings.json for saved values
Sometimes a bad save persists:
```bash
cat /workspace/shared/cli_LLM_chat_inference_program/Cli_Chat_Inference_V5/settings.json | python3 -m json.tool
```

If you see wrong values, reset or edit the file.

#### Step 5: Reset to defaults if needed
In interactive mode (before starting chat):
```python
# Can't directly call reset(), but can delete settings.json
rm /workspace/shared/cli_LLM_chat_inference_program/Cli_Chat_Inference_V5/settings.json

# Or use Python to reset
from settings import reset
reset()  # Must run in main.py context, not standalone
```

---

### Verification:
- `/params` command shows correct values
- Can set parameter without validation errors
- Parameter persists after restart (if it was a string param)

---

## Display/Formatting Issues

### Symptom: Terminal output looks wrong, colors missing, or text cut off

**Cause:** ANSI color codes not rendering, or terminal width too small.

### Step-by-Step Fix:

#### Step 1: Check if your terminal supports colors
```bash
# Should show colored text
echo "Red: \033[91mRED\033[0m"
echo "Green: \033[92mGREEN\033[0m"

# If plain text, your terminal doesn't support ANSI codes
```

#### Step 2: Check ui.py color definitions
Lines 16-28 define the colors. These are standard ANSI codes that should work on any modern terminal.

If they don't work, you might need to configure your shell or use a different terminal emulator.

#### Step 3: Clear screen issues
```python
# In ui.py line 31-36
def clear_screen():
    if os.name == 'nt':      # Windows
        os.system('cls')
    else:                    # Unix/macOS
        print("\033[H\033[J", end="")
```

If screen doesn't clear, try running in a fresh terminal window.

#### Step 4: Streaming output issues
The streaming buffer (lines 78-106) might not flush properly if terminal is too slow or disconnected.

To see full output at once, don't use streaming - just read the final response.

---

### Verification:
- Colors appear in terminal
- Screen clears when expected
- Streaming text appears character by character (if using interactive mode)

---

## General Debugging Checklist

When encountering ANY bug, follow this checklist:

1. **Identify the exact error message** - Copy it exactly as shown
2. **Find where it's generated** - Search for the error string in code
3. **Add debug prints** around the failing line
4. **Check input values** - What are you passing to the function?
5. **Verify return types** - Are you returning what the function expects?
6. **Test in isolation** - Can you reproduce with minimal test case?
7. **Check logs** - stderr output often has more info than stdout

---

## Quick Fixes for Common Scenarios

### "Need to add a new tool" → See: Tool Registration Issues (Step 3-5)

### "Tool doesn't work after adding code" → Restart Python (tools register on import)

### "File edit says no match found" → Read file first, copy exact whitespace (including [T:N] and [S:N])

### "Can't connect to LLM server" → Check if llama.cpp is running with `netstat -tlnp | grep 8080`

### "Chat history corrupted" → Delete or `/clear` in interactive mode

### "Parameter out of range error" → Check PARAM_RANGES dict in settings.py, stay within bounds

---

## When All Else Fails

1. **Print everything:**
   ```python
   import sys
   def debug_print(*args):
       print('\n'.join(map(repr, args)), file=sys.stderr)
   
   # Add to top of function:
   debug_print("Entering", func_name, "with", locals())
   ```

2. **Use Python debugger:**
   ```python
   import pdb; pdb.set_trace()  # Drops into debugger at that line
   ```

3. **Check the actual file on disk vs what you edited:**
   Sometimes editors save wrong files or you're editing a copy:
   ```bash
   diff -u /path/to/expected_file.py <(cat /workspace/shared/cli_LLM_chat_inference_program/Cli_Chat_Inference_V5/tools/bash_tool.py)
   ```

---

This playbook should help you systematically fix any bug you encounter. Start with the Quick Reference table to find your issue, then follow the step-by-step instructions.