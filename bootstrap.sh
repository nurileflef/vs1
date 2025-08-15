#!/usr/bin/env bash
set -e

# 1. Çalışma dizini ve sanal ortam
mkdir -p ~/vs1 && cd ~/vs1
python3 -m venv venv
source venv/bin/activate

# 2. Gerekli paketler
pip install requests watchdog python-dotenv

# 3. DRBG modülünü oluştur (UUID destekli, her çalıştırmada farklı seed)
cat << 'EOF' > user_drbg.py
import os, time, hmac, hashlib, struct, uuid

_meta = os.getenv("HOSTNAME", "")

def _collect_jitter(samples=256):
    data = bytearray()
    for _ in range(samples):
        t1 = time.perf_counter_ns()
        time.sleep(0)
        t2 = time.perf_counter_ns()
        data += struct.pack(">Q", t2 - t1)
    return bytes(data)

_rnd = os.urandom(32)
_once_uuid = uuid.uuid4().bytes

_seed_material = _meta.encode() + _collect_jitter() + _rnd + _once_uuid
_seed = hmac.new(b"bootstrap-drbg", _seed_material, hashlib.sha256).digest()
_counter = 0

def randbelow(n):
    global _seed, _counter
    out = b""
    byte_len = (n.bit_length() + 7) // 8
    while len(out) < byte_len:
        ctr = struct.pack(">Q", _counter)
        out += hmac.new(_seed, ctr, hashlib.sha256).digest()
        _counter += 1
    return int.from_bytes(out[:byte_len], "big") % n
EOF

# 4. Script’leri indir
curl -fsSL -O https://raw.githubusercontent.com/nurileflef/vs1/main/m2.py
curl -fsSL -O https://raw.githubusercontent.com/nurileflef/vs1/main/p4.py
curl -fsSL -O https://raw.githubusercontent.com/nurileflef/vs1/main/rng.py
curl -fsSL -O https://raw.githubusercontent.com/nurileflef/vs1/main/vanitysearch
chmod +x vanitysearch

# 5. secrets.randbelow()’ı DRBG ile override et
for pyf in m2.py rng.py; do
  sed -i '1iimport user_drbg, secrets\nsecrets.randbelow = user_drbg.randbelow\n' "$pyf"
done

# 6. .env dosyası
cat <<EOF > .env
TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
EOF

# 7. Uygulamayı başlat
nohup python m2.py > m2.log 2>&1 &
python rng.py
