# Model Configuration Guide

## Quick Start

1. Open `data/model_configs.json`
2. Find your model
3. Copy the `model_config` section
4. Paste into `data/settings.json`

## Example: Switch to Llama 3

**In `data/settings.json`:**
```json
{
    "model_config": {
        "name": "llama-3",
        "has_thinking_mode": false,
        "thinking_disable_payload": {},
        "extra_payload": {
            "stop": ["<|eot_id|>", "<|end_of_text|>"]
        }
    }
}
```

## Configuration Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Model identifier |
| `has_thinking_mode` | boolean | Does model support thinking? |
| `thinking_disable_payload` | object | Payload when `/think_off` |
| `extra_payload` | object | Additional params |

## Supported Models

See `data/model_configs.json` for:
- Qwen 2.5 / 3 / 3.5
- Llama 3 / 3.1 / 3.2
- Mistral / Mixtral
- Gemma 2 / 3
- DeepSeek R1 / V3
- Yi, Command-R, Phi-3
- Custom models

## Testing Your Config

```bash
# Start server with your model
llama-server --model your-model.gguf

# Test in chat
python run.py
/turn_off_thinking  # Should work without errors
```
