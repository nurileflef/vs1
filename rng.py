#!/usr/bin/env python3
import secrets
import random
import subprocess
import re
import time
import sys
import errno
import os
from multiprocessing import Process, Manager

# ======== GÜVENLİ PRINT WRAPPER ========
original_print = print
def print(*args, **kwargs):
    try:
        original_print(*args, **kwargs)
    except IOError as e:
        if getattr(e, "errno", None) != errno.EAGAIN:
            raise

# ====== KULLANICI AYARLARI ======
KEY_MIN        = int("400000000000000000", 16)
KEY_MAX        = int("7FFFFFFFFFFFFFFFFF", 16)
RANGE_BITS     = 38
BLOCK_SIZE     = 1 << RANGE_BITS
KEYSPACE_LEN   = KEY_MAX - KEY_MIN + 1
MAX_OFFSET     = KEYSPACE_LEN - BLOCK_SIZE

VANITY         = "./vanitysearch"
ALL_FILE       = "ALL1.txt"
PREFIX         = "1PWo3JeB9"

CONTINUE_MAP = {
    "1PWo3JeB9jr": 75,
    "1PWo3JeB9j":  25,
    "1PWo3JeB9":   10,
    "1PWo3JeB":    1,
}
DEFAULT_CONTINUE = 3

# ====== SKIP WINDOW PARAMETRELERİ ======
SKIP_CYCLES    = 20
SKIP_BITS_MIN  = 55
SKIP_BITS_MAX  = 64

# ==============================================================================
# RASTGELE BAŞLANGIÇ FONKSİYONLARI
# ==============================================================================
def random_start():
    random_offset = secrets.randbelow(KEYSPACE_LEN)
    random_key = KEY_MIN + random_offset
    block_mask = ~((1 << RANGE_BITS) - 1)
    start = random_key & block_mask
    if start < KEY_MIN:
        start = KEY_MIN
    print(f">>> random_start → start=0x{start:x}")
    return start

def random_start_unique(gpu_id: int, used_starts):
    """Tamamen random, entropy + seed ile benzersiz start"""
    while True:
        # 16 hanelik hex seed
        extra_seed = secrets.token_hex(8)
        # Entropy: urandom + zaman + pid + gpu_id + extra_seed'in int değeri
        entropy_val = int.from_bytes(os.urandom(8), 'big') \
                      ^ time.time_ns() \
                      ^ (os.getpid() << 16) \
                      ^ (gpu_id << 8) \
                      ^ int(extra_seed, 16)
        random.seed(entropy_val)
        candidate = random_start()
        if candidate not in used_starts:
            used_starts.append(candidate)
            print(f"[GPU {gpu_id}] seed={extra_seed}")
            return candidate

# ==============================================================================
# YARDIMCI FONKSİYONLAR
# ==============================================================================
def wrap_inc(start: int, inc: int) -> int:
    off = (start - KEY_MIN + inc) % (MAX_OFFSET + 1)
    return KEY_MIN + off

def scan_at(start: int, gpu_id: int):
    sh = f"{start:x}"
    print(f">>> [GPU {gpu_id}] scan start=0x{sh}")
    p = subprocess.Popen(
        [VANITY, "-gpuId", str(gpu_id), "-o", ALL_FILE,
         "-start", sh, "-range", str(RANGE_BITS), PREFIX],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1
    )
    header_done = False
    hit = False
    addr = priv = None

    for line in p.stdout:
        if not header_done:
            print(line, end="", flush=True)
            if line.startswith("GPU:"):
                header_done = True
            continue

        if line.startswith("Public Addr:"):
            hit, addr = True, line.split()[-1].strip()
            print(f"    !! public-hit: {addr}")

        if "Priv (HEX):" in line and hit:
            m = re.search(r"0x\s*([0-9A-Fa-f]+)", line)
            if m:
                priv = m.group(1).zfill(64)
                print(f"    >> privkey: {priv}")

    p.wait()
    return hit, addr, priv

# ==============================================================================
# WORKER
# ==============================================================================
def worker(gpu_id: int, gpu_count: int, used_starts):
    sorted_pfx      = sorted(CONTINUE_MAP.keys(), key=lambda p: -len(p))
    start           = random_start_unique(gpu_id, used_starts)
    scan_ct         = 0
    initial_window  = 0
    window_rem      = 0
    skip_rem        = 0
    last_main_start = 0

    print(f"\n→ [GPU {gpu_id}] Başlatıldı. CTRL-C ile durdurabilirsiniz\n")

    try:
        while True:
            # ====== MAIN WINDOW ======
            if window_rem > 0:
                last_main_start = start
                hit, addr, priv = scan_at(start, gpu_id)
                scan_ct += 1

                if hit and priv:
                    matched = next((p for p in sorted_pfx if addr.startswith(p)), PREFIX)
                    new_win = CONTINUE_MAP.get(matched, DEFAULT_CONTINUE)
                    if new_win > initial_window:
                        initial_window = new_win
                        print(f"    >> [GPU {gpu_id}] nadir hit! window={initial_window}")

                window_rem -= 1
                if window_rem > 0:
                    start = wrap_inc(start, BLOCK_SIZE)
                else:
                    skip_rem = SKIP_CYCLES
                continue

            # ====== SKIP WINDOW ======
            if skip_rem > 0:
                bit_skip    = random.randrange(SKIP_BITS_MIN, SKIP_BITS_MAX+1)
                skip_amt    = 1 << bit_skip
                skip_start  = wrap_inc(last_main_start, skip_amt)
                start       = skip_start
                last_main_start = skip_start
                hit, addr, priv = scan_at(start, gpu_id)
                scan_ct += 1

                if hit and priv:
                    matched = next((p for p in sorted_pfx if addr.startswith(p)), PREFIX)
                    new_win = CONTINUE_MAP.get(matched, DEFAULT_CONTINUE)
                    if new_win > initial_window:
                        initial_window = new_win
                    window_rem = initial_window
                    skip_rem   = SKIP_CYCLES
                    start      = wrap_inc(start, BLOCK_SIZE)
                else:
                    skip_rem -= 1
                    if skip_rem == 0:
                        start = random_start_unique(gpu_id, used_starts)
                continue

            # ====== DEFAULT CONTINUE ======
            for _ in range(DEFAULT_CONTINUE):
                hit, addr, priv = scan_at(start, gpu_id)
                scan_ct += 1
                if hit and priv:
                    matched      = next((p for p in sorted_pfx if addr.startswith(p)), PREFIX)
                    initial_window = CONTINUE_MAP.get(matched, DEFAULT_CONTINUE)
                    window_rem     = initial_window
                    start          = wrap_inc(start, BLOCK_SIZE)
                    break
                else:
                    start = wrap_inc(start, BLOCK_SIZE)
            else:
                start = random_start_unique(gpu_id, used_starts)

            if scan_ct % 10 == 0:
                print(f"[GPU {gpu_id} STATUS] scans={scan_ct}, next=0x{start:x}")

    except KeyboardInterrupt:
        print(f"\n>> [GPU {gpu_id}] Çıkıyor...")

# ==============================================================================
# MAIN
# ==============================================================================
def main():
    gpu_count = 4
    manager = Manager()
    used_starts = manager.list()
    workers = []
    for gpu_id in range(gpu_count):
        p = Process(target=worker, args=(gpu_id, gpu_count, used_starts))
        p.start()
        workers.append(p)
    for p in workers:
        p.join()

if __name__ == "__main__":
    main()
