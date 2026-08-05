# Filesystem Inventory Safety

`src/maops_pydevops/core/filesystem_inventory.py` implements
`maops-py inventory filesystem`'s bounded, read-only, deterministic
filesystem scanner. This document describes its full safety contract —
what it never does, and the exact boundaries of what it does.

## Read-only metadata collection only

The scanner calls `os.lstat()`, `os.scandir()`, and `os.DirEntry.stat()`
exclusively. It never calls `open()`, `Path.open()`, `Path.read_text()`,
or `Path.read_bytes()` on a scanned entry. Every collected field —
`size_bytes`, `modified_ns`, entry type — comes from filesystem metadata
(`stat` results), never from opening or interpreting a file's contents.

## No file-content reads

Directly enforced by the point above: the scanner has no code path that
opens a regular file it discovers during traversal, regardless of its
extension, size, or apparent type.

## No hashing

The scanner never imports or calls `hashlib`. It reports size and
modification time, never a content digest — computing one would require
reading file content, which the scanner never does.

## No symlink traversal

Every entry — including the scan root itself — is classified via a
non-following stat call (`os.lstat()` for the root, `entry.stat(follow_symlinks=False)`
for every discovered entry). A symbolic link is counted as a symlink and
its target is never entered, dereferenced, or sized, regardless of
whether the target is a regular file, a directory, or nonexistent
(broken). This is what makes a self-referential symlink loop
structurally impossible to recurse into — a symlink pointing back at an
ancestor directory is just counted like any other symlink, never
followed.

## Same-filesystem boundary

The scan root's device number (`st_dev` from the initial `lstat()`) is
captured once before traversal begins. Every directory entry discovered
during traversal has its own `st_dev` compared against the root's; a
mismatch means the entry is counted (as a directory, and separately as a
`different_filesystem_entries`) but never recursed into — its own
contents are never enumerated, regardless of remaining depth or entry
budget. This is the scanner's mount-point boundary: it never crosses onto
a different filesystem/device than the one the scan root lives on.

## Max-depth limit

The root is depth `0`. A directory's own contents are only enumerated if
`(that directory's depth) + 1 <= max_depth` — i.e. `--max-depth 0` means
the root's own children are never enumerated at all (`os.scandir()` is
never even called on the root), while `--max-depth 2` enumerates the
root's children (depth 1) and grandchildren (depth 2), but never
descends into a depth-2 directory's own children (depth 3). A directory
whose contents were skipped purely due to this limit is still itself
counted by its parent's scan; `max_depth_reached` is set to `true`
whenever this happens at least once during the scan.

## Max-entry limit

`max_entries` is a hard cap on the total number of successfully-`stat`'d
entries (`scanned_entries`). Once reached, enumeration stops immediately
— even mid-directory — and `truncated` is set to `true`. The cutoff point
is fully deterministic given the same tree and the same limit, because
traversal order itself is deterministic (see below); it is not
deterministic in the sense of "always finishes the current directory
first."

## Deterministic traversal

Within each directory, entries are enumerated via `os.scandir()` and
sorted by entry **name** (not a normalized relative path) before being
processed. Traversal is depth-first: a directory's own entry is recorded,
then its children are fully processed (subject to the depth/entry limits
above), before moving to that directory's next sibling. This name-based,
per-directory sort was chosen over a global normalized-relative-path sort
for simplicity — it is sufficient to make traversal order, largest-file
tie-breaking, and truncation cutoffs fully deterministic for a given tree
and given limits, without the added complexity of a whole-tree sort.

## Race handling

Entries can disappear or change between `os.scandir()` enumerating them
and the scanner's own `stat()` call on each one. `FileNotFoundError`
(entry vanished) and `NotADirectoryError` (a path component was replaced
by something else mid-scan) are recorded as `skipped_entries`;
`PermissionError` and any other `OSError` subclass are recorded as
`inaccessible_entries`. Either way, one structured `InventoryIssue` entry
is appended and the scan continues with the next sibling — a race never
aborts an otherwise-meaningful scan. A directory that itself becomes
unreadable or vanishes between being discovered and having
`os.scandir()` called on it is handled identically. Only `OSError` and
its subclasses are caught this way; an unexpected non-`OSError` exception
(a genuine programming error) is never silently swallowed — it propagates
normally.

## Apparent size vs. allocated disk blocks

`size_bytes` is `st_size` — the file's apparent logical size, as reported
by the filesystem. This is **not** the number of disk blocks actually
allocated to the file (`st_blocks * block_size`), which can differ
meaningfully for sparse files, filesystem compression, or deduplication.
`total_file_bytes` in a report's summary is the sum of every scanned
regular file's `st_size`, for the same reason: an apparent-size total,
not a disk-usage total. This inventory is not a disk-usage tool.

## Special files

Sockets, named pipes (FIFOs), and device files encountered during
traversal (at the root or nested) are counted as `other` and never read,
opened, or connected to.

## Permission limitations

The scanner runs with the invoking user's own filesystem permissions —
it does not attempt privilege elevation, and a directory or file it
cannot access due to permissions becomes a structured issue (see "Race
handling" above), not a crash. It cannot see more of the filesystem than
the invoking user already could.

## Root symlink behavior

If the scan root itself is a symbolic link, it is classified via
`os.lstat()` and reported as a single symlink entry — it is **never**
followed to determine whether it points at a file or a directory, even
though following it might seem like the more "useful" behavior for a
root argument specifically. This is deliberate and consistent with the
rest of the module's never-follow-symlinks policy: a broken symlink root
(pointing at a nonexistent target) produces the identical valid,
error-free report as a symlink pointing at real content, since target
validity is never inspected.

## Why this is not a malware scanner, backup verifier, or forensic tool

This scanner deliberately does none of the things those tools need:

- **Not a malware scanner**: it never reads file content, so it cannot
  inspect content for signatures, patterns, or embedded scripts.
- **Not a backup verifier**: it never computes a checksum or hash, so it
  cannot prove two files are byte-identical, only that their reported
  size and modification time match.
- **Not a forensic tool**: it does not preserve access times, does not
  capture extended attributes, ownership, or permission bits in its
  report, and does not create a tamper-evident record of what it
  observed. `os.lstat()`/`os.scandir()` calls themselves may update a
  directory's access time on some filesystems, which a forensic
  collection process would need to explicitly avoid or account for.

It is a bounded, deterministic, read-only *summary* tool — sized for
answering "roughly what's in this tree, and how big is it" quickly and
safely, not for any task that depends on content integrity or a
legally-defensible chain of custody.
