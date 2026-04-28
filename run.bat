@echo off
setlocal

:: Define the virtual environment directory
set VENV_DIR=.venv

:: Check if the virtual environment exists
if not exist "%VENV_DIR%" (
    echo [System] Virtual environment not found. Creating one...
    python -m venv %VENV_DIR%
    if errorlevel 1 (
        echo [Error] Failed to create virtual environment. Please ensure Python is installed and in your PATH.
        pause
        exit /b 1
    )
    
    echo [System] Installing required libraries: textual and requests...
    "%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip
    "%VENV_DIR%\Scripts\python.exe" -m pip install textual requests
    if errorlevel 1 (
        echo [Error] Failed to install dependencies.
        pause
        exit /b 1
    )
)

:: Launch the application
echo [System] Launching MC Manager...
"%VENV_DIR%\Scripts\python.exe" mc_manager_tui.py %*

if errorlevel 1 (
    echo [System] Application exited with an error.
    pause
)

endlocal
