#!/usr/bin/env python3
import subprocess
import time
import threading
import random

# ========== AYARLAR ==========

VANITYSEARCH_BIN = "./vanitysearch"
TARGET_PATTERN   = "1PWo3JeB9"
RANGE_BITS       = 38
BLOCK_SIZE       = 1 << RANGE_BITS      # 2^38
LOOP_DELAY       = 0.5                  # saniye

# Ortalama step büyüklüğü → random üretim bu değere göre olacak
STEP_SIZE_HEX    = "11757126E8EF7B512"  # ~ortalama adım
BASE_STEP        = int(STEP_SIZE_HEX, 16)

OUTPUT_FILE      = "ALL1.txt"            # <<< TEK DOSYA >>>

# GPU Aralıkları (start, end)
GPU_RANGES = {
    0: ("400000000000000000", "4FFFFFFFFFFFFFFFFF"),
    1: ("500000000000000000", "5FFFFFFFFFFFFFFFFF"),
    2: ("600000000000000000", "6FFFFFFFFFFFFFFFFF"),
    3: ("700000000000000000", "7FFFFFFFFFFFFFFFFF"),
}


# ========== YARDIMCI FONKSİYONLAR ==========

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def generate_random_step(base_step_dec):
    """BASE_STEP etrafında ±%20 varyansla random step üretir."""
    var = int(base_step_dec * 0.2)
    return random.randint(base_step_dec - var, base_step_dec + var)


def generate_start_near_range_start(range_start_dec, base_step_dec):
    """
    Start, aralığın başına yakın olacak şekilde random offset ile belirlenir.
    Offset büyüklüğü base_step_dec civarında seçilir.
    """
    offset = random.randint(0, base_step_dec)
    return range_start_dec + offset


# ========== GPU WORKER ==========

def gpu_worker(gpu_id, start_hex, end_hex):
    range_start = int(start_hex, 16)
    range_end   = int(end_hex, 16)

    while True:
        # 1) Adım büyüklüğünü ve raw start'ı üret
        step_size = generate_random_step(BASE_STEP)
        raw_start = generate_start_near_range_start(range_start, BASE_STEP)

        # 2) Başlangıcı BLOCK_SIZE ile hizala, ama current'ta raw kullan
        aligned_start = (raw_start // BLOCK_SIZE) * BLOCK_SIZE
        current       = raw_start

        log(f"[GPU {gpu_id}] New STEP={(step_size):X} | "
            f"Aligned START=0x{aligned_start:016X}")

        iteration = 0
        # 3) Aynı mantıkla taramaya devam et
        while True:
            # blok sınırını aşarsa çık
            if aligned_start + BLOCK_SIZE > range_end:
                break

            start_hex_str = f"{aligned_start:016X}"
            log(f"[GPU {gpu_id} | Iter {iteration}] start={start_hex_str}")

            cmd = [
                VANITYSEARCH_BIN,
                "-gpuId", str(gpu_id),
                "-o", OUTPUT_FILE,
                "-start", start_hex_str,
                "-range", str(RANGE_BITS),
                TARGET_PATTERN
            ]

            try:
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as e:
                log(f"[GPU {gpu_id}] ERROR: {e}")

            # 4) bir sonraki raw offset'e geç, sonra hizala
            current       += step_size
            aligned_start = (current // BLOCK_SIZE) * BLOCK_SIZE

            iteration     += 1
            time.sleep(LOOP_DELAY)

        log(f"[GPU {gpu_id}] Aralık bitti. Yeni STEP + START ile yeniden başlıyoruz...\n")


# ========== ANA ==========

def main():
    threads = []
    for gpu_id, (s_hex, e_hex) in GPU_RANGES.items():
        t = threading.Thread(
            target=gpu_worker,
            args=(gpu_id, s_hex, e_hex),
            daemon=True
        )
        t.start()
        threads.append(t)

    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
