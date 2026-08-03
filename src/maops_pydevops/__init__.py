"""MAOps Python DevOps Automation Toolkit.

Importing this package has no side effects: the version is looked up
lazily via :func:`maops_pydevops.version.get_version`, never at import
time.
"""

from __future__ import annotations

from maops_pydevops.version import get_version

__all__ = ["get_version"]
