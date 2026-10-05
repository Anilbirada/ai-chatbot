#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ ! -f ".venv/bin/python" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if [ ! -f ".env" ]; then
  cp .env.example .env
fi
python app.py
