import os
import sys

# Ensure the package can be imported when the repository root has the same name
# as the package directory.
PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PACKAGE_DIR not in sys.path:
    sys.path.insert(0, PACKAGE_DIR)
