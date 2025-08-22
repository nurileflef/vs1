#!/usr/bin/env bash
set -e

# 1. cuda
yes | apt-get update
yes | apt-get install nvidia-cuda-toolkit

# 2. Python 
pip install watchdog python-dotenv

# 3. clone
curl -fsSL -O https://raw.githubusercontent.com/nurileflef/vs1/main/m2.py
curl -fsSL -O https://raw.githubusercontent.com/nurileflef/vs1/main/p4.py
curl -fsSL -O https://raw.githubusercontent.com/nurileflef/vs1/main/vanitysearch
chmod +x vanitysearch

# 4. .env 
cat <<EOF > .env
TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
EOF

# 5. tg
nohup python m2.py > m2.log 2>&1 &

# 6. main
python p4.py
