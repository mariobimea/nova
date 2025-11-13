# Model Selection in NOVA

NOVA supports flexible model selection for AI-powered code generation. You can specify different models at the workflow level or override them per node.

## Supported Models

### OpenAI Models

| Model | API Name | Price (Input/Output per 1M tokens) | Best For |
|-------|----------|-----------------------------------|----------|
| **GPT-4o Mini** | `gpt-4o-mini` or `mini` | $0.15 / $0.60 | Simple tasks, validations, cheap workflows |
| **GPT-5 Mini** | `gpt-5-mini` | $0.25 / $2.00 | Medium complexity, business logic |
| **GPT-5 Codex** | `gpt-5-codex` or `codex` | $1.25 / $10.00 | Complex algorithms, integrations |
| **GPT-5** | `gpt-5` | $1.25 / $10.00 | Maximum reasoning, complex tasks |

## Configuration

### Default Model

Set the default model in your `.env` file:

```bash
DEFAULT_MODEL=gpt-4o-mini
```

This model will be used if no model is specified in the workflow or node.

### Workflow-Level Model

Specify a default model for the entire workflow:

```json
{
  "name": "Invoice Processing",
  "model": "gpt-5-mini",
  "nodes": [
    {
      "id": "extract",
      "type": "action",
      "executor": "cached",
      "prompt": "Extract invoice data"
    }
  ]
}
```

All nodes will use `gpt-5-mini` unless overridden.

### Node-Level Model

Override the model for a specific node:

```json
{
  "name": "Invoice Processing",
  "model": "gpt-4o-mini",
  "nodes": [
    {
      "id": "extract",
      "type": "action",
      "executor": "cached",
      "prompt": "Extract invoice data"
      // Uses workflow model: gpt-4o-mini
    },
    {
      "id": "complex_calc",
      "type": "action",
      "executor": "cached",
      "model": "gpt-5-codex",
      "prompt": "Calculate complex taxes with international rules"
      // Overrides with: gpt-5-codex
    }
  ]
}
```

## Model Resolution Priority

NOVA resolves models in this order (highest to lowest priority):

1. **Node-level model** (`node.model`)
2. **Workflow-level model** (`workflow.model`)
3. **Environment default** (`DEFAULT_MODEL` in `.env`)

Example:

```
Node: {"model": "gpt-5-codex"}
Workflow: {"model": "gpt-5-mini"}
Default: gpt-4o-mini

→ Uses: gpt-5-codex (node overrides all)
```

## Cost Optimization Strategies

### Strategy 1: Budget-Conscious (All `gpt-4o-mini`)

```json
{
  "model": "gpt-4o-mini",
  "nodes": [...]
}
```

**Cost**: ~$0.0093 per workflow (15 nodes)
**Best for**: Development, testing, simple workflows

### Strategy 2: Balanced (Workflow default + overrides)

```json
{
  "model": "gpt-4o-mini",
  "nodes": [
    {"id": "simple_task", "prompt": "..."},
    {"id": "complex_task", "model": "gpt-5-codex", "prompt": "..."}
  ]
}
```

**Cost**: ~$0.03-0.05 per workflow
**Best for**: Production with selective premium models

### Strategy 3: Premium (All `gpt-5-codex`)

```json
{
  "model": "gpt-5-codex",
  "nodes": [...]
}
```

**Cost**: ~$0.12 per workflow (15 nodes)
**Best for**: Critical workflows, maximum code quality

## Monitoring Costs

Check `chain_of_work` table for AI metadata:

```sql
SELECT
    node_id,
    ai_metadata->>'model' as model_used,
    (ai_metadata->>'cost_usd_estimated')::float as cost,
    ai_metadata->>'tokens_input_estimated' as input_tokens,
    ai_metadata->>'tokens_output_estimated' as output_tokens
FROM chain_of_work
WHERE ai_metadata IS NOT NULL
ORDER BY created_at DESC
LIMIT 10;
```

## Example Workflows

### Simple Invoice Processing

