@echo off
setlocal
cd /d "%~dp0"

rem Creates a "Stock Matcher" shortcut on the Desktop that starts the app
rem with its console window minimized.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d = [Environment]::GetFolderPath('Desktop');" ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Stock Matcher.lnk'));" ^
  "$s.TargetPath = (Join-Path '%~dp0' 'start_stock_matcher.bat');" ^
  "$s.WorkingDirectory = '%~dp0';" ^
  "$s.IconLocation = (Join-Path '%~dp0' 'resources\stock_matcher.ico');" ^
  "$s.WindowStyle = 7;" ^
  "$s.Description = 'Script to stock video matcher';" ^
  "$s.Save()"

if errorlevel 1 (
    echo [ERROR] Could not create the shortcut.
) else (
    echo Done: "Stock Matcher" shortcut created on your Desktop.
)
echo.
pause
