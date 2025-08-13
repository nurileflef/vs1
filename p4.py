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
RANGE_BITS     = 39
BLOCK_SIZE     = 1 << RANGE_BITS
KEYSPACE_LEN   = KEY_MAX - KEY_MIN + 1
MAX_OFFSET     = KEYSPACE_LEN - BLOCK_SIZE  # start en fazla KEY_MAX - 2^RANGE_BITS + 1 olabilir

VANITY         = "./vanitysearch"
ALL_FILE       = "ALL.txt"          # istersen GPU'ya göre: f"ALL_gpu{gpu_id}.txt"
PREFIX         = "1PWo3JeB9"

# Bulunan prefix'e göre "ek skip tarama sayısı"
CONTINUE_MAP = {
    "1PWo3JeB9jr": 100,
    "1PWo3JeB9j":   71,
    "1PWo3JeB9":     15,
    "1PWo3JeB":      5,
}
DEFAULT_CONTINUE = 5  # hit sonrası varsayılan ek skip taraması

# ====== SKIP PARAMETRELERİ ======
SKIP_BITS_MIN  = 55
SKIP_BITS_MAX  = 64

# ====== GPU / RESEED ======
TOTAL_GPUS     = 4
RESEED_EVERY   = 15      # taban reseed periyodu (scan sayısı)
RESEED_JITTER  = 5       # ± jitter (örn. 15±5 → 10..20)

# ====== YARDIMCI ======
def block_index_from_start(start: int) -> int:
    return (start - KEY_MIN) >> RANGE_BITS

def random_start(gpu_id=0, total_gpus=1):
    """
    Start adresini KEY_MIN..KEY_MIN+MAX_OFFSET aralığından uniform seçer.
    GPU'lar çakışmasın diye block_index % total_gpus == gpu_id sınıfını korur.
    Bu seçim blok hizasında DEĞİL; alt bitler de rastgeleleşir.
    """
    while True:
        off = secrets.randbelow(MAX_OFFSET + 1)  # 0..MAX_OFFSET (geçerli tüm start'lar)
        if ((off >> RANGE_BITS) % total_gpus) == gpu_id:
            start = KEY_MIN + off
            print(f">>> [GPU {gpu_id}] random_start → 0x{start:x} (class={block_index_from_start(start) % total_gpus})")
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

def reseed_threshold() -> int:
    """RESEED_EVERY ± RESEED_JITTER aralığında pozitif eşik döndürür."""
    if RESEED_JITTER <= 0:
        return max(1, RESEED_EVERY)
    delta = secrets.randbelow(2 * RESEED_JITTER + 1) - RESEED_JITTER  # [-J, +J]
    return max(1, RESEED_EVERY + delta)

def worker(gpu_id: int):
    sorted_pfx = sorted(CONTINUE_MAP.keys(), key=lambda p: -len(p))

    start               = random_start(gpu_id=gpu_id, total_gpus=TOTAL_GPUS)
    scan_ct             = 0
    extra_skips         = 0
    miss_ct             = 0

    # Per-GPU reseed sayaçları
    scans_since_reseed  = 0
    reseed_target       = reseed_threshold()
    reseed_pending      = False  # extra-skip sırasında dolarsa, bitince uygulanacak

    print(f"\n→ GPU {gpu_id} skip-modunda başlatıldı. CTRL-C ile durdurabilirsiniz.\n")

    try:
        while True:
            # Hit sonrası planlı ek skip taraması
            if extra_skips > 0:
                bit_skip = random.randrange(SKIP_BITS_MIN, SKIP_BITS_MAX + 1)
                start    = wrap_inc(start, 1 << bit_skip)

                step_idx = (CONTINUE_MAP.get(PREFIX, DEFAULT_CONTINUE) - extra_skips + 1)
                print(f"[GPU {gpu_id}]   >> [SKIP-AFTER-HIT] step={step_idx}, {bit_skip}-bit skip → 0x{start:x}")

                hit, addr, priv = scan_at(start, gpu_id)
                scan_ct += 1
                scans_since_reseed += 1

                if hit and priv:
                    matched     = next((p for p in sorted_pfx if addr.startswith(p)), PREFIX)
                    extra_skips = CONTINUE_MAP.get(matched, DEFAULT_CONTINUE)
                    miss_ct     = 0
                    print(f"[GPU {gpu_id}]   >> HIT in extra-skip! matched={matched}, reset extra_skips={extra_skips}\n")
                else:
                    extra_skips -= 1
                    miss_ct     += 1

                # Eşik dolduysa, extra-skip bitince reseed yap
                if scans_since_reseed >= reseed_target:
                    reseed_pending = True

                # Extra-skip bitti ve reseed bekliyorsa şimdi uygula
                if extra_skips == 0 and reseed_pending:
                    old = start
                    start = random_start(gpu_id=gpu_id, total_gpus=TOTAL_GPUS)
                    scans_since_reseed = 0
                    reseed_target      = reseed_threshold()
                    reseed_pending     = False
                    print(f"🔄 [GPU {gpu_id}] reseed (post-extra): old=0x{old:x} → new=0x{start:x} | next threshold={reseed_target}")

                if scan_ct % 10 == 0:
                    print(f"[GPU {gpu_id}] [STATUS] scans={scan_ct}, next=0x{start:x}")
                continue

            # Normal sürekli skip taraması
            bit_skip = random.randrange(SKIP_BITS_MIN, SKIP_BITS_MAX + 1)
            start    = wrap_inc(start, 1 << bit_skip)
            print(f"[GPU {gpu_id}]   >> [SKIP] {bit_skip}-bit skip → 0x{start:x}")

            hit, addr, priv = scan_at(start, gpu_id)
            scan_ct += 1
            scans_since_reseed += 1

            if hit and priv:
                matched     = next((p for p in sorted_pfx if addr.startswith(p)), PREFIX)
                extra_skips = CONTINUE_MAP.get(matched, DEFAULT_CONTINUE)
                miss_ct     = 0
                print(f"[GPU {gpu_id}]   >> HIT! matched={matched}, schedule extra_skips={extra_skips}\n")
            else:
                miss_ct += 1

            # Normal modda eşik dolduysa hemen reseed
            if scans_since_reseed >= reseed_target and extra_skips == 0:
                old = start
                start = random_start(gpu_id=gpu_id, total_gpus=TOTAL_GPUS)
                scans_since_reseed = 0
                reseed_target      = reseed_threshold()
                print(f"🔄 [GPU {gpu_id}] reseed: old=0x{old:x} → new=0x{start:x} | next threshold={reseed_target}")

            if scan_ct % 10 == 0:
                cls = block_index_from_start(start) % TOTAL_GPUS
                print(f"[GPU {gpu_id}] [STATUS] scans={scan_ct}, next=0x{start:x}, class={cls}")

    except KeyboardInterrupt:
        print(f"\n>> GPU {gpu_id} durduruldu.")

def main():
    threads = []
    for gpu_id in range(TOTAL_GPUS):
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





