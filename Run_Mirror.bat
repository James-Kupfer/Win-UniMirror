@echo off
setlocal EnableDelayedExpansion

:: ---------------------------------------------------------------------------
:: run_mirror.bat
:: Mirrors configured source folders to a destination root using robocopy.
::
:: Steps performed automatically:
::   1. Load all settings from mirror_config.py (--env mode).
::   2. Pre-mirror rename pass: sanitize shell-problematic filenames in each
::      source folder via mirror_config.py <source>.
::   3. Build robocopy /xf exclusions from the persistent fail list.
::   4. Execute one robocopy /mir job per source folder.
::   5. Parse the robocopy log and append any newly failed paths to the
::      fail list for exclusion on future runs.
::
:: Configure all settings in src\mirror_config.py before running.
:: ---------------------------------------------------------------------------

echo Starting Mirror Process...

:: ---------------------------------------------------------
:: LOAD CONFIG from mirror_config.py (env mode)
:: ---------------------------------------------------------
set "CONFIG_SCRIPT=%~dp0src\mirror_config.py"
set "ERROR_FLAG=0"
set "ERROR_LOG="

for /f "usebackq tokens=1,* delims==" %%A in (`python "%CONFIG_SCRIPT%" --env`) do (
    set "%%A=%%B"
)

if errorlevel 1 (
    set "ERROR_FLAG=1"
    set "ERROR_LOG=!ERROR_LOG![CONFIG] Failed to load mirror_config.py. "
    goto report
)

:: ---------------------------------------------------------
:: Timestamp log file: mirror_YYYYMMDD_HHMM.log
:: ---------------------------------------------------------
for /f "tokens=1-4 delims=/ " %%A in ("%DATE%") do (
    set "D_DOW=%%A"
    set "D_MON=%%B"
    set "D_DAY=%%C"
    set "D_YR=%%D"
)
for /f "tokens=1-2 delims=:." %%A in ("%TIME: =0%") do (
    set "T_HR=%%A"
    set "T_MIN=%%B"
)
for %%F in ("%LOG_FILE%") do set "LOG_DIR=%%~dpF"
set "LOG_FILE=%LOG_DIR%mirror_%D_YR%%D_MON%%D_DAY%_%T_HR%%T_MIN%.log"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

:: Ensure fail list file exists
if not exist "%FAIL_LIST%" (
    type nul > "%FAIL_LIST%"
)

:: ---------------------------------------------------------
:: PRE-MIRROR RENAME PASS
:: Sanitizes shell-problematic characters and enforces max
:: name length before robocopy runs.
:: ---------------------------------------------------------
set /a IDX=0
:rename_loop
if !IDX! GEQ %SOURCE_COUNT% goto rename_done

set "SRC=!SOURCE_%IDX%!"
echo Sanitizing filenames in !SRC!...
python "%CONFIG_SCRIPT%" "!SRC!"

if errorlevel 2 (
    set "ERROR_FLAG=1"
    set "ERROR_LOG=!ERROR_LOG![RENAME] Source folder not found: !SRC!. "
)

set /a IDX+=1
goto rename_loop
:rename_done

:: ---------------------------------------------------------
:: BUILD /XF FROM FAIL LIST (filenames only)
:: robocopy /xf matches on filename, not full path.
:: ---------------------------------------------------------
set "FAIL_XF="
for /f "usebackq delims=" %%F in (`python "%CONFIG_SCRIPT%" --fail-filenames`) do (
    set "FAIL_XF=!FAIL_XF! "%%F""
)

:: ---------------------------------------------------------
:: ROBOCOPY FLAGS
:: /mir   - mirror (delete destination files not in source)
:: /XA:H  - exclude hidden files
:: /FFT   - use FAT file times (2-second granularity)
:: /A-:SH - remove System and Hidden attributes from copied files
:: /256   - disable very-long-path support (use \?\ prefix instead)
:: ---------------------------------------------------------
set "ROBO_FLAGS=/mir /XA:H /FFT /r:%ROBO_RETRIES% /w:1 /A-:SH /compress /256 /nodcopy %SPEED_FLAGS%"

:: Conditionally set /MAX flag (0 = no limit)
if "%ROBO_MAX_BYTES%"=="0" (
    set "MAX_FLAG="
) else (
    set "MAX_FLAG=/MAX:%ROBO_MAX_BYTES%"
)

:: ---------------------------------------------------------
:: EXECUTE MIRRORS
:: ---------------------------------------------------------
set /a IDX=0
:mirror_loop
if !IDX! GEQ %SOURCE_COUNT% goto mirror_done

set "SRC=!SOURCE_%IDX%!"
for %%F in ("!SRC!") do set "FOLDER_NAME=%%~nxF"
set "DEST=%MIRROR_ROOT%\!FOLDER_NAME!"

echo Mirroring !SRC! -^> !DEST!...
robocopy "!SRC!" "!DEST!" *.* %ROBO_FLAGS% ^
    /xd %EXCLUDE_DIRS% ^
    /xf %EXCLUDE_FILES% %FAIL_XF% ^
    %MAX_FLAG% ^
    /log+:"%LOG_FILE%"

set "RC=!ERRORLEVEL!"
if !RC! GEQ 4 (
    set "ERROR_FLAG=1"
    set "ERROR_LOG=!ERROR_LOG![!FOLDER_NAME!] Robocopy exited with code !RC!. "
)

set /a IDX+=1
goto mirror_loop

:mirror_done

:: ---------------------------------------------------------
:: POST-PROCESS: append newly failed paths to fail list
:: ---------------------------------------------------------
set "SRC_ARGS="
for /L %%I in (0,1,%SOURCE_COUNT%) do (
    if not "%%I"=="%SOURCE_COUNT%" (
        for /f "tokens=2 delims==" %%S in ('set SOURCE_%%I 2^>nul') do (
            set "SRC_ARGS=!SRC_ARGS! "%%S""
        )
    )
)
python "%CONFIG_SCRIPT%" --append-failures "%LOG_FILE%" !SRC_ARGS!

:report
if "%ERROR_FLAG%"=="1" (
    echo.
    echo ============================================================
    echo MIRROR COMPLETED WITH ERRORS
    echo ============================================================
    echo %ERROR_LOG%
    echo.
    echo Log file: %LOG_FILE%
    echo Fail list: %FAIL_LIST%
    echo Window will remain open. Press any key to close.
    echo ============================================================
    pause > nul
) else (
    echo.
    echo Mirror process completed successfully. Log: %LOG_FILE%
    echo Closing in 5 seconds...
    timeout /t 5 /nobreak > nul
)
