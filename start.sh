#!/bin/sh

chown asmon:asmon /home/asmon/config.py

export PYTHONUNBUFFERED=1

exec su -c "python3 asmon.py" asmon
