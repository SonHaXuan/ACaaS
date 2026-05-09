import os
import sys


# Keep repo-local pytest runs isolated from globally installed plugins.
if any(arg.endswith("pytest") or arg == "-m" for arg in sys.argv):
    os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
