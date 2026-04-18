@echo off
setlocal

echo ========================================
echo  TapTapLoot Clicker - Build Script
echo ========================================
echo.

echo [1/4] Installing dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo [2/4] Installing PyInstaller...
python -m pip install pyinstaller
if errorlevel 1 goto :error

echo.
echo [3/4] Generating version info...
python _make_version_info.py
if errorlevel 1 goto :error

echo.
echo [4/4] Building exe...
if exist icon.ico (
    python -m PyInstaller --onefile --noconsole ^
        --name TapTapLootClicker ^
        --icon=icon.ico ^
        --version-file=version_info.txt ^
        --add-data "config.toml;." ^
        --hidden-import=win32timezone ^
        --hidden-import=PIL._tkinter_finder ^
        taptaploot_clicker.py
) else (
    echo [INFO] icon.ico not found, building without custom icon
    python -m PyInstaller --onefile --noconsole ^
        --name TapTapLootClicker ^
        --version-file=version_info.txt ^
        --add-data "config.toml;." ^
        --hidden-import=win32timezone ^
        --hidden-import=PIL._tkinter_finder ^
        taptaploot_clicker.py
)
if errorlevel 1 goto :error

echo.
echo [5/5] Tagging output with version...
set /p VER=<VERSION
if "%VER%"=="" (
    echo [ERROR] 無法讀取 VERSION 檔
    goto :error
)
copy /Y "dist\TapTapLootClicker.exe" "dist\TapTapLootClicker-v%VER%.exe" >nul
if errorlevel 1 (
    echo [ERROR] 版本化複製失敗
    goto :error
)

echo.
echo ========================================
echo  Build complete!
echo  Output:
echo    - dist\TapTapLootClicker.exe          (latest)
echo    - dist\TapTapLootClicker-v%VER%.exe   (versioned, for release)
echo ========================================
echo.
pause
exit /b 0

:error
echo.
echo ========================================
echo  Build FAILED. See errors above.
echo ========================================
pause
exit /b 1
