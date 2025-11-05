# E2B Template Update Log

## November 5, 2025 - Template Migration

### Summary

Migrated from `nova-workflow-engine-v3` to `nova-workflow-fresh` due to E2B caching issues affecting package availability in Railway production.

### Problem

**Symptom**: Pre-installed packages (PyMuPDF, psycopg2, python-dotenv) were missing in Railway execution despite working locally.

**Root Causes**:
1. E2B template caching - Previous template ID `hylet6zk79e4aq58ytic` had cached version without packages
2. Railway Worker missing environment variable - `E2B_TEMPLATE_ID` was only set in Web App service, not Worker service

### Solution

1. **Created new template with fresh ID**:
   - Old: `hylet6zk79e4aq58ytic` (nova-workflow-engine-v3)
   - New: `wzqi57u2e8v2f90t6lh5` (nova-workflow-fresh)

2. **Added environment variable to Worker**:
   - Railway → Worker service → Variables → `E2B_TEMPLATE_ID=wzqi57u2e8v2f90t6lh5`

### Verification

```bash
# Test in Railway (workflow ID 2 is the package verification test)
curl -X POST 'https://web-production-a1c4f.up.railway.app/workflows/2/execute' \
  -H 'Content-Type: application/json' -d '{}'

# Check results after 10 seconds
curl 'https://web-production-a1c4f.up.railway.app/tasks/{task-id}'
```

**Result**: ✅ All 6 packages now available in production

```
PyMuPDF: OK
requests: OK
pandas: OK
pillow: OK
psycopg2: OK
python_dotenv: OK
```

### Files Updated

1. **E2B_TEMPLATE.md**: Complete rewrite with new template ID and troubleshooting guide
2. **README.md**: Added `E2B_TEMPLATE_ID` to environment variables section
3. **src/core/executors.py**: Updated template ID in comments
4. **.env**: Updated local environment to use new template
5. **e2b.toml**: Auto-generated with new template ID

### Key Learnings

1. **E2B caching is aggressive**: Template IDs are cached. To force a fresh build, create a new template with a different ID.

2. **Railway requires variables in ALL services**: Workers execute code, not the API. Both services need `E2B_TEMPLATE_ID`.

3. **Template verification**:
   - Local test: `python3 test_template_simple.py`
   - Production test: Execute workflow 2 via API

4. **Template naming convention**: Use descriptive names that indicate freshness/version to avoid confusion.

### Deprecated Templates

The following templates are **deprecated** and should not be used:

- `j0hjup33shzpbnumir2w` - Original nova-invoice template
- `izvjugmy05jeo0vwg755` - Private test template
- `hylet6zk79e4aq58ytic` - nova-workflow-engine-v1/v2/v3 (caching issues)

### Current Production Configuration

**Template Name**: `nova-workflow-fresh`
**Template ID**: `wzqi57u2e8v2f90t6lh5`
**Status**: ✅ Production Ready
**Verified**: November 5, 2025

**Railway Environment Variables** (BOTH services):
```
E2B_API_KEY=e2b_a58171ddb2be1e03333222f77fa4bd1273e6f699
E2B_TEMPLATE_ID=wzqi57u2e8v2f90t6lh5
```

### Future Considerations

1. **Monitoring**: Add alerting for package import errors
2. **Testing**: Add automated tests that verify package availability in production
3. **Documentation**: Keep E2B_TEMPLATE.md updated with any template changes
4. **Version pinning**: Continue pinning package versions in e2b.Dockerfile

---

**Author**: Mario Ferrer (with Claude Code assistance)
**Date**: November 5, 2025