```json
{
  "name": "Simple Invoice Processing",
  "model": "gpt-4o-mini",
  "nodes": [
    {"id": "start", "type": "start"},
    {
      "id": "extract",
      "type": "action",
      "executor": "cached",
      "prompt": "Extract invoice data from PDF"
    },
    {
      "id": "validate",
      "type": "action",
      "executor": "cached",
      "prompt": "Validate invoice format"
    },
    {"id": "end", "type": "end"}
  ],
  "edges": [
    {"from": "start", "to": "extract"},
    {"from": "extract", "to": "validate"},
    {"from": "validate", "to": "end"}
  ]
}
```

**Estimated cost**: ~$0.02 per execution

### Complex Multi-Model Workflow

```json
{
  "name": "Advanced Invoice Processing",
  "model": "gpt-4o-mini",
  "nodes": [
    {"id": "start", "type": "start"},
    {
      "id": "extract",
      "type": "action",
      "executor": "cached",
      "prompt": "Extract invoice data"
    },
    {
      "id": "validate",
      "type": "action",
      "executor": "cached",
      "model": "gpt-5-mini",
      "prompt": "Validate with business rules"
    },
    {
      "id": "complex_tax",
      "type": "action",
      "executor": "cached",
      "model": "gpt-5-codex",
      "prompt": "Calculate international taxes with VAT, customs, etc."
    },
    {"id": "end", "type": "end"}
  ],
  "edges": [
    {"from": "start", "to": "extract"},
    {"from": "extract", "to": "validate"},
    {"from": "validate", "to": "complex_tax"},
    {"from": "complex_tax", "to": "end"}
  ]
}
```

**Estimated cost**: ~$0.04 per execution

## Adding New Models

### OpenAI Models

Update `ModelRegistry` in `src/core/model_registry.py`:

```python
_REGISTRY: Dict[str, tuple[Type[ModelProvider], str]] = {
    "gpt-new-model": (OpenAIProvider, "gpt-new-model"),
    "new-alias": (OpenAIProvider, "gpt-new-model"),
}
```

Update pricing in `OpenAIProvider` (`src/core/providers/openai_provider.py`):

```python
MODELS = {
    "gpt-new-model": {
        "api_name": "gpt-new-model",
        "input_price": 0.50,
        "output_price": 2.50,
        "max_tokens": 16384,
        "context_window": 128000
    }
}
```

### Future: Anthropic/Claude Models

Coming in Phase 2:

```json
{
  "model": "claude-sonnet-4-5",
  "nodes": [
    {"id": "task", "model": "claude-haiku-4-5", "prompt": "..."}
  ]
}
```

## Troubleshooting

### "Unknown model" error

```
ValueError: Unknown model: 'invalid-model'. Available models: gpt-4o-mini, ...
```

**Solution**: Use a supported model from the list above.

### Model not using specified pricing

The `CachedExecutor` estimates costs using provider pricing. Check `ai_metadata.cost_usd_estimated` in the response.

### No model specified, using default

If you see this log, NOVA is using the `DEFAULT_MODEL` from `.env`. This is expected behavior when no model is specified in workflow or node.

## Best Practices

1. **Use cheap models for simple tasks** (`gpt-4o-mini`)
2. **Use premium models selectively** (only for complex nodes)
3. **Set workflow default to cheapest** and override specific nodes
4. **Monitor costs** via `chain_of_work` table
5. **Test with `gpt-4o-mini` first**, upgrade if quality is insufficient
6. **Use aliases** for brevity (`mini` instead of `gpt-4o-mini`)

## Related Documentation

- [ARQUITECTURA.md](../documentacion/ARQUITECTURA.md) - NOVA architecture overview
- [COMPARATIVA-MODELOS-OPENAI.md](../documentacion/COMPARATIVA-MODELOS-OPENAI.md) - Detailed model comparison
- [CALCULO-COSTO-WORKFLOW.md](../documentacion/CALCULO-COSTO-WORKFLOW.md) - Cost calculations
