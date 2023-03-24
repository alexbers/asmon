#!/bin/sh

#mkdir -p db

chown asmon:asmon /home/asmon/config.py
#chmod o-w db

export PYTHONUNBUFFERED=1

exec su -c "python3 asmon.py" asmon
