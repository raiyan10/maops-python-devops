#!/usr/bin/env python3
"""Normalize file-mode bits inside built wheel/sdist archives.

Building from a filesystem that always reports files as mode 0777 (e.g. a
WSL drvfs-mounted Windows path) leaks those permissions into the archives
that ``python -m build`` produces, since setuptools copies the source
filesystem's mode bits by default. This rewrites every regular-file entry
in dist/*.whl (ZIP) and dist/*.tar.gz (tar) to mode 0644, and every
directory entry to 0755, regardless of what the source filesystem
reported.

Only zip/tar metadata is rewritten, never file content, so wheel RECORD
hashes (computed over content only) remain valid.

Usage: normalize_archive_permissions.py <dist_dir>
"""

from __future__ import annotations

import stat
import sys
import tarfile
import zipfile
from pathlib import Path

REGULAR_FILE_MODE = 0o644
DIRECTORY_MODE = 0o755


def normalize_wheel(path: Path) -> None:
    tmp_path = path.with_name(path.name + ".tmp")
    with (
        zipfile.ZipFile(path, "r") as source,
        zipfile.ZipFile(tmp_path, "w") as dest,
    ):
        for info in source.infolist():
            data = source.read(info.filename)
            is_dir = info.filename.endswith("/")
            mode = DIRECTORY_MODE if is_dir else REGULAR_FILE_MODE
            type_bits = stat.S_IFDIR if is_dir else stat.S_IFREG

            new_info = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            new_info.compress_type = info.compress_type
            new_info.create_system = info.create_system
            new_info.external_attr = (type_bits | mode) << 16
            dest.writestr(new_info, data)
    tmp_path.replace(path)


def normalize_sdist(path: Path) -> None:
    tmp_path = path.with_name(path.name + ".tmp")
    with (
        tarfile.open(path, "r:gz") as source,
        tarfile.open(tmp_path, "w:gz") as dest,
    ):
        for member in source.getmembers():
            fileobj = source.extractfile(member) if member.isfile() else None
            member.mode = DIRECTORY_MODE if member.isdir() else REGULAR_FILE_MODE
            member.uid = 0
            member.gid = 0
            member.uname = ""
            member.gname = ""
            dest.addfile(member, fileobj=fileobj)
    tmp_path.replace(path)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: normalize_archive_permissions.py <dist_dir>", file=sys.stderr)
        return 2

    dist_dir = Path(argv[1])
    for wheel in sorted(dist_dir.glob("*.whl")):
        normalize_wheel(wheel)
        print(f"normalized: {wheel}")
    for sdist in sorted(dist_dir.glob("*.tar.gz")):
        normalize_sdist(sdist)
        print(f"normalized: {sdist}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
