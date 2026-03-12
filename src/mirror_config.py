"""
mirror_config.py
----------------
Configuration, pre-mirror filename sanitization, fail-list management,
and robocopy log parsing for the Windows mirror system.

This module serves a dual purpose:

1. **Imported by run_mirror.bat** via subprocess to emit KEY=VALUE environment
   variables that drive the robocopy mirror jobs.
2. **Invoked directly** as a script for pre-mirror filename sanitization and
   post-mirror failure tracking.

CLI modes
---------
``--env``
    Emit all settings as KEY=VALUE lines for the BAT to parse.
``--append-failures <log> <src1> [src2 ...]``
    Parse a robocopy log and append any newly failed source paths to the
    persistent fail list.
``--fail-filenames``
    Print the filename (basename only) of each fail-list entry, one per line,
    for use in robocopy ``/xf``.
``<source_path> [--dry-run]``
    Sanitize file and directory names under *source_path*, renaming anything
    that contains shell-problematic characters or exceeds the name-length
    limit.  Pass ``--dry-run`` to preview changes without renaming.

Layout
------
MirrorSettings       - all user-tunable settings (source folders, destination,
                       robocopy flags, exclusions, file size limit).
sanitize / rename    - helpers that clean filenames before mirroring.
fail-list helpers    - track files that robocopy could not copy so they can
                       be excluded on subsequent runs.
log parser           - extract failed source paths from a robocopy log.
emit_env             - serialize settings to KEY=VALUE for the BAT.
"""

import os
import re
import sys
from dataclasses import dataclass, field
from typing import List

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

#: Absolute path to the project root (one level above this file).
SCRIPT_BASE_DIR: str = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir)
)

#: Persistent file that records source paths robocopy failed to copy.
FAIL_LIST_PATH: str = os.path.join(
    os.path.dirname(__file__), "mirror_failures_to_exclude.txt"
)


# ---------------------------------------------------------------------------
# Settings dataclass
# ---------------------------------------------------------------------------

@dataclass
class MirrorSettings:
    """All settings consumed by ``run_mirror.bat`` via robocopy.

    Attributes:
        source_folders: Top-level directories to mirror (one robocopy job each).
        mirror_root:    Destination root; each source folder maps to a
                        same-named sub-folder here.
        threads:        Robocopy multi-thread count (``/MT:<n>``).
        retries:        Robocopy retry count per failed file (``/r:<n>``).
        show_progress:  Show per-file copy progress (``/np`` suppresses it).
        show_file_list: Show copied file names in log (``/nfl`` suppresses it).
        show_dir_list:  Show traversed directory names in log (``/ndl``
                        suppresses it).
        exclude_dirs:   Directory names / patterns passed to robocopy ``/xd``.
        exclude_files:  File patterns passed to robocopy ``/xf``.
        max_bytes:      Maximum file size to copy in bytes (``/MAX:<n>``).
                        Set to ``0`` to disable the limit (no ``/MAX`` flag).
        log_file:       Base log path; the BAT appends a timestamp before use.
    """

    source_folders: List[str] = field(default_factory=lambda: [
        r"C:\Documents",
        r"C:\Beaker",
    ])
    mirror_root: str = r"O:\ProtonDrive\My files"

    # Robocopy performance flags
    threads: int = 32           # /MT:
    retries: int = 5            # /r:
    show_progress: bool = False  # False = /np
    show_file_list: bool = False # False = /nfl
    show_dir_list: bool = False  # False = /ndl

    exclude_dirs: List[str] = field(default_factory=lambda: [
        "*KNIME*", "*RECYCLE*", "AppData", "Application Data", "*Cookies*",
        "Local Settings", "My Music", "My Pictures", "My Videos",
        "NetHood", "PrintHood", "Start Menu", "Cache",
        "temp", r"Market Data\Raw",
    ])
    exclude_files: List[str] = field(default_factory=lambda: [
        "*.tmp", "*.log", "*.bin",
        "*.ldf", "*.mdf", "*.ndf",
        "*.DAT", "*.bak", "*.trn",
        "*.db", "*.sqlite", "*.sqlite3",
    ])

    max_bytes: int = 0  # 0 = no /MAX limit

    log_file: str = field(
        default_factory=lambda: os.path.join(SCRIPT_BASE_DIR, "logs", "mirror.log")
    )


# ---------------------------------------------------------------------------
# Name sanitization constants
# ---------------------------------------------------------------------------

#: Maximum total path length before we start truncating names.
MAX_PATH_SAFE: int = 230

#: Maximum filename length (base + extension) after sanitization.
MAX_NAME_LEN: int = 150

#: Characters valid on NTFS but problematic for shells / robocopy.
INVALID_CHARS: re.Pattern = re.compile(r"[,&;%^!()\[\]{}'`~@#$+=]")

