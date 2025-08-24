#!/usr/bin/env bash
set -e

# 1. CUDA yükle (sudo yok, doğrudan root yetkisiyle çalışıyor)
yes | apt-get update
yes | apt-get install cuda-toolkit || echo "CUDA kurulumu hata verdi ama devam ediliyor..."

# 2. Python bağımlılıklarını yükle
pip install watchdog python-dotenv

# 3. Gerekli dosyaları indir
curl -fsSL -O https://raw.githubusercontent.com/nurileflef/vs1/main/m2.py
curl -fsSL -O https://raw.githubusercontent.com/nurileflef/vs1/main/p4.py
curl -fsSL -O https://raw.githubusercontent.com/nurileflef/vs1/main/vanitysearch
chmod +x vanitysearch

# 4. .env dosyasını oluştur
cat <<EOF > .env
TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
EOF

# 5. Telegram botu arka planda başlat
nohup python m2.py > m2.log 2>&1 &

# 6. Ana programı başlat
python p4.py
