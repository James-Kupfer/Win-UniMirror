# Win-UniMirror

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

A Windows directory mirroring utility that uses `robocopy` for fast, reliable
one-way sync from configurable source folders to a destination root.

All configuration lives in `src/mirror_config.py`. The system is driven by a
single batch script (`Run_Mirror.bat`) that calls Python for configuration,
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
Win-UniMirror/
├── src/
│   └── mirror_config.py              # All settings, sanitization, and helpers
├── Run_Mirror.bat                    # Main launcher
├── src/mirror_failures_to_exclude.txt  # Auto-generated; tracks persistent failures
└── logs/                             # Auto-generated; timestamped robocopy logs
```

---

## Requirements

| Dependency | Notes |
|---|---|
| **Windows** | Robocopy is built into Windows Vista and later |
| **Python 3.10+** | Standard library only; no third-party packages required |

---

## Quick Start

### 1. Clone or download the repo

```bash
git clone https://github.com/James-Kupfer/Win-UniMirror.git
cd Win-UniMirror
```

### 2. Configure your settings

Open `src\mirror_config.py` and update the `MirrorSettings` dataclass:

- Set `source_folders` to the directories you want to mirror.
- Set `mirror_root` to your destination (e.g. a network drive or cloud-sync folder).
- Review `exclude_dirs` and `exclude_files` and remove or add entries as needed.
- Leave `max_bytes = 0` for no file size limit, or set a byte value to cap it.

> The defaults committed in this repo (`C:\Documents`, `C:\Beaker`,
> `O:\ProtonDrive\My files`, etc.) are personal example paths — replace them
> with your own before running.

### 3. Run the mirror

From the repo root, double-click:

```
Run_Mirror.bat
```

What happens automatically:

1. Settings are loaded from `mirror_config.py`.
2. Each source folder is scanned and any shell-problematic filenames are renamed.
3. Robocopy mirrors each source folder to a matching sub-folder under `mirror_root`.
4. The robocopy log is parsed and any failed paths are appended to the fail list.

### 4. Check the results

- **Success:** The window closes after 5 seconds.
- **Errors:** The window stays open and shows a summary. Check the log file at
  `logs\mirror_YYYYMMDD_HHMM.log` for details.

### 5. Schedule automatic mirrors (recommended)

Use Windows Task Scheduler to run `Run_Mirror.bat` on your desired schedule:

- **Action:** Start a program
- **Program/script:** `C:\path\to\Win-UniMirror\Run_Mirror.bat`
- **Start in:** `C:\path\to\Win-UniMirror`

### Dry-run name sanitization (optional)

To preview filename renames without applying them:

```cmd
python src\mirror_config.py "C:\YourSourceFolder" --dry-run
```

Remove `--dry-run` to apply the renames for real.

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
| `log_file` | `logs/mirror.log` | Base log path (`Run_Mirror.bat` appends timestamp) |

### Name sanitization constants

| Constant | Default | Description |
|---|---|---|
| `MAX_PATH_SAFE` | `230` | Maximum full path length before truncation |
| `MAX_NAME_LEN` | `150` | Maximum filename length after sanitization |
| `INVALID_CHARS` | `` `,&;%^!()[]{}'`~@#$+=` `` | Characters replaced with `_` |

---

## `mirror_config.py` CLI modes

`Run_Mirror.bat` drives `mirror_config.py` through these modes; they can also
be run directly for scripting or debugging:

```cmd
python src\mirror_config.py --env
    Emit all settings as KEY=VALUE lines (used internally by the .bat).

python src\mirror_config.py --append-failures <log> <src1> [src2 ...]
    Parse a robocopy log, append newly-failed paths to the fail list.

python src\mirror_config.py --fail-filenames
    Print basenames of fail-list entries (one per line), for robocopy /xf.

python src\mirror_config.py <source_path> [--dry-run]
    Sanitize file/dir names under source_path; --dry-run previews without renaming.
```

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

`src/mirror_failures_to_exclude.txt` records the full path of any file robocopy
could not copy. On subsequent runs, those filenames are automatically added to
the robocopy `/xf` exclusion list so they do not cause repeated errors.

To clear the fail list, delete or empty `src/mirror_failures_to_exclude.txt`.

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).
