@echo off
cd /d "%~dp0"
echo ========================================================
echo   Running Long-Form 16:9 Landscape Piano Generator
echo ========================================================
python bot.py
echo.
echo Video export completed! Check FINAL_EXPORTED_VIDEOS folder.
pause
