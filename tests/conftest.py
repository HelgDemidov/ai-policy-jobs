"""Shared test setup: put scripts/ on sys.path, matching how the scripts
themselves resolve their own imports. run.py/store.py import as plain
sibling modules; scripts/connectors/{ats,query}/ import as subpackages of
that same sys.path root (e.g. `from connectors.ats import lever`)."""
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# web/api/ is its own sys.path root, deliberately NOT scripts/ — it deploys
# under web/'s Vercel Root Directory, which can't reach outside itself.
WEB_API_DIR = Path(__file__).resolve().parent.parent / "web" / "api"
if str(WEB_API_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_API_DIR))
