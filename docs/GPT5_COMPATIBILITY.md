# GPT-5 API Compatibility Guide

## Overview

GPT-5 models have different parameter requirements compared to GPT-4 models. This document outlines the key differences and how NOVA handles them.

## Key Differences

### 1. Token Limit Parameter

**GPT-4 models:**
```python
{
    "max_tokens": 2000
}
```

**GPT-5 models:**
```python
{
    "max_completion_tokens": 2000  # Different parameter name!
}
```

### 2. Temperature Parameter

**GPT-4 models:**
```python
{
    "temperature": 0.2  # Any value 0.0-2.0 supported
}
```

**GPT-5 models:**
```python
{
    # DON'T set temperature at all!
    # GPT-5 only supports temperature=1 (default)
    # Setting any other value causes: 400 error
}
```

**Error if you set custom temperature:**
```
Error code: 400 - {'error': {
    'message': "Unsupported value: 'temperature' does not support 0.2 with this model.
                Only the default (1) value is supported.",
    'type': 'invalid_request_error'
}}
```

### 3. New GPT-5 Parameters (Optional)

GPT-5 introduces new parameters for reasoning control:

```python
{
    "reasoning": {
        "effort": "minimal" | "medium" | "high"
        # Controls reasoning token usage and latency
        # Default: "medium"
    },
    "text": {
        "verbosity": "low" | "medium" | "high"
        # Controls output length and detail
        # Default: "medium"
    }
}
```

**Note:** These are optional and not currently used in NOVA Phase 1.

## How NOVA Handles This

The `OpenAIProvider` class automatically detects GPT-5 models and adjusts parameters:

```python
# In generate_code_with_tools() and generate_text()
if self.model_name.startswith("gpt-5"):
    # GPT-5 specific parameters
    api_params["max_completion_tokens"] = 2000
    # Don't set temperature - use default (1.0)
else:
    # GPT-4 and other models
    api_params["max_tokens"] = 2000
    api_params["temperature"] = 0.2  # Deterministic code generation
```

## Supported Models

### GPT-5 Models (require special handling):
- `gpt-5`
- `gpt-5-mini`
- `gpt-5-codex` (Responses API only, not Chat Completions)

### GPT-4 Models (standard parameters):
- `gpt-4o-mini`
- `gpt-4o`
- `gpt-4-turbo`

## Best Practices

1. **Always use model detection:**
   ```python
   if model_name.startswith("gpt-5"):
       # GPT-5 specific code
   ```

2. **Don't hardcode temperature for GPT-5:**
   ```python
   # ❌ BAD
   temperature = 0.2  # Will fail for GPT-5

   # ✅ GOOD
   if not model_name.startswith("gpt-5"):
       api_params["temperature"] = 0.2
   ```

3. **Use correct token parameter:**
   ```python
   # ❌ BAD
   api_params["max_tokens"] = 2000  # Won't work for GPT-5

   # ✅ GOOD
   if model_name.startswith("gpt-5"):
       api_params["max_completion_tokens"] = 2000
   else:
       api_params["max_tokens"] = 2000
   ```

## Testing Checklist

When adding GPT-5 support to a new feature:

- [ ] Test with `gpt-5` model
- [ ] Test with `gpt-5-mini` model
- [ ] Verify no `temperature` parameter is sent
- [ ] Verify `max_completion_tokens` is used (not `max_tokens`)
- [ ] Test with GPT-4 model to ensure backward compatibility
- [ ] Check error logs for any 400 errors related to parameters

## References

- OpenAI GPT-5 Cookbook: https://cookbook.openai.com/examples/gpt-5/gpt-5_new_params_and_tools
- OpenAI Developer Forum: https://community.openai.com/t/temperature-in-gpt-5-models/1337133
- NOVA Model Registry: [/src/core/model_registry.py](../src/core/model_registry.py)
- NOVA OpenAI Provider: [/src/core/providers/openai_provider.py](../src/core/providers/openai_provider.py)

## Changelog

### 2025-01-13
- Initial documentation
- Fixed temperature parameter compatibility
- Added detection logic to OpenAIProvider