#: Replacement character for invalid characters.
REPLACEMENT: str = "_"


# ---------------------------------------------------------------------------
# Name sanitization helpers
# ---------------------------------------------------------------------------

def truncate_name(name: str, max_len: int = MAX_NAME_LEN) -> str:
    """Shorten *name* to *max_len* characters while preserving the extension.

    Args:
        name:    File or directory name to truncate.
        max_len: Maximum allowed length.

    Returns:
        Truncated name with the original extension intact, or *name* unchanged
        if it is already within the limit.
    """
    if len(name) <= max_len:
        return name
    base, ext = os.path.splitext(name)
    keep_base_len = max(1, max_len - len(ext))
    return base[:keep_base_len] + ext


def sanitize_name_for_dir(
    dirpath: str, name: str, excluded_roots: List[str]
) -> str:
    """Return a sanitized version of *name*, or *name* unchanged if it is safe.

    Sanitization replaces shell-problematic characters with underscores and
    truncates the result if it still exceeds ``MAX_NAME_LEN`` or would push
    the full path beyond ``MAX_PATH_SAFE``.

    Files inside any of *excluded_roots* are skipped entirely so that
    already-excluded directories are not renamed unnecessarily.

    If the sanitized target path already exists, the original name is returned
    to avoid a collision.

    Args:
        dirpath:        Directory containing the file or sub-directory.
        name:           File or directory name to sanitize.
        excluded_roots: Absolute paths that should not be sanitized.

    Returns:
        Sanitized name, or the original *name* if no change is needed or safe.
    """
    norm_dir = os.path.normcase(os.path.abspath(dirpath))
    for ex in excluded_roots:
        if norm_dir.startswith(os.path.normcase(os.path.abspath(ex))):
            return name

    cleaned = INVALID_CHARS.sub(REPLACEMENT, name)
    cleaned = truncate_name(cleaned, MAX_NAME_LEN)

    base, ext = os.path.splitext(cleaned)
    while len(os.path.join(dirpath, cleaned)) > MAX_PATH_SAFE and len(base) > 1:
        base = base[:-1]
        cleaned = base + ext

    if os.path.exists(os.path.join(dirpath, cleaned)):
        return name

    return cleaned


def rename_tree(
    root: str, excluded_roots: List[str], dry_run: bool = False
) -> list[tuple[str, str]]:
    """Walk *root* bottom-up and rename any files or directories that need it.

    Bottom-up traversal ensures child paths are renamed before their parents,
    so parent-directory renames do not invalidate child paths mid-walk.

    Args:
        root:           Top-level directory to sanitize.
        excluded_roots: Sub-trees to leave untouched.
        dry_run:        If ``True``, collect renames without applying them.

    Returns:
        List of ``(old_path, new_path)`` tuples for every rename performed
        (or that would be performed during a dry run).
    """
    renamed: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        for fname in filenames:
            clean = sanitize_name_for_dir(dirpath, fname, excluded_roots)
            if clean != fname:
                old = os.path.join(dirpath, fname)
                new = os.path.join(dirpath, clean)
                if not dry_run:
                    os.rename(old, new)
                renamed.append((old, new))

        for dname in dirnames:
            clean = sanitize_name_for_dir(dirpath, dname, excluded_roots)
            if clean != dname:
                old = os.path.join(dirpath, dname)
                new = os.path.join(dirpath, clean)
                if not dry_run:
                    os.rename(old, new)
                renamed.append((old, new))

    return renamed


# ---------------------------------------------------------------------------
# Fail-list helpers
# ---------------------------------------------------------------------------
# The fail list stores FULL paths for human readability and auditing.
# When passed to robocopy /xf we extract just the filename, since
# robocopy /xf matches on filename only, not the full path.

