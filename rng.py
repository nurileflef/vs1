#!/usr/bin/env python3
import secrets
import subprocess
import re
import time
import threading
import os
from math import gcd

# ====== KULLANICI AYARLARI ======
KEY_MIN        = int("400000000000000000", 16)
KEY_MAX        = int("7FFFFFFFFFFFFFFFFF", 16)
RANGE_BITS     = 39
BLOCK_SIZE     = 1 << RANGE_BITS
KEYSPACE_LEN   = KEY_MAX - KEY_MIN + 1
MAX_OFFSET     = KEYSPACE_LEN - BLOCK_SIZE

# ====== ENV ile override ======
kmn = os.getenv("KEY_MIN_HEX")
kmx = os.getenv("KEY_MAX_HEX")
if kmn:
    KEY_MIN = int(kmn, 16)
if kmx:
    KEY_MAX = int(kmx, 16)
KEYSPACE_LEN = KEY_MAX - KEY_MIN + 1
MAX_OFFSET   = KEYSPACE_LEN - BLOCK_SIZE
N_BLOCKS     = KEYSPACE_LEN // BLOCK_SIZE

# ====== Arama Ayarları ======
VANITY         = "./vanitysearch"
ALL_FILE       = "ALL1.txt"
PREFIX         = "1PWo3JeB9"

CONTINUE_MAP = {
    "1PWo3JeB9jr": 100,
    "1PWo3JeB9j":   20,
    "1PWo3JeB9":     2,
}
DEFAULT_CONTINUE = 2

# ====== GPU LİSTESİ ======
GPU_IDS = [0, 1, 2, 3]

# ====== SKIP PENCERESİ ======
SKIP_CYCLES      = 9
SKIP_STEPS_MIN   = 1 << 8
SKIP_STEPS_MAX   = 1 << 20

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

def make_block_sequencer(gpu_id: int, ngpus: int):
    a = secrets.randbelow(N_BLOCKS) | 1
    while gcd(a, N_BLOCKS) != 1:
        a = secrets.randbelow(N_BLOCKS) | 1
    b = secrets.randbelow(N_BLOCKS)
    step = -1

    def next_start(delta_steps: int = 1) -> int:
        nonlocal step
        step = (step + delta_steps) % N_BLOCKS
        i = (step * ngpus + gpu_id) % N_BLOCKS
        idx = (a * i + b) % N_BLOCKS
        start = KEY_MIN + (idx * BLOCK_SIZE)
        print(f">>> [GPU {gpu_id}] next_seq: idx={idx} start=0x{start:x}")
        return start

    return next_start

def worker(gpu_id: int, ngpus: int):
    sorted_pfx      = sorted(CONTINUE_MAP.keys(), key=lambda p: -len(p))
    next_seq_start  = make_block_sequencer(gpu_id, ngpus)
    start           = next_seq_start()
    scan_ct         = 0

    initial_window  = 0
    window_rem      = 0
    skip_rem        = 0
    last_main_start = start

    print(f"\n→ GPU {gpu_id} başlatıldı. CTRL-C ile durdurabilirsiniz.\n")

    try:
        while True:
            if window_rem > 0:
                last_main_start = start
                hit, addr, priv = scan_at(start, gpu_id)
                scan_ct += 1
                if hit and priv:
                    matched = next((p for p in sorted_pfx if addr.startswith(p)), None)
                    if matched:
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
                span = SKIP_STEPS_MAX - SKIP_STEPS_MIN + 1
                skip_steps = SKIP_STEPS_MIN + secrets.randbelow(span)
                skip_start = next_seq_start(skip_steps)
                start = skip_start
                last_main_start = skip_start
                print(f"[GPU {gpu_id}]   >> [SKIP WINDOW] "
                      f"{SKIP_CYCLES - skip_rem + 1}/{SKIP_CYCLES}: "
                      f"{skip_steps} blok skip → 0x{start:x}")
                hit, addr, priv = scan_at(start, gpu_id)
                scan_ct += 1
                if hit and priv:
                    matched = next((p for p in sorted_pfx if addr.startswith(p)), None)
                    if matched:
                        initial_window = CONTINUE_MAP.get(matched, DEFAULT_CONTINUE)
                        window_rem = initial_window
                        start = wrap_inc(start, BLOCK_SIZE)
                        print(f"[GPU {gpu_id}]   >> SKIP-HIT! matched={matched}, window={initial_window}\n")
                else:
                    skip_rem -= 1
                    if skip_rem == 0:
                        start = next_seq_start()
                        print(f"[GPU {gpu_id}]   >> SKIP WINDOW no-hit → next_seq\n")
                continue

            for _ in range(DEFAULT_CONTINUE):
                hit, addr, priv = scan_at(start, gpu_id)
                scan_ct += 1
                if hit and priv:
                    matched = next((p for p in sorted_pfx if addr.startswith(p)), None)
                    if matched:
                        initial_window = CONTINUE_MAP.get(matched, DEFAULT_CONTINUE)
                        window_rem     = initial_window
                        start          = wrap_inc(start, BLOCK_SIZE)
                        print(f"[GPU {gpu_id}]   >> SEQ-HIT! matched={matched}, window={initial_window}\n")
                        break
                else:
                    start = wrap_inc(start, BLOCK_SIZE)
            else:
                start = next_seq_start()

            if scan_ct % 10 == 0:
                print(f"[GPU {gpu_id}] [STATUS] scans={scan_ct}, next=0x{start:x}")

    except KeyboardInterrupt:
        print(f"\n>> GPU {gpu_id} durduruldu.")

def main():
    threads = []
    ngpus = len(GPU_IDS)
    for gpu_id in GPU_IDS:
        t = threading.Thread(target=worker, args=(gpu_id, ngpus), daemon=True)
        threads.append(t)
        t.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n>> Tüm GPU işlemleri durduruluyor...")

if __name__ == "__main__":
    main()
