"""CLI-facing inventory orchestration used by ``maops-py inventory ...``.

Thin wiring only: no argparse knowledge, no traversal or collection logic
of its own. Actual collection lives in
:mod:`maops_pydevops.core.system_inventory` and
:mod:`maops_pydevops.core.filesystem_inventory`.
"""

from __future__ import annotations

from maops_pydevops.core.filesystem_inventory import build_filesystem_report
from maops_pydevops.core.inventory_models import FilesystemInventoryReport, SystemInventoryReport
from maops_pydevops.core.system_inventory import build_system_report

__all__ = [
    "FilesystemInventoryReport",
    "SystemInventoryReport",
    "build_filesystem_report",
    "build_system_report",
]
