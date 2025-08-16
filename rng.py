import subprocess
import time
import threading
import random

# ========== AYARLAR ==========

VANITYSEARCH_BIN = "./vanitysearch"
TARGET_PATTERN = "1PWo3JeB9"
RANGE_HEX = 1 << 38  # 2^37
LOOP_DELAY = 0.5  # saniye

# Ortalama step büyüklüğü → random üretim bu değere göre olacak
STEP_SIZE_HEX = "17576E8EF7B512C"  # örn: ~4.5 TB
OUTPUT_FILE = "ALL1.txt"  # <<< TEK DOSYA >>>

# GPU Aralıkları (start, end)
GPU_RANGES = {
    0: ("400000000000000000", "4FFFFFFFFFFFFFFFFF"),
    1: ("500000000000000000", "5FFFFFFFFFFFFFFFFF"),
    2: ("600000000000000000", "6FFFFFFFFFFFFFFFFF"),
    3: ("700000000000000000", "7FFFFFFFFFFFFFFFFF"),
}

# =========================================

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def generate_random_step(base_step_dec):
    """Verilen base step (int) çevresinde ±%20 varyansla random step üretir"""
    variance = int(base_step_dec * 0.2)
    return random.randint(base_step_dec - variance, base_step_dec + variance)

def generate_start_near_range_start(range_start_dec, base_step_dec):
    """
    Start, aralığın başına yakın olacak şekilde random offset ile belirlenir.
    Offset büyüklüğü base_step_dec civarında seçildi.
    """
    max_offset = base_step_dec  # Offset aralığını step büyüklüğüne göre ayarlıyoruz
    offset = random.randint(0, max_offset)
    return range_start_dec + offset

def gpu_worker(gpu_id, start_hex, end_hex):
    range_start = int(start_hex, 16)
    range_end = int(end_hex, 16)
    base_step = int(STEP_SIZE_HEX, 16)

    while True:
        # Yeni random step oluştur
        step_size = generate_random_step(base_step)
        step_hex = f"{step_size:X}"

        # Başlangıç aralığın başına yakın olacak şekilde random offset ile belirleniyor
        start = generate_start_near_range_start(range_start, base_step)

        log(f"[GPU {gpu_id}] New STEP: {step_hex} | START: {start:016X}")
        current = start
        iteration = 0

        while current + RANGE_HEX <= range_end:
            start_hex_str = f"{current:016X}"

            log(f"[GPU {gpu_id} | Iter {iteration}] start={start_hex_str}")

            cmd = [
                VANITYSEARCH_BIN,
                "-gpuId", str(gpu_id),
                "-o", OUTPUT_FILE,
                "-start", start_hex_str,
                "-range", "37",
                TARGET_PATTERN
            ]

            try:
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as e:
                log(f"[GPU {gpu_id}] ERROR: {e}")

            current += step_size
            iteration += 1
            time.sleep(LOOP_DELAY)

        log(f"[GPU {gpu_id}] Aralık bitti. Yeni random step + start ile tekrar başlıyoruz...\n")

def main():
    threads = []
    for gpu_id, (start_hex, end_hex) in GPU_RANGES.items():
        t = threading.Thread(target=gpu_worker, args=(gpu_id, start_hex, end_hex))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

if __name__ == "__main__":
    main()
