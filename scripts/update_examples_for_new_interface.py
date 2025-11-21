#!/usr/bin/env python3
"""
Script to update all example files to use new executor interface.

Old: result = await executor.execute(...)
New: result, metadata = await executor.execute(...)

Also updates assertions:
Old: result['_ai_metadata']
New: metadata['ai_metadata']
"""

import os
import re
from pathlib import Path

def update_file(filepath):
    """Update a single file to use new executor interface"""
    print(f"\n📝 Processing: {filepath}")

    with open(filepath, 'r') as f:
        content = f.read()

    original_content = content
    changes_made = 0

    # Pattern 1: Update execute() calls
    # From: result = await executor.execute(
    # To:   result, metadata = await executor.execute(
    pattern1 = r'(\s+)result = await executor\.execute\('
    replacement1 = r'\1result, metadata = await executor.execute('
    content, count1 = re.subn(pattern1, replacement1, content)
    changes_made += count1
    if count1 > 0:
        print(f"  ✅ Updated {count1} execute() calls")

    # Pattern 2: Update E2B executor mock returns
    # From: executor.e2b_executor.execute = AsyncMock(return_value={"result": ...})
    # To:   executor.e2b_executor.execute = AsyncMock(return_value=({"result": ...}, {}))
    # (This pattern is less common in examples, more in tests)

    # Pattern 3: Update _ai_metadata access
    # From: result['_ai_metadata']
    # To:   metadata.get('ai_metadata', {})  # Safer with .get()
    pattern3 = r"result\['_ai_metadata'\]"
    replacement3 = r"metadata.get('ai_metadata', {})"
    content, count3 = re.subn(pattern3, replacement3, content)
    changes_made += count3
    if count3 > 0:
        print(f"  ✅ Updated {count3} _ai_metadata accesses")

    # Pattern 4: Update _ai_metadata checks
    # From: if '_ai_metadata' in result:
    # To:   if metadata and 'ai_metadata' in metadata:
    pattern4 = r"if '_ai_metadata' in result:"
    replacement4 = r"if metadata and 'ai_metadata' in metadata:"
    content, count4 = re.subn(pattern4, replacement4, content)
    changes_made += count4
    if count4 > 0:
        print(f"  ✅ Updated {count4} _ai_metadata checks")

    # Pattern 5: Update metadata variable assignment
    # From: metadata = result['_ai_metadata']
    # To:   ai_meta = metadata.get('ai_metadata', {})
    # Note: We rename to ai_meta to avoid conflict with exec metadata
    pattern5 = r"(\s+)metadata = result\['_ai_metadata'\]"
    replacement5 = r"\1ai_meta = metadata.get('ai_metadata', {})"
    content, count5 = re.subn(pattern5, replacement5, content)
    changes_made += count5
    if count5 > 0:
        print(f"  ✅ Updated {count5} metadata assignments")
        # Also update references from metadata. to ai_meta.
        content = re.sub(r'\bmetadata\.get\(', r'ai_meta.get(', content)
        content = re.sub(r"\bmetadata\['", r"ai_meta['", content)

    if changes_made > 0:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"  💾 Saved {changes_made} total changes")
        return True
    else:
        print(f"  ⏭️  No changes needed")
        return False

def main():
    """Update all example and script files"""
    repo_root = Path(__file__).parent.parent

    # Directories to process
    directories = [
        repo_root / "examples",
        repo_root / "scripts",
    ]

    files_updated = 0
    files_total = 0

    for directory in directories:
        if not directory.exists():
            continue

        print(f"\n{'='*80}")
        print(f"Processing directory: {directory}")
        print(f"{'='*80}")

        for filepath in directory.glob("*.py"):
            # Skip this script itself
            if filepath.name == "update_examples_for_new_interface.py":
                continue

            files_total += 1
            if update_file(filepath):
                files_updated += 1

    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}")
    print(f"Files processed: {files_total}")
    print(f"Files updated: {files_updated}")
    print(f"Files unchanged: {files_total - files_updated}")
    print(f"\n✅ Done!")

if __name__ == "__main__":
    main()
