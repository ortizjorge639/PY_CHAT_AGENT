#!/bin/bash
# ─────────────────────────────────────────────────────────────
# App Service startup script
# Installs the Microsoft ODBC Driver 18 for SQL Server, then
# launches the Python application.
# ─────────────────────────────────────────────────────────────
set -e

# Only install if the driver isn't already present
if ! odbcinst -q -d 2>/dev/null | grep -qi "ODBC Driver 18"; then
    echo ">>> Installing ODBC Driver 18 for SQL Server..."
    apt-get update -qq
    ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
        curl apt-transport-https gnupg

    # Add Microsoft package repo (Debian 11 / Bullseye — matches App Service image)
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | apt-key add -
    curl -fsSL https://packages.microsoft.com/config/debian/11/prod.list \
        > /etc/apt/sources.list.d/mssql-release.list

    apt-get update -qq
    ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18
    echo ">>> ODBC Driver 18 installed."
else
    echo ">>> ODBC Driver 18 already present."
fi

echo ">>> Starting application..."
exec python main_test.py
