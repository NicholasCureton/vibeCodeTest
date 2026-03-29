# LLM Bash Tool Efficiency Guide

## Core Principles

### 1. TOKEN EFFICIENCY (Token Optimization)
- **Search**: Use `grep` for speed, `rg` only when needed (PCRE2 support, git-aware)
- **File Reading**: Always use `cat` for LLM input—zero overhead vs bat markdown formatting
- **Discovery**: Use `fdfind --glob "*.py"` instead of find for cleaner output

```bash
# Optimal patterns
grep -r "pattern" /path --include="*.py"
cat /absolute/path/file.py  # Never use bat for LLM input
fdfind --glob "*.py" /project | head -100
```

### 2. SAFE FILE OPERATIONS
- **Write files**: Use heredocs (no escape sequences)
- **Avoid**: sed for replacements, interactive editors like vim/nano

```bash
cat > file.py << 'EOF'
def safe_function():
    return "clean code"
EOF
```

### 3. VERSION CONTROL PATTERN
Always stage changes atomically: `git add . && git commit -m "<type>(scope): <message>"`

## Four-Phase Workflow

| Phase | Goal | Key Commands |
|-------|------|--------------|
| **Research** | Find relevant code | git grep, git log -S, git status |
| **Plan** | Decide changes needed | Checklist: files affected, tests, compatibility |
| **Execute** | Apply modifications | Heredocs for writes, Python scripts for replacements |
| **Verify** | Confirm success | git diff --stat, syntax checks |

### Phase 1: Research & Discovery
```bash
# Search patterns across codebase
git grep "pattern" -- "*.py" --line-number

# Find when code changed in history  
git log -S"old_text" --oneline

# List affected files only
git grep -l "pattern" -- "*.py"
```

### Phase 2: Planning Checklist
- Does this change affect multiple files?
- Are tests that need updating?
- Is backward compatibility maintained?
- Commit message clear and complete?

### Phase 3: Execution Methods

**Method A - Heredoc (Clean Writes)**
```bash
# Get clean copy, write safely, commit atomically
git checkout HEAD -- file.py
cat > /tmp/new_content.py << 'EOF'
def new_function(): pass
EOF
cp /tmp/new_content.py file.py && git add . && git commit -m "Add feature"
```

**Method B - Python Script (Pattern Replacement)**
```bash
python3 << 'PY'
import re, os
for f in ["file1.py", "file2.py"]:
    with open(f) as fp: content = fp.read()
    content = re.sub(r'\bOLD_PATTERN\b', 'NEW_CODE', content)
    with open(f, 'w') as fp: fp.write(content)
PY
git add . && git commit -m "Replace patterns"
```

### Phase 4: Verification & Safety
```bash
# Check changes before committing
git diff --stat                    # See affected files
python3 -m py_compile file.py      # Syntax check
```

## Git Command Quick Reference

| Task | Command |
|------|---------|
| Current status | git status |
| Stage all changes | git add . |
| View unstaged diff | git diff |
| Search in history | git log -S"text" |
| Get file from commit | git show HASH:file.py |
| Create branch | git checkout -b feature-name |

## Multi-Language Support

**Python**: Use built-in ast module for safe transformations
```python
import ast
tree = ast.parse(code)  # Safe symbol extraction/modification
```

**JavaScript/TypeScript**: Run `node --check file.js` for syntax validation

**Go**: Run go vet before committing changes

## Best Practices Summary

1. Always use absolute paths—avoid shell expansion issues
2. Filter output before LLM context—dont send full files
3. Stage all related changes atomically (git add .)
4. Use heredocs for file writes—no escape headaches
5. Verify syntax/compilation after modifications
6. Write clear commit messages (<type>(scope): <subject>)

## Safety Checklist

Before committing:
- git status shows expected changes only
- git diff --cached --stat confirms files to modify
- Syntax checked (py_compile, node --check, etc.)
- No conflict markers in staged content
- Commit message follows convention

---
*Concise Guide: Token Efficiency + Safe LLM Bash Operations - Under 500 words*
