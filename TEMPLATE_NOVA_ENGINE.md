# NOVA E2B Template - `nova-engine`

**Status**: ✅ **PRODUCTION READY**
**Created**: 2025-11-09
**Template ID**: `wzqi57u2e8v2f90t6lh5`
**Template Alias**: `nova-engine`
**Build System**: E2B Build System 2.0 (Programmatic)

---

## Overview

Custom E2B sandbox template optimized for NOVA workflow engine with pre-installed Python packages for common automation tasks.

**Cold Start Time**: ~2 seconds (vs ~6s without template)
**Size**: 12.4 GB
**CPUs**: 2
**RAM**: 2048 MB

---

## Pre-installed Packages

| Package | Version | Purpose |
|---------|---------|---------|
| **PyMuPDF** | 1.24.0 | PDF processing (extraction, OCR) |
| **requests** | 2.31.0 | HTTP requests (APIs, webhooks) |
| **pandas** | 2.1.4 | Data manipulation and analysis |
| **pillow** | 10.1.0 | Image processing |
| **psycopg2-binary** | 2.9.10 | PostgreSQL database connections |
| **python-dotenv** | 1.0.0 | Environment variable management |

**Plus all dependencies**: numpy, certifi, urllib3, charset-normalizer, idna, python-dateutil, pytz, tzdata, six

---

## Build System

This template uses **E2B Build System 2.0** (programmatic approach) instead of Dockerfiles.

### Build Script

Location: [`template_build.py`](template_build.py)

```python
from e2b import Template

template = (
    Template()
    .from_image("python:3.12")
    .set_user("root")
    .set_workdir("/")
    .apt_install(["build-essential", "gcc", "g++", "make", "curl", "git"])
    .pip_install([
        "PyMuPDF==1.24.0",
        "requests==2.31.0",
        "pandas==2.1.4",
        "pillow==10.1.0",
        "psycopg2-binary==2.9.10",
        "python-dotenv==1.0.0",
    ])
    .set_user("user")
    .set_workdir("/home/user")
)

Template.build(
    template,
    alias="nova-engine",
    cpu_count=2,
    memory_mb=2048,
)
```

### Rebuild Template

If you need to modify packages:

```bash
cd /Users/marioferrer/automatizaciones/nova

# Edit template_build.py to add/remove packages
# Then rebuild:
python3 template_build.py
```

**Important**: Template ID remains the same (`wzqi57u2e8v2f90t6lh5`), E2B updates it in-place.

---

## Configuration

### Environment Variables

Add to `.env`:

```bash
E2B_API_KEY=e2b_a58171ddb2be1e03333222f77fa4bd1273e6f699
E2B_TEMPLATE_ID=nova-engine
```

**Important for Railway**: Set `E2B_TEMPLATE_ID` in **BOTH** services:
- ✅ Web (API)
- ✅ **Worker (Celery)** ← CRITICAL (Worker executes the code)

### Usage in Code

```python
from e2b import Sandbox

# Using template alias
sandbox = Sandbox.create(template="nova-engine")

# Using template ID
sandbox = Sandbox.create(template="wzqi57u2e8v2f90t6lh5")

# Execute Python code
result = sandbox.commands.run("python3 -c 'import pandas; print(pandas.__version__)'")
print(result.stdout)  # "2.1.4"

sandbox.kill()
```

---

## Testing

### Test Script

Location: [`test_nova_template.py`](test_nova_template.py)

```bash
python3 test_nova_template.py
```

**Expected Output**:

```
============================================================
NOVA E2B Template Test
============================================================

✅ E2B_API_KEY: e2b_a58171...
✅ E2B_TEMPLATE_ID: nova-engine

🚀 Creating sandbox from template...

✅ Sandbox created successfully

🔍 Testing pre-installed packages...

📦 Package availability:
PyMuPDF: ✅ 1.24.0
requests: ✅ 2.31.0
pandas: ✅ 2.1.4
pillow: ✅ 10.1.0
psycopg2: ✅ 2.9.10 (dt dec pq3 ext lo64)
python-dotenv: ✅ installed

✅ All packages installed correctly!

============================================================
✅ Template test PASSED - Ready for production!
============================================================
```

---

## Why Build System 2.0?

**Advantages over Dockerfile approach**:
- ✅ Type hints and autocompletion
- ✅ Programmatic builds (can be dynamic)
- ✅ No need to manage `e2b.toml` or start commands
- ✅ Easier CI/CD integration
- ✅ Better error messages
- ✅ Official E2B recommended approach

