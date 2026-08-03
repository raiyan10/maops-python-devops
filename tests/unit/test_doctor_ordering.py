"""Doctor check ordering is fixed and deterministic across repeated calls."""

from maops_pydevops.commands.doctor import build_report

EXPECTED_ORDER = [
    "python_version",
    "package_import",
    "os_family",
    "temp_directory",
    "filesystem_encoding",
    "python_executable",
    "git",
    "docker",
    "kubectl",
    "terraform",
    "ansible",
]


def test_check_ordering_is_deterministic() -> None:
    first = [check.name for check in build_report().checks]
    second = [check.name for check in build_report().checks]
    assert first == second == EXPECTED_ORDER
