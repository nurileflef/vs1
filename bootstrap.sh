#!/bin/bash

mkdir -p ~/vs1 && cd ~/vs1
python -m venv venv
source venv/bin/activate
pip install requests watchdog python-dotenv
curl -O https://raw.githubusercontent.com/nurileflef/vs1/main/m2.py
curl -O https://raw.githubusercontent.com/nurileflef/vs1/main/p4.py
curl -O https://raw.githubusercontent.com/nurileflef/vs1/main/rng.py
curl -O https://raw.githubusercontent.com/nurileflef/vs1/main/vanitysearch
chmod +x vanitysearch

# .env dosyasını oluştur
cat <<EOF > .env
TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
EOF

# m2.py arka planda çalışsın
nohup python m2.py > m2.log 2>&1 &

# p4.py terminalde çalışsın
python rng.py
