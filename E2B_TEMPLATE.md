# E2B Template Configuration - NOVA Workflow Engine

## Overview

NOVA uses a custom E2B sandbox template optimized for workflow execution with pre-installed packages.

**Template Name**: `nova-workflow-fresh`
**Template ID**: `wzqi57u2e8v2f90t6lh5`
**Status**: ✅ Production Ready (November 2025)

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
E2B_TEMPLATE_ID=wzqi57u2e8v2f90t6lh5
```

**Important for Railway**: Ensure BOTH services have this variable:
- ✅ Web App (API)
- ✅ Worker (Celery) - **CRITICAL**: Worker executes the code, must have template ID

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
e2b template build --name "nova-workflow-fresh" -c "/root/.jupyter/start-up.sh"
```

**Important**: Always include the `-c "/root/.jupyter/start-up.sh"` flag for code interpreter compatibility.

### 3. Template ID remains the same

The template ID (`wzqi57u2e8v2f90t6lh5`) remains constant across builds. E2B will update the template in-place without changing the ID.

---

## Testing

Run the test script to verify the template:

```bash
python3 test_template_simple.py
```

Expected output:

```
✅ E2B_API_KEY: e2b_a58171...
✅ E2B_TEMPLATE_ID: wzqi57u2e8v2f90t6lh5

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

### Test in Railway (Production)

To test the template in production, execute the test workflow:

```bash
curl -X POST 'https://your-railway-url.railway.app/workflows/2/execute' -H 'Content-Type: application/json' -d '{}'
```

Check results after 10 seconds:

```bash
curl 'https://your-railway-url.railway.app/tasks/{task-id}'
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
e2b template build --name "nova-workflow-fresh" -c "/root/.jupyter/start-up.sh"
```

### Packages missing in Railway but work locally

**Symptom**: Local tests pass but Railway shows `ImportError: No module named 'xyz'`

**Root Cause**: Worker service missing `E2B_TEMPLATE_ID` environment variable.

**Solution**:
1. Go to Railway → Worker service → Variables
2. Add `E2B_TEMPLATE_ID=wzqi57u2e8v2f90t6lh5`
3. Redeploy Worker
4. **Why**: The Worker (Celery) executes workflows, not the API. Both services need the template ID.

### Packages missing (template issue)

**Symptom**: `ImportError: No module named 'xyz'` everywhere (local + Railway)

**Solution**: Add the package to `e2b.Dockerfile` and rebuild.

### Template list shows wrong name

**Symptom**: Template appears with generic name instead of `nova-workflow-fresh`

**Solution**: Use `--name` flag during build:

```bash
e2b template build --name "nova-workflow-fresh" -c "/root/.jupyter/start-up.sh"
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

### Template History

**November 2025**: `nova-workflow-fresh` (wzqi57u2e8v2f90t6lh5) - Current production template
**October 2025**: `nova-workflow-engine-v1/v2/v3` (hylet6zk79e4aq58ytic) - Deprecated (caching issues)
**Earlier**: Multiple separate templates (j0hjup33shzpbnumir2w, izvjugmy05jeo0vwg755)

**Current**: Single unified template `nova-workflow-fresh` in project root.

**Why new template**: Previous template ID had E2B caching issues. Creating a completely new template with fresh ID resolved package availability problems.

---

## Additional Resources

- [E2B Documentation](https://e2b.dev/docs)
- [E2B Code Interpreter](https://github.com/e2b-dev/code-interpreter)
- [Template Migration Guide](https://e2b.dev/docs/template/migration-v2)

---

Last updated: 2025-11-05
