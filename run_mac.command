#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ ! -f ".env" ]; then
  cp judge-demo.env.example .env
  echo "Golden 데모용 안전 설정(.env)을 준비했습니다."
fi
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
