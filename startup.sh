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

# Install Google Chrome for Kaleido PNG export (choreographer backend requires Chrome, not Chromium)
if ! command -v google-chrome &> /dev/null && ! command -v google-chrome-stable &> /dev/null; then
    echo ">>> Installing Google Chrome for Kaleido chart export..."
    apt-get update -qq
    # Add Google Chrome repository
    curl -fsSL https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list
    apt-get update -qq
    apt-get install -y --no-install-recommends google-chrome-stable
    echo ">>> Google Chrome installed."
else
    echo ">>> Google Chrome already present."
fi

echo ">>> Starting application..."
exec python main.py
