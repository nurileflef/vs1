import random
import subprocess
import signal
import sys

# Hex aralıkları
start_min = int("400000000000000000", 16)
start_max = int("7FFFFFFFFFFFFFFFFF", 16)

# GPU ID'leri
gpu_ids = [0, 1, 2, 3]

# Komut şablonu
base_command = "./vanitysearch -gpuId {gpu} -o ALL{gpu}.txt -start {start} -range 65 -random 1PWo3JeB9"

# Alt işlemleri burada tutacağız
processes = []

def signal_handler(sig, frame):
    print("\nCtrl+C algılandı. Alt işlemler durduruluyor...")
    for p in processes:
        try:
            p.terminate()
            p.wait(timeout=5)
            print(f"PID {p.pid} durduruldu.")
        except Exception as e:
            print(f"PID {p.pid} durdurulamadı: {e}")
    sys.exit(0)

# Ctrl+C sinyalini yakala
signal.signal(signal.SIGINT, signal_handler)

# Her GPU için komutu oluştur ve çalıştır
for gpu in gpu_ids:
    random_start = hex(random.randint(start_min, start_max))[2:].upper()
    command = base_command.format(gpu=gpu, start=random_start)
    print(f"Başlatılıyor: {command}")
    p = subprocess.Popen(command, shell=True)
    processes.append(p)

# Ana thread beklemede kalmalı
for p in processes:
    p.wait()
