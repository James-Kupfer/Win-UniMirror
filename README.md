# Windows Robocopy Mirror

A Windows directory mirroring utility that uses `robocopy` for fast, reliable
one-way sync from configurable source folders to a destination root.

All configuration lives in `src/mirror_config.py`. The system is driven by a
single batch script (`run_mirror.bat`) that calls Python for configuration,
pre-flight filename sanitization, and post-run failure tracking.

---

## Features

| Feature | Details |
|---|---|
| **Robocopy mirroring** | One `/mir` job per source folder; destination exactly matches source |
| **Pre-mirror rename** | Sanitizes shell-problematic characters and truncates over-length names before sync |
| **Fail list** | Tracks files robocopy cannot copy; auto-excludes them on future runs |
| **Log parsing** | Automatically extracts failed paths from the robocopy log after each run |
| **Configurable exclusions** | Per-directory and per-extension exclusions via `mirror_config.py` |
| **File size limit** | Optional `/MAX` cap; set `max_bytes = 0` to disable |
| **Performance tuning** | Configurable thread count, retry count, and log verbosity |
| **Timestamped logs** | Each run writes a dated log file to `<project_root>/logs/` |

---

## Project Structure

```
<project_root>/
├── src/
│   └── mirror_config.py              # All settings, sanitization, and helpers
├── run_mirror.bat                    # Main launcher
├── mirror_failures_to_exclude.txt    # Auto-generated; tracks persistent failures
└── logs/                             # Auto-generated; timestamped robocopy logs
```

---

## Requirements

| Dependency | Notes |
|---|---|
| **Windows** | Robocopy is built into Windows Vista and later |
| **Python 3.10+** | Standard library only; no third-party packages required |

---

## Configuration Reference

All settings are in the `MirrorSettings` dataclass in `src/mirror_config.py`.

| Field | Default | Description |
|---|---|---|
| `source_folders` | `[C:\Documents, C:\Beaker]` | Directories to mirror (one robocopy job each) |
| `mirror_root` | `O:\ProtonDrive\My files` | Destination root |
| `threads` | `32` | Robocopy `/MT:` thread count |
| `retries` | `5` | Robocopy `/r:` retries per failed file |
| `show_progress` | `False` | Show per-file progress (`/np` suppresses) |
| `show_file_list` | `False` | Log copied file names (`/nfl` suppresses) |
| `show_dir_list` | `False` | Log traversed directories (`/ndl` suppresses) |
| `exclude_dirs` | *(see config)* | Directory names/patterns for `/xd` |
| `exclude_files` | *(see config)* | File patterns for `/xf` |
| `max_bytes` | `0` | Max file size to copy; `0` = no limit |
| `log_file` | `logs/mirror.log` | Base log path (BAT appends timestamp) |

### Name sanitization constants

| Constant | Default | Description |
|---|---|---|
| `MAX_PATH_SAFE` | `230` | Maximum full path length before truncation |
| `MAX_NAME_LEN` | `150` | Maximum filename length after sanitization |
| `INVALID_CHARS` | `` `,&;%^!()[]{}'`~@#$+=` `` | Characters replaced with `_` |

---

## Logging

Each run writes a timestamped log to `<project_root>/logs/`:

```
logs/mirror_YYYYMMDD_HHMM.log
```

Robocopy exit codes 0-3 are considered successful; code 4 and above trigger
the error report in the console window.

---

## Fail List

`mirror_failures_to_exclude.txt` records the full path of any file robocopy
could not copy. On subsequent runs, those filenames are automatically added to
the robocopy `/xf` exclusion list so they do not cause repeated errors.

To clear the fail list, delete or empty `mirror_failures_to_exclude.txt`.
