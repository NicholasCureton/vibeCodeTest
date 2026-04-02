# Payload Customization Mini Tutorial

## Quick Start

**For Qwen 3.5 (default):** No changes needed - already configured.

**For other models:** Copy your model's config from `data/model_configs.json` to `data/settings.json`.

---

## Understanding `model_config`

Located in `data/settings.json`:

```json
{
    "model_config": {
        "name": "qwen-3.5",
        "has_thinking_mode": true,
        "thinking_disable_payload": {
            "stop": ["Thinking Process:", "ikka", "otta"],
            "chat_template_kwargs": {"enable_thinking": false}
        },
        "extra_payload": {}
    }
}
```

### Fields Explained

| Field | When Sent | Purpose |
|-------|-----------|---------|
| `name` | Never | Your reference label |
| `has_thinking_mode` | Never | Does model support reasoning? |
| `thinking_disable_payload` | `/think_off` | Payload to disable thinking |
| `extra_payload` | Always | Additional params for every request |

---

## Common Customizations

### 1. Change Model (Qwen 3.5 → Llama 3)

**Step 1:** Open `data/model_configs.json`

**Step 2:** Find `llama-3` section:
```json
"llama-3": {
    "name": "llama-3",
    "has_thinking_mode": false,
    "thinking_disable_payload": {},
    "extra_payload": {
        "stop": ["<|eot_id|>", "<|end_of_text|>"]
    }
}
```

**Step 3:** Replace in `data/settings.json`:
```json
"model_config": {
    "name": "llama-3",
    "has_thinking_mode": false,
    "thinking_disable_payload": {},
    "extra_payload": {
        "stop": ["<|eot_id|>", "<|end_of_text|>"]
    }
}
```

**Done!** Restart and use Llama 3.

---

### 2. Add Custom Parameters

Want to always send `max_tokens` and `repetition_penalty`?

```json
{
    "model_config": {
        "name": "custom",
        "has_thinking_mode": false,
        "thinking_disable_payload": {},
        "extra_payload": {
            "max_tokens": 8192,
            "repetition_penalty": 1.2
        }
    }
}
```

---

### 3. Configure Thinking Mode (Qwen 3 / DeepSeek-R1)

**Qwen 3 (stop tokens only):**
```json
{
    "name": "qwen-3",
    "has_thinking_mode": true,
    "thinking_disable_payload": {
        "stop": ["Thinking Process:", "ikka", "otta"]
    },
    "extra_payload": {}
}
```

**DeepSeek-R1 (reasoning budget):**
```json
{
    "name": "deepseek-r1",
    "has_thinking_mode": true,
    "thinking_disable_payload": {
        "reasoning_budget": 0
    },
    "extra_payload": {
        "max_tokens": 64000
    }
}
```

---

### 4. Completely Custom Model

Unknown model? Start blank and add what you need:

```json
{
    "model_config": {
        "name": "my-custom-model",
        "has_thinking_mode": false,
        "thinking_disable_payload": {},
        "extra_payload": {}
    }
}
```

Then test and add params as needed:
```json
"extra_payload": {
    "stop": ["<END>"],
    "max_tokens": 4096
}
```

---

## Testing Your Config

```bash
# 1. Start llama.cpp server with your model
llama-server --model your-model.gguf

# 2. Test basic chat
python run.py "Hello"

# 3. Test thinking toggle (if applicable)
python run.py
>>> /think_off
>>> Does it stop reasoning?

# 4. Check server logs for actual payload
```

---

## Troubleshooting

### Problem: Thinking not disabling

**Check:** `has_thinking_mode` is `true` and `thinking_disable_payload` has correct params.

**Qwen 3.5:** Needs both `stop` tokens AND `chat_template_kwargs`

**Qwen 3:** Needs only `stop` tokens

**Other models:** Set `has_thinking_mode: false`

---

### Problem: Params not being sent

**Check:** Params are in `extra_payload`, not at root level.

❌ Wrong:
```json
{
    "model_config": {...},
    "max_tokens": 8192
}
```

✅ Correct:
```json
{
    "model_config": {
        "extra_payload": {
            "max_tokens": 8192
        }
    }
}
```

---

### Problem: Server rejects payload

**Check:** Your model actually supports those params. Not all OpenAI-compatible servers support `top_k`, `min_p`, etc.

**Solution:** Remove unsupported params from `extra_payload`.

---

## Reference

- `data/model_configs.json` - 15+ pre-configured models
- `MODEL_CONFIG.md` - Full configuration guide
- `data/settings.json` - Your active configuration

---

## Need Help?

1. Check if your model is in `data/model_configs.json`
2. Copy that config exactly
3. Test with `/think_off` command
4. Adjust based on actual behavior

**Remember:** Model configs are starting points. Real behavior may vary by llama.cpp version and server setup.
