#!/usr/bin/env python3
"""
Build script for NOVA E2B custom template using Build System 2.0.

This creates a custom sandbox with pre-installed packages:
- PyMuPDF (PDF processing)
- requests (HTTP/APIs)
- pandas (Data analysis)
- pillow (Image processing)
- psycopg2-binary (PostgreSQL)
- python-dotenv (Environment config)

Usage:
    python3 template_build.py
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    from e2b import Template, default_build_logger
except ImportError:
    print("❌ E2B SDK not installed")
    print("Install with: pip install e2b")
    exit(1)

def build_nova_template():
    """Build NOVA workflow engine template with pre-installed packages."""

    print("🚀 Building NOVA template with Build System 2.0...\n")

    # Define the template programmatically
    template = (
        Template()
        # Base image (Python 3.12)
        .from_image("python:3.12")

        # Set user and workdir
        .set_user("root")
        .set_workdir("/")

        # Environment variables for pip
        .set_envs({
            "PIP_DEFAULT_TIMEOUT": "100",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_CACHE_DIR": "1",
        })

        # Install system dependencies
        .apt_install([
            "build-essential",
            "gcc",
            "g++",
            "make",
            "curl",
            "git",
        ])

        # Install Python packages (exact versions)
        .pip_install([
            "PyMuPDF==1.24.0",       # PDF processing
            "requests==2.31.0",       # HTTP/APIs
            "pandas==2.1.4",          # Data analysis
            "pillow==10.1.0",         # Image processing
            "psycopg2-binary==2.9.10", # PostgreSQL
            "python-dotenv==1.0.0",   # Environment config
        ])

        # Set final user and workdir
        .set_user("user")
        .set_workdir("/home/user")
    )

    print("📦 Template definition created")
    print("\nPackages to install:")
    print("  - PyMuPDF 1.24.0 (PDF processing)")
    print("  - requests 2.31.0 (HTTP/APIs)")
    print("  - pandas 2.1.4 (Data analysis)")
    print("  - pillow 10.1.0 (Image processing)")
    print("  - psycopg2-binary 2.9.10 (PostgreSQL)")
    print("  - python-dotenv 1.0.0 (Environment config)")
    print("\n🔨 Building template...\n")

    # Build the template
    Template.build(
        template,
        alias="nova-engine",  # Template name
        cpu_count=2,          # 2 vCPUs
        memory_mb=2048,       # 2GB RAM
        on_build_logs=default_build_logger(),  # Show build logs
    )

    print("\n✅ Template built successfully!")
    print("\nTemplate details:")
    print("  Name: nova-engine")
    print("  CPUs: 2")
    print("  RAM: 2048 MB")
    print("\nYou can now use this template in your code:")
    print('  from e2b_code_interpreter import Sandbox')
    print('  sandbox = Sandbox.create(template="nova-engine")')

if __name__ == "__main__":
    # Check API key
    api_key = os.getenv("E2B_API_KEY")
    if not api_key:
        print("❌ E2B_API_KEY not found in environment")
        print("\nPlease set your E2B API key:")
        print("  export E2B_API_KEY=e2b_your_key_here")
        print("\nOr add to .env file:")
        print("  E2B_API_KEY=e2b_your_key_here")
        exit(1)

    build_nova_template()
