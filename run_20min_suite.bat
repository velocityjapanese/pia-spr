@echo off
cd /d "%~dp0"
echo ========================================================
echo   Running 20-Minute Long-Form Piano Suite Generator
echo   (6 Movements, Evolving Keys & Tempos, YouTube Chapters)
echo ========================================================
python bot.py --minutes 20 --mood relaxing
echo.
echo 20-Minute Video and Chapters export completed! Check FINAL_EXPORTED_VIDEOS folder.
pause
