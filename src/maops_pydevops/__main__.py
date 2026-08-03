"""Enable ``python -m maops_pydevops`` to invoke the same CLI as ``maops-py``."""

from __future__ import annotations

import sys

from maops_pydevops.cli import main

if __name__ == "__main__":
    sys.exit(main())
