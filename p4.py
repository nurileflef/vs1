#!/usr/bin/env python3
import secrets
import random
import subprocess
import re
import time
import threading

# ====== KULLANICI AYARLARI ======
KEY_MIN        = int("400000000000000000", 16)
KEY_MAX        = int("7FFFFFFFFFFFFFFFFF", 16)
RANGE_BITS     = 40
BLOCK_SIZE     = 1 << RANGE_BITS
KEYSPACE_LEN   = KEY_MAX - KEY_MIN + 1
MAX_OFFSET     = KEYSPACE_LEN - BLOCK_SIZE

VANITY         = "./vanitysearch"
ALL_FILE       = "ALL.txt"
PREFIX         = "1PWo3JeB"

CONTINUE_MAP = {
    "1PWo3JeB9jr": 100,
    "1PWo3JeB9j":   71,
    "1PWo3JeB9":     1,
    "1PWo3JeB":      1,
}
DEFAULT_CONTINUE = 1

# ====== SKIP WINDOW PARAMETRELERİ ======
SKIP_CYCLES    = 25
SKIP_BITS_MIN  = 62
SKIP_BITS_MAX  = 64

# ====== GPU ADEDİ ======
TOTAL_GPUS = 4

def random_start(gpu_id=0, total_gpus=1):
    low_blk  = KEY_MIN >> RANGE_BITS
    high_blk = KEY_MAX >> RANGE_BITS
    count    = high_blk - low_blk + 1

    # GPU'ya özel blok aralığı
    blocks_per_gpu = count // total_gpus
    blk_start = low_blk + gpu_id * blocks_per_gpu
    blk_end   = blk_start + blocks_per_gpu - 1

    blk_idx  = secrets.randbelow(blk_end - blk_start + 1) + blk_start
    start    = blk_idx << RANGE_BITS
    print(f">>> [GPU {gpu_id}] random_start → 0x{start:x} (block range: {blk_start}-{blk_end})")
    return start

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
            print(f"[GPU {gpu_id}]   !! public-hit: {addr}")
        if "Priv (HEX):" in line and hit:
            m = re.search(r"0x\s*([0-9A-Fa-f]+)", line)
            if m:
                priv = m.group(1).zfill(64)
                print(f"[GPU {gpu_id}]   >> privkey: {priv}")

    p.wait()
    return hit, addr, priv

def worker(gpu_id: int):
    sorted_pfx      = sorted(CONTINUE_MAP.keys(), key=lambda p: -len(p))
    start           = random_start(gpu_id=gpu_id, total_gpus=TOTAL_GPUS)
    scan_ct         = 0

    initial_window  = 0
    window_rem      = 0
    skip_rem        = 0
    last_main_start = 0

    print(f"\n→ GPU {gpu_id} başlatıldı. CTRL-C ile durdurabilirsiniz.\n")

    try:
        while True:
            if window_rem > 0:
                last_main_start = start
                hit, addr, priv = scan_at(start, gpu_id)
                scan_ct += 1

                if hit and priv:
                    matched = next((p for p in sorted_pfx if addr.startswith(p)), PREFIX)
                    new_win = CONTINUE_MAP.get(matched, DEFAULT_CONTINUE)
                    if new_win > initial_window:
                        initial_window = new_win
                        print(f"[GPU {gpu_id}]   >> nadir hit! window={initial_window}")

                window_rem -= 1
                print(f"[GPU {gpu_id}]   >> [MAIN WINDOW] {initial_window-window_rem}/{initial_window}")

                if window_rem > 0:
                    start = wrap_inc(start, BLOCK_SIZE)
                else:
                    skip_rem = SKIP_CYCLES
                    print(f"[GPU {gpu_id}]   >> MAIN WINDOW bitti → skip-window={SKIP_CYCLES}\n")
                continue

            if skip_rem > 0:
                bit_skip    = random.randrange(SKIP_BITS_MIN, SKIP_BITS_MAX+1)
                skip_amt    = 1 << bit_skip
                skip_start  = wrap_inc(last_main_start, skip_amt)
                start       = skip_start
                last_main_start = skip_start

                print(f"[GPU {gpu_id}]   >> [SKIP WINDOW] "
                      f"{SKIP_CYCLES-skip_rem+1}/{SKIP_CYCLES}: "
                      f"{bit_skip}-bit skip → 0x{start:x}")

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
                    print(f"[GPU {gpu_id}]   >> SKIP-HIT! matched={matched}, window={initial_window}\n")
                else:
                    skip_rem -= 1
                    if skip_rem == 0:
                        start = random_start(gpu_id=gpu_id, total_gpus=TOTAL_GPUS)
                        print(f"[GPU {gpu_id}]   >> SKIP WINDOW no-hit→ random_start\n")
                continue

            for _ in range(DEFAULT_CONTINUE):
                hit, addr, priv = scan_at(start, gpu_id)
                scan_ct += 1
                if hit and priv:
                    matched        = next((p for p in sorted_pfx if addr.startswith(p)), PREFIX)
                    initial_window = CONTINUE_MAP.get(matched, DEFAULT_CONTINUE)
                    window_rem     = initial_window
                    start          = wrap_inc(start, BLOCK_SIZE)
                    print(f"[GPU {gpu_id}]   >> SEQ-HIT! matched={matched}, window={initial_window}\n")
                    break
                else:
                    start = wrap_inc(start, BLOCK_SIZE)
            else:
                start = random_start(gpu_id=gpu_id, total_gpus=TOTAL_GPUS)

            if scan_ct % 10 == 0:
                print(f"[GPU {gpu_id}] [STATUS] scans={scan_ct}, next=0x{start:x}")

    except KeyboardInterrupt:
        print(f"\n>> GPU {gpu_id} durduruldu.")

def main():
    threads = []
    for gpu_id in [0, 1, 2, 3]:
        t = threading.Thread(target=worker, args=(gpu_id,), daemon=True)
        threads.append(t)
        t.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n>> Tüm GPU işlemleri durduruluyor...")

if __name__ == "__main__":
    main()