def load_fail_list() -> set[str]:
    """Return the set of normalised full paths stored in the fail list.

    Returns:
        Empty set if the fail list does not yet exist.
    """
    if not os.path.exists(FAIL_LIST_PATH):
        return set()
    with open(FAIL_LIST_PATH, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def append_failures(failed_paths: list[str]) -> None:
    """Append *failed_paths* to the fail list, skipping existing entries.

    Args:
        failed_paths: Full source paths that robocopy could not copy.
    """
    if not failed_paths:
        return
    existing = load_fail_list()
    new_items = [p for p in failed_paths if p not in existing]
    if not new_items:
        return
    with open(FAIL_LIST_PATH, "a", encoding="utf-8") as f:
        for p in new_items:
            f.write(p + "\n")


def emit_fail_filenames() -> None:
    """Print the basename of every fail-list entry, one per line.

    The BAT uses this output to build the robocopy ``/xf`` argument.
    """
    for entry in sorted(load_fail_list()):
        print(os.path.basename(entry))


# ---------------------------------------------------------------------------
# Log parser
# ---------------------------------------------------------------------------

# Matches robocopy error lines such as:
# 2026/03/08 08:28:16 ERROR 3 (0x00000003) Copying File C:\some\path\file.ext
_ERROR_LINE_RE: re.Pattern = re.compile(
    r"ERROR\s+\d+\s+\(0x[\dA-Fa-f]+\)\s+Copying File\s+(?P<path>.+)$"
)


def extract_failed_paths(log_path: str, sources: List[str]) -> list[str]:
    """Parse a robocopy log and return source file paths that failed.

    Only paths rooted under one of *sources* are included; unrelated entries
    are ignored.

    Args:
        log_path: Absolute path to the robocopy log file.
        sources:  List of source root directories used in the mirror run.

    Returns:
        Sorted list of unique failed source file paths.
    """
    if not os.path.exists(log_path):
        return []

    src_norms = [
        os.path.normcase(os.path.abspath(s.strip('"\'))) for s in sources
    ]
    failed: set[str] = set()

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = _ERROR_LINE_RE.search(line.rstrip("\n"))
            if not m:
                continue
            raw_path = m.group("path").strip()
            if not os.path.isabs(raw_path):
                continue
            norm = os.path.normcase(os.path.abspath(raw_path))
            if any(norm.startswith(s) for s in src_norms):
                failed.add(raw_path)

    return sorted(failed)


# ---------------------------------------------------------------------------
# Environment emitter for BAT
# ---------------------------------------------------------------------------

def emit_env() -> None:
    """Print all settings as KEY=VALUE lines for ``run_mirror.bat`` to parse.

    Also creates the log directory if it does not already exist.
    """
    cfg = MirrorSettings()

    print(f"MIRROR_ROOT={cfg.mirror_root}")
    print(f"ROBO_THREADS={cfg.threads}")
    print(f"ROBO_RETRIES={cfg.retries}")
    print(f"ROBO_MAX_BYTES={cfg.max_bytes}")  # 0 means omit /MAX
    print(f"LOG_FILE={cfg.log_file}")
    print(f"FAIL_LIST={FAIL_LIST_PATH}")

    os.makedirs(os.path.dirname(cfg.log_file), exist_ok=True)

    xd_parts = [f'"{d}"' if " " in d else d for d in cfg.exclude_dirs]
    print(f"EXCLUDE_DIRS={' '.join(xd_parts)}")
    print(f"EXCLUDE_FILES={' '.join(cfg.exclude_files)}")

    for i, folder in enumerate(cfg.source_folders):
        print(f"SOURCE_{i}={folder}")
    print(f"SOURCE_COUNT={len(cfg.source_folders)}")

    speed_flags = f"/MT:{cfg.threads}"
    if not cfg.show_progress:
        speed_flags += " /np"
    if not cfg.show_file_list:
        speed_flags += " /nfl"
    if not cfg.show_dir_list:
        speed_flags += " /ndl"
    print(f"SPEED_FLAGS={speed_flags}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--env":
        emit_env()

    elif len(sys.argv) > 1 and sys.argv[1] == "--append-failures":
        # Usage: mirror_config.py --append-failures <log> <src1> [src2 ...]
        if len(sys.argv) < 4:
            print("Usage: mirror_config.py --append-failures <log> <src1> [src2 ...]")
            sys.exit(0)
        log_path = sys.argv[2]
        srcs = sys.argv[3:]
        failed = extract_failed_paths(log_path, srcs)
        if failed:
            print(f" Appending {len(failed)} failed path(s) to fail list:")
            for p in failed:
                print(f"  {p}")
        else:
            print(" No new failures found in log.")
        append_failures(failed)

    elif len(sys.argv) > 1 and sys.argv[1] == "--fail-filenames":
        emit_fail_filenames()

    else:
        # Rename mode: mirror_config.py <source_path> [--dry-run]
        if len(sys.argv) < 2:
            print(
                "Usage: mirror_config.py --env | --append-failures | "
                "--fail-filenames | <source_path> [--dry-run]"
            )
            sys.exit(1)
        source = sys.argv[1]
        dry = "--dry-run" in sys.argv
        cfg = MirrorSettings()
        excluded_roots = [d for d in cfg.exclude_dirs if os.path.isabs(d)]
        if not os.path.isdir(source):
            print(f"ERROR: Source folder not found: {source}")
            sys.exit(2)
        results = rename_tree(source, excluded_roots, dry_run=dry)
        if results:
            label = "[DRY RUN] Would rename" if dry else "Renamed"
            for old, new in results:
                print(f"  {label}: {old} -> {os.path.basename(new)}")
            print(f"  Total: {len(results)} item(s) renamed.")
        else:
            print(" No invalid or over-length names found. Nothing renamed.")
