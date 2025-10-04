@echo off
setlocal enabledelayedexpansion

echo [INFO] Starting batch script execution.
echo [INFO] Delayed expansion enabled.

:: --- Configuration ---
set VENV_DIR=venv
set PYTHON_EXE=python
:: AIRFLOW_HOME is now calculated dynamically below

echo.
echo =================================================================
echo Airflow/Kafka ETL Pipeline Environment Setup (Windows)
echo =================================================================
echo.

:: 1. Create Python Virtual Environment
if not exist %VENV_DIR% (
    echo [INFO] Creating virtual environment in .\%VENV_DIR%...
    %PYTHON_EXE% -m venv %VENV_DIR%
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment. Ensure Python is installed and in your PATH.
        goto :end
    )
    echo [INFO] Virtual environment created successfully.
) else (
    echo [INFO] Virtual environment .\%VENV_DIR% already exists. Skipping creation.
)

:: 2. Activate the Virtual Environment
echo [INFO] Activating virtual environment...
call %VENV_DIR%\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment. Exiting.
    goto :end
)
echo [INFO] Virtual environment activated.

:: 3. Install Required Python Dependencies
echo [INFO] Checking for required Python dependencies...
set "SENTINEL_FILE=%VENV_DIR%\install_complete.flag"

if exist %SENTINEL_FILE% (
    echo [INFO] Dependencies already installed (flag file found). Skipping pip install.
    goto :skip_install
)

echo [INFO] Dependencies not yet installed. Starting fresh installation.
pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install Python packages. Check your internet connection or package names.
    goto :deactivate
)
echo [INFO] Creating sentinel file to mark installation as complete.
echo Installation successful > %SENTINEL_FILE%
goto :continue_setup

:skip_install
echo [INFO] Dependencies check complete.

:continue_setup
echo [INFO] Dependencies flow logic successfully executed.

:: 4. Initialize Airflow Configuration (CRITICAL FIX FOR WINDOWS/SQLITE & FCNTL)
echo [INFO] Initializing Airflow Configuration...

:: Get Absolute Path of the project root
set "PROJECT_ROOT=%CD%"
echo [INFO] Current working directory (PROJECT_ROOT) is: %PROJECT_ROOT%

:: Set AIRFLOW_HOME to the absolute path of the target folder.
set "AIRFLOW_HOME=%PROJECT_ROOT%\airflow"

:: Construct the absolute path for the SQLite database file
set "DB_PATH=%AIRFLOW_HOME%\airflow.db"

:: CRITICAL FIX 1: SQLite URI on Windows requires absolute path AND forward slashes (/) 
:: We replace all backslashes in the path with forward slashes for URI compliance.
set "DB_URI_PATH=!DB_PATH:\=/!"

:: Set the final connection string
set "AIRFLOW__CORE__SQL_ALCHEMY_CONN=sqlite:///%DB_URI_PATH%"

:: CRITICAL FIX 2: Overriding core auth manager to prevent 'fcntl' (Unix-only) import during db initialization on Windows.
:: This is required because the default simple_auth_manager imports fcntl.
set "AIRFLOW__CORE__AUTH_MANAGER="

echo [INFO] Setting AIRFLOW_HOME to: %AIRFLOW_HOME%
echo [INFO] Setting DB Connection (Fix): %AIRFLOW__CORE__SQL_ALCHEMY_CONN%
echo [INFO] Setting CORE Auth Manager (Fix): <Empty String>
echo [INFO] Environment Variables set for Airflow initialization.

echo [INFO] Running 'airflow db migrate' to initialize database...
airflow db migrate
if errorlevel 1 (
    echo [ERROR] Database migration failed. Please check the full error log above.
    goto :deactivate
)

echo [INFO] Creating Airflow Admin User...
airflow users create --username admin --firstname Admin --lastname User --role Admin --email admin@example.com -p admin
if errorlevel 1 (
    echo [ERROR] Failed to create admin user. This usually happens if the user already exists. Continuing...
)

echo [INFO] Starting and killing Airflow services to ensure necessary files are created...
airflow webserver -D
airflow scheduler -D
airflow kill
echo [SUCCESS] Airflow initialization complete.

:deactivate
echo [INFO] Deactivating virtual environment...
call deactivate

:end
echo.
echo =================================================================
echo SETUP COMPLETE!
echo.
echo NEXT STEPS (CRITICAL):
echo 1. You must have Kafka and Airflow services running (recommend Docker Compose).
echo 2. Place "user_etl_dag.py" and "kafka_utils.py" into your "%AIRFLOW_HOME%\dags" folder.
echo 3. Start the Airflow Webserver and Scheduler using Docker or the following commands:
echo    ^> %VENV_DIR%\Scripts\activate.bat
echo    ^> airflow webserver -p 8080
echo    ^> airflow scheduler
echo =================================================================
pause
endlocal
