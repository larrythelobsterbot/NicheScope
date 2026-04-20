#!/bin/bash
# Wrapper script for the NicheScope scheduler.
# Loads environment variables from .env before starting Python.
cd /home/muffinman/NicheScope/collectors

# Source the .env file if it exists
if [ -f /home/muffinman/NicheScope/.env ]; then
    set -a
    source /home/muffinman/NicheScope/.env
    set +a
fi

exec /home/muffinman/NicheScope/collectors/venv/bin/python scheduler.py