**Previous Issues with Dockerfile**:
- ❌ Required manual start command configuration
- ❌ Template kept failing with "port not open" errors
- ❌ Had to match code-interpreter's Jupyter setup

**With Build System 2.0**:
- ✅ Works immediately out of the box
- ✅ No Jupyter/server complexity
- ✅ Clean Python-only environment

---

## File Structure

```
/nova/
├── template_build.py          # Build script (Build System 2.0)
├── test_nova_template.py      # Test script
├── e2b.Dockerfile             # OLD (kept for reference, not used)
├── e2b.toml                   # Auto-generated config
├── .env                       # Contains E2B_TEMPLATE_ID=nova-engine
└── TEMPLATE_NOVA_ENGINE.md    # This file
```

---

## Costs

**E2B Pricing** (as of November 2025):
- **Hobby tier**: $100 free credits (~7 months development)
- **Usage**: ~$0.03/second (2 vCPU + 2GB RAM)
- **Estimated production**: $10-15/month (depending on workflow frequency)

**Cost Optimization**:
- Pre-installed packages reduce cold start (save ~4s per execution)
- Use `timeout` parameter to kill long-running sandboxes
- Cache results when possible (reduces executions)

---

## Troubleshooting

### "Template not found"

**Symptom**: `Template 'nova-engine' not found`

**Solution**: Use template ID instead of alias:

```python
sandbox = Sandbox.create(template="wzqi57u2e8v2f90t6lh5")
```

### "Port 49999 not open"

**Symptom**: `The sandbox is running but port is not open`

**Cause**: Trying to use `e2b-code-interpreter` SDK with this template

**Solution**: Use standard `e2b` SDK:

```python
# ❌ Don't use
from e2b_code_interpreter import Sandbox

# ✅ Use this
from e2b import Sandbox
```

This template doesn't include Jupyter server, so use `sandbox.commands.run()` instead of `sandbox.run_code()`.

### Template rebuild fails

**Symptom**: Build fails or times out

**Solution**:

1. Check package versions are available on PyPI
2. Ensure `E2B_API_KEY` is set
3. Try building with fewer packages first
4. Check E2B dashboard for build logs

### Package not found in Railway

**Symptom**: Works locally but fails in Railway with `ImportError`

**Root Cause**: Worker service missing `E2B_TEMPLATE_ID`

**Solution**:

1. Railway → Worker service → Variables
2. Add `E2B_TEMPLATE_ID=nova-engine`
3. Redeploy Worker
4. **Why**: Worker executes code, not the API

---

## Migration from Previous Templates

### From `nova-workflow-fresh` (Legacy)

The old template used Dockerfile with manual CLI build. New template uses Build System 2.0.

**What changed**:
- ✅ Same packages, same versions
- ✅ Same template ID (`wzqi57u2e8v2f90t6lh5`)
- ✅ Alias changed: `nova-workflow-fresh` → `nova-engine`
- ✅ Build method: Dockerfile → Programmatic

**Migration**:

```bash
# Update .env
E2B_TEMPLATE_ID=nova-engine  # Changed from wzqi57u2e8v2f90t6lh5

# Update Railway env vars (both Web + Worker)
E2B_TEMPLATE_ID=nova-engine
```

No code changes needed.

---

## Best Practices

1. **Always test after rebuild**: Run `test_nova_template.py`
2. **Pin package versions**: Ensures reproducibility
3. **Minimize packages**: Only add what you actually need
4. **Use alias in production**: Easier to update template later
5. **Set timeout**: Prevent runaway sandboxes

```python
# Good
sandbox = Sandbox.create(
    template="nova-engine",
    timeout=60  # Kill after 60s
)

# Execute with timeout
result = sandbox.commands.run("python3 script.py", timeout=30)
```

---

## Related Documentation

- [E2B Build System 2.0](https://e2b.dev/blog/introducing-build-system-2-0)
- [E2B Custom Templates Guide](../documentacion/E2B-CUSTOM-TEMPLATES.md)
- [NOVA Executor](src/core/executors.py)

---

## Changelog

**2025-11-09**: Initial template built with Build System 2.0
- Template ID: `wzqi57u2e8v2f90t6lh5`
- Alias: `nova-engine`
- Status: ✅ Production ready
- All 6 packages tested and working

---

*Last updated: 2025-11-09*
