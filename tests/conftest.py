"""Tests for zhihu-fetch-skill scripts.

Put ``scripts/`` on sys.path so tests import the same modules as CLI.
Stub Playwright when it is not installed so import-time sys.exit is skipped.
Live tests use the default workspace under the skill root: ``zhihu-fetch-workspace/``.
"""

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

try:
    import playwright  # noqa: F401
except ImportError:
    playwright = types.ModuleType("playwright")
    async_api = types.ModuleType("playwright.async_api")
    async_api.async_playwright = None
    sys.modules["playwright"] = playwright
    sys.modules["playwright.async_api"] = async_api
