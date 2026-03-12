# Quick Start

Follow these steps to run your first mirror using `run_mirror.bat`.

## 1. Clone or download the repo

```bash
git clone https://github.com/<your-username>/windows-robocopy-mirror.git
cd windows-robocopy-mirror
```

## 2. Configure your settings

Open `src\mirror_config.py` and update the `MirrorSettings` dataclass:

- Set `source_folders` to the directories you want to mirror.
- Set `mirror_root` to your destination (e.g. a network drive or cloud-sync folder).
- Review `exclude_dirs` and `exclude_files` and remove or add entries as needed.
- Leave `max_bytes = 0` for no file size limit, or set a byte value to cap it.

## 3. Run the mirror

From the repo root, double-click:

```
run_mirror.bat
```

What happens automatically:

1. Settings are loaded from `mirror_config.py`.
2. Each source folder is scanned and any shell-problematic filenames are renamed.
3. Robocopy mirrors each source folder to a matching sub-folder under `mirror_root`.
4. The robocopy log is parsed and any failed paths are appended to the fail list.

## 4. Check the results

- **Success:** The window closes after 5 seconds.
- **Errors:** The window stays open and shows a summary. Check the log file at
  `logs\mirror_YYYYMMDD_HHMM.log` for details.

## 5. Schedule automatic mirrors (recommended)

Use Windows Task Scheduler to run `run_mirror.bat` on your desired schedule:

- **Action:** Start a program
- **Program/script:** `C:\path\to\repo\run_mirror.bat`
- **Start in:** `C:\path\to\repo`

## Dry-run name sanitization (optional)

To preview filename renames without applying them:

```cmd
python src\mirror_config.py "C:\YourSourceFolder" --dry-run
```

Remove `--dry-run` to apply the renames for real.
