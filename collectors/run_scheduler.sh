#!/bin/bash
# Wrapper script for the NicheScope scheduler.
# Loads environment variables from .env before starting Python.
cd /opt/nichescope/collectors

# Source the .env file if it exists
if [ -f /opt/nichescope/.env ]; then
    set -a
    source /opt/nichescope/.env
    set +a
fi

exec python3 scheduler.py
