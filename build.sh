#!/usr/bin/env bash

# Set strict mode: exit on error, treat unset variables as error, and propagate errors in pipelines
set -euo pipefail

# --- CONFIGURATION ---
# The sentinel file used to check if dependencies were previously installed.
INSTALL_FLAG_FILE="venv/install_complete.flag"
# Airflow environment directory relative to project root
AIRFLOW_HOME="airflow"
# Debug mode flag. Run as 'DEBUG=true ./build.sh' to enable.
DEBUG=false

# Function to safely echo messages based on type
log() {
    local type="$1"
    local message="$2"
    case "$type" in
        "INFO") echo "[INFO] $message" ;;
        "SUCCESS") echo "[SUCCESS] $message" ;;
        "ERROR") echo "[ERROR] $message" >&2 ;;
    esac
}

# Function to run when the script exits (even on error)
cleanup_and_exit() {
    local exit_code=$?
    if [ "$exit_code" -ne 0 ]; then
        log "ERROR" "Script failed at line $BASH_LINENO with code $exit_code."
        log "ERROR" "Please check the error messages above."
        echo "================================================================="
        exit "$exit_code"
    fi
    # Deactivate venv if it was activated
    if command -v deactivate &> /dev/null; then
        log "INFO" "Deactivating virtual environment..."
        deactivate
    fi
    echo ""
    log "SUCCESS" "SETUP COMPLETE"
    echo "================================================================="
}
trap cleanup_and_exit EXIT

# Check for debug flag
if [ "$DEBUG" = true ]; then
    set -x # Enable verbose tracing
    log "INFO" "Debug mode enabled (set -x)."
fi

echo "================================================================="
echo "Airflow/Kafka ETL Pipeline Environment Setup (BASH/Unix)"
echo "================================================================="
log "INFO" "Starting script execution."

# ----------------------------------------------------
# 1. PYTHON DETECTION
# ----------------------------------------------------
PYTHON_EXEC=""
OS="$(uname -s)"
log "INFO" "Attempting to find Python 3 executable on $OS..."

# Use 'where.exe' on Windows/MSYS2/Cygwin (most reliable)
if [[ "$OS" == "MINGW"* || "$OS" == "CYGWIN"* || "$OS" == "MSYS"* ]]; then
    PYTHON_CANDIDATE=$(where.exe python3.exe 2>/dev/null || where.exe python.exe 2>/dev/null)
    if [ -n "$PYTHON_CANDIDATE" ]; then
        # Take the first path found
        PYTHON_EXEC=$(echo "$PYTHON_CANDIDATE" | head -n 1)
    fi
# Use 'command -v' on Linux/macOS
else
    if command -v python3 &> /dev/null; then
        PYTHON_EXEC=$(command -v python3)
    elif command -v python &> /dev/null; then
        PYTHON_EXEC=$(command -v python)
    fi
fi

if [ -z "$PYTHON_EXEC" ]; then
    log "ERROR" "Python 3 not found."
    log "ERROR" "Please ensure 'python3', 'python', or 'python.exe' is installed and available in your PATH."
    exit 1
fi

log "SUCCESS" "Found Python executable: $PYTHON_EXEC"

# ----------------------------------------------------
# 2. VIRTUAL ENVIRONMENT
# ----------------------------------------------------
if [ -d "venv" ]; then
    log "INFO" "Virtual environment 'venv' already exists. Skipping creation."
else
    log "INFO" "Creating virtual environment 'venv'..."
    "$PYTHON_EXEC" -m venv venv
    log "SUCCESS" "Virtual environment created."
fi

log "INFO" "Activating virtual environment..."
# Activate depending on platform (using explicit paths for robustness)
if [[ "$OS" == "MINGW"* || "$OS" == "CYGWIN"* || "$OS" == "MSYS"* ]]; then
    VENV_ACTIVATE_SCRIPT="venv/Scripts/activate"
    # MSYS2/Git Bash usually requires sourcing with '.' or 'source'
    . "$VENV_ACTIVATE_SCRIPT"
    log "INFO" "Activated using Windows path: $VENV_ACTIVATE_SCRIPT"
else
    VENV_ACTIVATE_SCRIPT="venv/bin/activate"
    . "$VENV_ACTIVATE_SCRIPT"
    log "INFO" "Activated using Unix path: $VENV_ACTIVATE_SCRIPT"
fi

# ----------------------------------------------------
# 3. DEPENDENCIES (Skip if installed)
# ----------------------------------------------------
if [ -f "$INSTALL_FLAG_FILE" ]; then
    log "INFO" "Skipping dependency installation (flag file found)."
else
    log "INFO" "Installing dependencies from requirements.txt..."
    # Ensure pip is up-to-date and install dependencies
    pip install --upgrade pip
    pip install -r requirements.txt
    
    # Create the flag file upon successful installation
    touch "$INSTALL_FLAG_FILE"
    log "SUCCESS" "Dependencies installed and flag file created."
fi

# ----------------------------------------------------
# 4. AIRFLOW CONFIGURATION
# ----------------------------------------------------
log "INFO" "Initializing Airflow Configuration..."

# Ensure the Airflow HOME directory exists
mkdir -p "$AIRFLOW_HOME"
export AIRFLOW_HOME="$(pwd)/$AIRFLOW_HOME"
log "INFO" "Setting AIRFLOW_HOME to: $AIRFLOW_HOME"

# Airflow on Windows/SQLite requires absolute path with forward slashes
PROJECT_ROOT_ABS=$(pwd)
DB_PATH_URI="sqlite:///${PROJECT_ROOT_ABS}/${AIRFLOW_HOME}/airflow.db"
# Replace backslashes with forward slashes for SQLite URI format (critical on Windows)
DB_PATH_URI=$(echo "$DB_PATH_URI" | sed 's/\\/\//g')

export AIRFLOW__CORE__SQL_ALCHEMY_CONN="$DB_PATH_URI"
log "INFO" "Setting DB Connection (Fix): $AIRFLOW__CORE__SQL_ALCHEMY_CONN"

# Fix for "ModuleNotFoundError: No module named 'fcntl'" on Windows
export AIRFLOW__CORE__AUTH_MANAGER=""
log "INFO" "Disabling core auth manager to bypass fcntl error on non-POSIX systems."

# ----------------------------------------------------
# 5. AIRFLOW DATABASE & ADMIN USER
# ----------------------------------------------------
log "INFO" "Running 'airflow db migrate' to initialize database..."
airflow db migrate

log "INFO" "Creating default Airflow user 'admin'..."
# Use || true to prevent the script from failing if the user already exists on subsequent runs
airflow users create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com \
    --password admin || true

# ----------------------------------------------------
# 6. FINAL INSTRUCTIONS
# ----------------------------------------------------
echo ""
echo "================================================================="
log "SUCCESS" "SETUP COMPLETE"
echo "NEXT STEPS (CRITICAL):"
echo "1. Start Kafka services (using Docker or local installation)."
echo "2. Place your DAG (e.g., user_etl_dag.py) into the '$AIRFLOW_HOME/dags' folder."
echo "3. In two separate terminals (after ensuring venv is activated with 'source $VENV_ACTIVATE_SCRIPT'):"
echo "   > airflow webserver -p 8080"
echo "   > airflow scheduler"
echo "================================================================="
# The final exit is handled by the trap function