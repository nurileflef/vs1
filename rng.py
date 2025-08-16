import subprocess
import time
import threading
import random

# ========== Ayarlar ==========

VANITYSEARCH_BIN = "./vanitysearch"
TARGET_PATTERN = "1PWo3JeB9"
RANGE_HEX = 1 << 38  # 2^38
LOOP_DELAY = 0.5  # saniye

STEP_SIZE_HEX = "174576E38EF57B51C"  # base step
OUTPUT_FILE = "ALL1.txt"

WINDOW_LIMIT = 3  # hit sonrası kaç ardışık blok taransın

# GPU aralıkları (start, end)
GPU_RANGES = {
    0: ("400000000000000000", "4FFFFFFFFFFFFFFFFF"),
    1: ("500000000000000000", "5FFFFFFFFFFFFFFFFF"),
    2: ("600000000000000000", "6FFFFFFFFFFFFFFFFF"),
    3: ("700000000000000000", "7FFFFFFFFFFFFFFFFF"),
}

# ========== Yardımcı Fonksiyonlar ==========

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def generate_random_step(base_step_dec):
    variance = int(base_step_dec * 0.2)
    return random.randint(base_step_dec - variance, base_step_dec + variance)

def generate_start_near_range_start(range_start_dec, base_step_dec):
    offset = random.randint(0, base_step_dec)
    return range_start_dec + offset

# ========== GPU Worker ==========

def gpu_worker(gpu_id, start_hex, end_hex):
    range_start = int(start_hex, 16)
    range_end   = int(end_hex, 16)
    base_step   = int(STEP_SIZE_HEX, 16)

    window_mode  = False
    window_count = 0
    current      = None

    while True:
        # STEP belirle
        step_size = RANGE_HEX if window_mode else generate_random_step(base_step)
        step_hex  = f"{step_size:X}"

        # START belirle
        if window_mode and current:
            start = current
        else:
            start = generate_start_near_range_start(range_start, base_step)

        log(f"[GPU {gpu_id}] STEP: {step_hex} | START: {start:016X}")
        current   = start
        iteration = 0

        while current + RANGE_HEX <= range_end:
            start_hex_str = f"{current:016X}"
            log(f"[GPU {gpu_id} | Iter {iteration}] start={start_hex_str}")

            cmd = [
                VANITYSEARCH_BIN,
                "-gpuId", str(gpu_id),
                "-o", OUTPUT_FILE,
                "-start", start_hex_str,
                "-range", "40",
                TARGET_PATTERN
            ]

            try:
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as e:
                log(f"[GPU {gpu_id}] ERROR: {e}")

            # Hit kontrolü
            try:
                with open(OUTPUT_FILE) as f:
                    for line in f:
                        if line.startswith("Public Addr:") and TARGET_PATTERN in line:
                            log(f"[GPU {gpu_id}] HIT DETECTED: {line.strip()}")
                            window_mode  = True
                            window_count = 0
                            break
            except Exception as e:
                log(f"[GPU {gpu_id}] File Read Error: {e}")

            # Window modundaysak sayaç artır
            if window_mode:
                window_count += 1
                if window_count >= WINDOW_LIMIT:
                    log(f"[GPU {gpu_id}] Window tamamlandı. Random moda dönülüyor.")
                    window_mode = False

            current += step_size
            iteration += 1
            time.sleep(LOOP_DELAY)

        log(f"[GPU {gpu_id}] Aralık bitti. Yeni random step + start ile tekrar başlıyoruz...\n")

# ========== Ana Fonksiyon ==========

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
