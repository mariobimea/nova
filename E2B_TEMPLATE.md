# E2B Template Configuration - NOVA Workflow Engine

## Overview

NOVA uses a custom E2B sandbox template optimized for workflow execution with pre-installed packages.

**Template Name**: `nova-workflow-engine-v1`
**Template ID**: `hylet6zk79e4aq58ytic`
**Status**: ✅ Production Ready

---

## Pre-installed Packages

The template includes commonly used Python packages to reduce cold start time from ~6s to ~1.5s:

| Package | Version | Purpose |
|---------|---------|---------|
| PyMuPDF | 1.24.0 | PDF processing (OCR, extraction) |
| requests | 2.31.0 | HTTP requests (API calls, webhooks) |
| pandas | 2.1.4 | Data manipulation and analysis |
| pillow | 10.1.0 | Image processing |
| psycopg2-binary | 2.9.10 | PostgreSQL database connections |
| python-dotenv | 1.0.0 | Environment variable management |

---

## File Structure

```
/nova/
├── e2b.Dockerfile     # Template definition
├── e2b.toml          # Auto-generated config
└── .env              # E2B_TEMPLATE_ID configuration
```

---

## Configuration

### Environment Variables

Add to `.env`:

```bash
E2B_API_KEY=e2b_a58171ddb2be1e03333222f77fa4bd1273e6f699
E2B_TEMPLATE_ID=hylet6zk79e4aq58ytic
```

### Executor Usage

The E2BExecutor automatically uses the template from `.env`:

```python
from core.executors import get_executor

# Automatically uses E2B_TEMPLATE_ID from environment
executor = get_executor()  # Returns E2BExecutor with custom template

# Execute code
result = await executor.execute(
    code="print('Hello from NOVA!')",
    context={},
    timeout=60
)
```

---

## Rebuilding the Template

If you need to modify the template (add/remove packages, change versions):

### 1. Edit `e2b.Dockerfile`

```dockerfile
FROM e2bdev/code-interpreter:latest

# Add new packages
RUN pip install --no-cache-dir \
    your-new-package==1.0.0
```

### 2. Rebuild

```bash
e2b template build --name "nova-workflow-engine-v1" -c "/root/.jupyter/start-up.sh"
```

**Important**: Always include the `-c "/root/.jupyter/start-up.sh"` flag for code interpreter compatibility.

### 3. Template ID remains the same

The template ID (`hylet6zk79e4aq58ytic`) remains constant across builds. No need to update `.env`.

---

## Testing

Run the test script to verify the template:

```bash
python3 test_template_simple.py
```

Expected output:

```
✅ E2B_API_KEY: e2b_a58171...
✅ E2B_TEMPLATE_ID: hylet6zk79e4aq58ytic

🚀 Creating E2BExecutor...

🔍 Testing pre-installed packages...

📦 Package availability:
  PyMuPDF: ✅
  requests: ✅
  pandas: ✅
  pillow: ✅
  psycopg2: ✅
  python-dotenv: ✅

✅ All packages installed correctly!
✅ Status: success

============================================================
✅ Template test PASSED - Ready for production!
============================================================
```

---

## Costs

**E2B Pricing** (as of 2025):
- **Hobby tier**: $100 free credits (~7 months of development)
- **Usage**: ~$0.03/second (2 vCPU + 512MB RAM)
- **Estimated production**: $7-10/month

---

## Troubleshooting

### Template timeout errors

**Symptom**: `The sandbox is running but port is not open`

**Solution**: Ensure you rebuilt with the start command:

```bash
e2b template build --name "nova-workflow-engine-v1" -c "/root/.jupyter/start-up.sh"
```

### Packages missing

**Symptom**: `ImportError: No module named 'xyz'`

**Solution**: Add the package to `e2b.Dockerfile` and rebuild.

### Template list shows wrong name

**Symptom**: Template appears with generic name instead of `nova-workflow-engine-v1`

**Solution**: Use `--name` flag during build:

```bash
e2b template build --name "nova-workflow-engine-v1" -c "/root/.jupyter/start-up.sh"
```

---

## Best Practices

1. **Always test after rebuild**: Run `test_template_simple.py` after any changes
2. **Pin package versions**: Ensures reproducibility
3. **Minimize cold start**: Only add packages you actually need
4. **Use start command**: Required for e2b-code-interpreter compatibility
5. **Single template**: Keep one unified template for all workflows

---

## Migration Notes

### From Multiple Templates

Previously, NOVA had 3 separate template directories:
- `nova-invoice/` (Public, ID: j0hjup33shzpbnumir2w)
- `nova-sandbox/` (Private, ID: izvjugmy05jeo0vwg755)
- `nova-sandbox-v2/` (duplicate ID)

**Now**: Single unified template `nova-workflow-engine-v1` in project root.

**Backups**: Old configurations saved in `.backup/e2b-templates-*/`

---

## Additional Resources

- [E2B Documentation](https://e2b.dev/docs)
- [E2B Code Interpreter](https://github.com/e2b-dev/code-interpreter)
- [Template Migration Guide](https://e2b.dev/docs/template/migration-v2)

---

Last updated: 2025-11-04
