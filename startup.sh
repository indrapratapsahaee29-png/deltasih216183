#!/bin/sh
set -eu
cd /workspace

if curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8080/api/health; then
  exit 0
fi

cd /workspace/nearestexchange/backend
if [ ! -d venv ]; then
  python3 -m venv venv
fi
./venv/bin/python -m pip install --upgrade pip >/dev/null
./venv/bin/python -m pip install -q -r requirements.txt
PORT=8080 HOST=0.0.0.0 ./venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8080 >>/tmp/app-startup.log 2>&1 &
