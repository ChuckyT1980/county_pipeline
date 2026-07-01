@echo off
setlocal

set CMD=%1
set ARG1=%2
set ARG2=%3
set ARG3=%4

if "%CMD%"=="" (
    echo Usage: obs.bat [run^|verify^|health^|query^|compat]
    exit /b 1
)

if "%CMD%"=="run" (
    echo Starting Production Pipeline...
    python run_controller.py
    exit /b %ERRORLEVEL%
)

if "%CMD%"=="verify" (
    if "%ARG1%"=="" (
        echo Usage: obs.bat verify [RUN_ID]
        exit /b 1
    )
    echo Verifying RUN_ID: %ARG1%
    python -m scheduler.replay_engine %ARG1%
    python analysis/drift_engine.py %ARG1%
    python analysis/evolution_tracker.py %ARG1%
    exit /b %ERRORLEVEL%
)

if "%CMD%"=="health" (
    if "%ARG1%"=="" (
        echo Usage: obs.bat health [RUN_ID]
        exit /b 1
    )
    python query.py system health %ARG1%
    exit /b %ERRORLEVEL%
)

if "%CMD%"=="query" (
    if "%ARG1%"=="" (
        echo Usage: obs.bat query "[DOMAIN]" "[ACTION]" "[ARGS...]"
        exit /b 1
    )
    python query.py %ARG1% %ARG2% %ARG3%
    exit /b %ERRORLEVEL%
)

if "%CMD%"=="compat" (
    if "%ARG3%"=="" (
        echo Usage: obs.bat compat "[COMMAND]" "[V1]" "[V2]"
        exit /b 1
    )
    python query.py compat compare %ARG1% %ARG2% %ARG3%
    exit /b %ERRORLEVEL%
)

echo Unknown command: %CMD%
exit /b 1
