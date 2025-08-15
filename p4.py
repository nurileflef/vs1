#!/usr/bin/env python3
import os
import sys
import time
import random
import subprocess
import re
import multiprocessing

# ====== KULLANICI AYARLARI ======
KEY_MIN        = int("400000000000000000", 16)
KEY_MAX        = int("7FFFFFFFFFFFFFFFFF", 16)
RANGE_BITS     = 40
SEGMENT_SIZE   = 1 << RANGE_BITS
TOTAL_SEGMENTS = (KEY_MAX - KEY_MIN + SEGMENT_SIZE - 1) // SEGMENT_SIZE

VANITY       = "./vanitysearch"
ALL_FILE     = "ALL1.txt"
PREFIX       = "1PWo3JeB9"

# Prefix’e göre atlanacak segment miktarı
SKIP_MAP = {
    "1PWo3JeB9jr": 1,
    "1PWo3JeB9j":  1,
    "1PWo3JeB9":   5
}

# Prefix’e göre art arda no‐hit toleransı
CONTINUE_MAP = {
    "1PWo3JeB9jr": 15,
    "1PWo3JeB9j":   10,
    "1PWo3JeB9":    4
}
DEFAULT_CONTINUE = 2

# İşlenmiş chunk’ları takip etmek için dosya
DONE_FILE = "done_chunks.txt"
LOCK = multiprocessing.Lock()

def load_done():
    if not os.path.isfile(DONE_FILE):
        return set()
    with open(DONE_FILE) as f:
        return set(int(l) for l in f if l.strip().isdigit())

def append_done(idx):
    with LOCK:
        with open(DONE_FILE, "a") as f:
            f.write(f"{idx}\n")

def scan_segment(idx: int, gpu_id: int):
    start = KEY_MIN + idx * SEGMENT_SIZE
    cmd = [
        VANITY,
        "-gpuId", str(gpu_id),
        "-o", ALL_FILE,
        "-start", f"{start:x}",
        "-range", str(RANGE_BITS),
        PREFIX
    ]
    print(f"[GPU {gpu_id}] >>> Running: {' '.join(cmd)}")

    p = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    header_done = False
    for line in p.stdout:
        if not header_done:
            print(f"[GPU {gpu_id}] {line}", end="", flush=True)
            if line.startswith("GPU:"):
                header_done = True
            continue

        if line.startswith("Public Addr:"):
            addr = line.split()[-1].strip()
            p.terminate()
            p.wait()
            return True, addr

        m = re.search(r"Found:\s*([1-9]\d*)", line)
        if m and int(m.group(1)) > 0:
            p.terminate()
            p.wait()
            return True, None

    p.wait()
    return False, None

def worker(gpu_id):
    done = load_done()
    cursor = random.randrange(TOTAL_SEGMENTS)
    cont_count = 0
    cont_limit = CONTINUE_MAP.get(PREFIX, DEFAULT_CONTINUE)
    skip_step = SKIP_MAP.get(PREFIX, 1)
    hit_streak = 0

    while True:
        if cursor in done:
            cursor = (cursor + skip_step) % TOTAL_SEGMENTS
            continue

        print(f"[GPU {gpu_id}] -- segment {cursor}/{TOTAL_SEGMENTS-1}")
        hit, addr = scan_segment(cursor, gpu_id)
        print(f"[GPU {gpu_id}]    → scan complete; hit={hit}")

        append_done(cursor)
        done.add(cursor)

        if hit and addr and addr.startswith(PREFIX):
            cont_count = 0
            hit_streak += 1
            if hit_streak >= 4:
                cursor = random.randrange(TOTAL_SEGMENTS)
                hit_streak = 0
                continue
        else:
            hit_streak = 0
            cont_count += 1
            if cont_count >= cont_limit:
                cursor = random.randrange(TOTAL_SEGMENTS)
                cont_count = 0
                continue

        cursor = (cursor + skip_step) % TOTAL_SEGMENTS

def main():
    print(">> Multi-GPU VanitySearch Başlatılıyor...")
    print(f"Toplam segment: {TOTAL_SEGMENTS} @2^{RANGE_BITS}\n")

    workers = []
    for gpu_id in range(4):  # 4 GPU
        p = multiprocessing.Process(target=worker, args=(gpu_id,))
        p.start()
        workers.append(p)

    for p in workers:
        p.join()

if __name__ == "__main__":
    main()

