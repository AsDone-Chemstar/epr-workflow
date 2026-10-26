
@echo off
cd /d "D:\EPR workflow"
".venv\Scripts\python.exe" "run_gui.py"
if errorlevel 1 (
    echo.
    echo EPR Workflow exited with an error.
    pause
)
