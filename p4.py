#!/usr/bin/env python3
import secrets, random, subprocess, re, time, multiprocessing as mp, signal

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

GPU_IDS        = [0, 1, 2, 3]   # 4 GPU
N_GPUS         = len(GPU_IDS)
STRIDE         = N_GPUS * BLOCK_SIZE

CONTINUE_MAP = {
    "1PWo3JeB9jr": 100,
    "1PWo3JeB9j":   71,
    "1PWo3JeB9":     3,
    "1PWo3JeB":      1,
}
DEFAULT_CONTINUE = 3

SKIP_CYCLES    = 25
SKIP_BITS_MIN  = 40
SKIP_BITS_MAX  = 64

def log(lock, gpu_id: int, msg: str):
    with lock:
        print(f"[GPU{gpu_id}] {msg}", flush=True)

def random_start_for_gpu(gpu_id: int) -> int:
    low_blk  = KEY_MIN >> RANGE_BITS
    high_blk = KEY_MAX >> RANGE_BITS
    first_offset = (gpu_id - (low_blk % N_GPUS)) % N_GPUS
    first_blk    = low_blk + first_offset
    if first_blk > high_blk:
        blk_idx = low_blk
    else:
        total = ((high_blk - first_blk) // N_GPUS) + 1
        r     = secrets.randbelow(total)
        blk_idx = first_blk + r * N_GPUS
    return blk_idx << RANGE_BITS

def wrap_inc(start: int, inc: int) -> int:
    off = (start - KEY_MIN + inc) % (MAX_OFFSET + 1)
    return KEY_MIN + off

def align_to_stride(inc: int) -> int:
    return STRIDE if inc < STRIDE else (inc // STRIDE) * STRIDE

def scan_at(lock, gpu_id: int, start: int):
    sh = f"{start:x}"
    log(lock, gpu_id, f">>> scan start=0x{sh}")
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
            log(lock, gpu_id, line.strip())
            if line.startswith("GPU:"):
                header_done = True
            continue
        if line.startswith("Public Addr:"):
            hit, addr = True, line.split()[-1].strip()
            log(lock, gpu_id, f"   !! public-hit: {addr}")
        if "Priv (HEX):" in line and hit:
            m = re.search(r"0x\s*([0-9A-Fa-f]+)", line)
            if m:
                priv = m.group(1).zfill(64)
                log(lock, gpu_id, f"   >> privkey: {priv}")
    p.wait()
    return hit, addr, priv

def worker(gpu_id: int, lock):
    random.seed(secrets.randbits(64))
    sorted_pfx      = sorted(CONTINUE_MAP.keys(), key=lambda p: -len(p))
    start           = random_start_for_gpu(gpu_id)
    scan_ct         = 0
    initial_window  = 0
    window_rem      = 0
    skip_rem        = 0
    last_main_start = 0

    log(lock, gpu_id, "→ Başladı")

    try:
        while True:
            if window_rem > 0:
                last_main_start = start
                hit, addr, priv = scan_at(lock, gpu_id, start)
                scan_ct += 1
                if hit and priv:
                    matched = next((p for p in sorted_pfx if addr.startswith(p)), PREFIX)
                    new_win = CONTINUE_MAP.get(matched, DEFAULT_CONTINUE)
                    if new_win > initial_window:
                        initial_window = new_win
                        log(lock, gpu_id, f"   >> nadir hit! window={initial_window}")
                window_rem -= 1
                log(lock, gpu_id, f"   >> [MAIN WINDOW] {initial_window-window_rem}/{initial_window}")
                start = wrap_inc(start, STRIDE) if window_rem > 0 else start
                if window_rem == 0:
                    skip_rem = SKIP_CYCLES
                    log(lock, gpu_id, f"   >> MAIN WINDOW bitti → skip-window={SKIP_CYCLES}")
                continue

            if skip_rem > 0:
                bit_skip    = random.randrange(SKIP_BITS_MIN, SKIP_BITS_MAX+1)
                raw_skip    = 1 << bit_skip
                skip_amt    = align_to_stride(raw_skip)
                skip_start  = wrap_inc(last_main_start, skip_amt)
                start       = skip_start
                last_main_start = skip_start
                log(lock, gpu_id, f"   >> [SKIP WINDOW] {SKIP_CYCLES-skip_rem+1}/{SKIP_CYCLES}: "
                                   f"{bit_skip}-bit skip → 0x{start:x}")
                hit, addr, priv = scan_at(lock, gpu_id, start)
                scan_ct += 1
                if hit and priv:
                    matched = next((p for p in sorted_pfx if addr.startswith(p)), PREFIX)
                    initial_window = CONTINUE_MAP.get(matched, DEFAULT_CONTINUE)
                    window_rem = initial_window
                    skip_rem   = SKIP_CYCLES
                    start      = wrap_inc(start, STRIDE)
                    log(lock, gpu_id, f"   >> SKIP-HIT! matched={matched}, window={initial_window}")
                else:
                    skip_rem -= 1
                    if skip_rem == 0:
                        start = random_start_for_gpu(gpu_id)
                        log(lock, gpu_id, f"   >> SKIP WINDOW no-hit→ random_start")
                continue

            for _ in range(DEFAULT_CONTINUE):
                hit, addr, priv = scan_at(lock, gpu_id, start)
                scan_ct += 1
                if hit and priv:
                    matched        = next((p for p in sorted_pfx if addr.startswith(p)), PREFIX)
                    initial_window = CONTINUE_MAP.get(matched, DEFAULT_CONTINUE)
                    window_rem     = initial_window
                    start          = wrap_inc(start, STRIDE)
                    log(lock, gpu_id, f"   >> SEQ-HIT! matched={matched}, window={initial_window}")
                    break
                else:
                    start = wrap_inc(start, STRIDE)
            else:
                start = random_start_for_gpu(gpu_id)

            if scan_ct % 10 == 0:
                log(lock, gpu_id, f"[STATUS] scans={scan_ct}, next=0x{start:x}")

    except KeyboardInterrupt:
        log(lock, gpu_id, ">> Exiting")

def main():
    mp.set_start_method("spawn", force=True)
    lock = mp.Lock()
    procs = []
    try:
        for gid in GPU_IDS:
            p = mp.Process(target=worker, args=(gid, lock), daemon=True)
            p.start()
            procs.append(p)
        while any(p.is_alive() for p in procs):
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[MAIN] Durduruluyor...", flush=True)
    finally:
        for p in procs:
            if p.is_alive():
                p.terminate()
        for p in procs:
            p.join()

if __name__ == "__main__":
    main()

