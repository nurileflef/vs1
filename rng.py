#!/usr/bin/env python3
import secrets
import random
import subprocess
import re
import time
import sys
import errno
from multiprocessing import Process

# ======== GÜVENLİ PRINT WRAPPER ========
# Tüm print'leri BlockingIOError'dan korur
original_print = print
def print(*args, **kwargs):
    try:
        original_print(*args, **kwargs)
    except IOError as e:
        # EAGAIN yalnızca "yazma bloklandı" hatası
        if getattr(e, "errno", None) != errno.EAGAIN:
            raise

# ====== KULLANICI AYARLARI ======
KEY_MIN        = int("400000000000000000", 16)
KEY_MAX        = int("7FFFFFFFFFFFFFFFFF",    16)
RANGE_BITS     = 40
BLOCK_SIZE     = 1 << RANGE_BITS
KEYSPACE_LEN   = KEY_MAX - KEY_MIN + 1
MAX_OFFSET     = KEYSPACE_LEN - BLOCK_SIZE

VANITY         = "./vanitysearch"
ALL_FILE       = "ALL1.txt"
PREFIX         = "1PWo3JeB9"  # güncellendi

CONTINUE_MAP = {
    "1PWo3JeB9jr": 50,
    "1PWo3JeB9j":   5,
    "1PWo3JeB9":    3,  # en sık çıkan olarak güncellendi
    "1PWo3JeB":     1,
}
DEFAULT_CONTINUE = 1

# ====== SKIP WINDOW PARAMETRELERİ ======
SKIP_CYCLES    = 25
SKIP_BITS_MIN  = 55
SKIP_BITS_MAX  = 64


# ==============================================================================
# ====== GÜNCELLENMİŞ VE İYİLEŞTİRİLMİŞ RANDOM FONKSİYONU ======
# ==============================================================================
def random_start():
    """
    KEY_MIN ve KEY_MAX arasında, istatistiksel olarak tamamen tekdüze (uniform) dağılıma sahip
    rastgele bir başlangıç noktası üretir. Bu yöntem, aralıktaki her bir olası anahtara
    eşit seçilme şansı verir ve herhangi bir desene yönelik yanlılık (bias) oluşturmaz.
    '4BBB' ve '49C1' gibi başlangıçların olasılığı tamamen eşittir.
    """
    # 1. Tüm anahtar uzayının toplam büyüklüğünü kullan.
    random_offset = secrets.randbelow(KEYSPACE_LEN)

    # 2. Bu rastgele ofseti, başlangıç anahtarına (KEY_MIN) ekleyerek
    #    tüm aralık içinde tamamen rastgele bir nokta belirle.
    random_key = KEY_MIN + random_offset

    # 3. vanitysearch'ün çalışması için bu tamamen rastgele anahtarı, ait olduğu
    #    bloğun başlangıç adresine hizala. Bu işlem, anahtarın son 40 bitini sıfırlar.
    block_mask = ~((1 << RANGE_BITS) - 1)
    start = random_key & block_mask

    # 4. Hizalama işlemi sonucu anahtarın KEY_MIN'in altına düşme ihtimaline karşı
    #    (çok düşük bir ihtimal de olsa) bir kontrol ekle.
    if start < KEY_MIN:
        start = KEY_MIN
        
    print(f">>> random_start → start=0x{start:x}")
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
            print(f"    !! public-hit: {addr}")

        if "Priv (HEX):" in line and hit:
            m = re.search(r"0x\s*([0-9A-Fa-f]+)", line)
            if m:
                priv = m.group(1).zfill(64)
                print(f"    >> privkey: {priv}")

    p.wait()
    return hit, addr, priv

def worker(gpu_id: int):
    sorted_pfx      = sorted(CONTINUE_MAP.keys(), key=lambda p: -len(p))
    start           = random_start()
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
                print(f"    >> [GPU {gpu_id}] [MAIN WINDOW] "
                      f"{initial_window-window_rem}/{initial_window}")

                if window_rem > 0:
                    start = wrap_inc(start, BLOCK_SIZE)
                else:
                    skip_rem = SKIP_CYCLES
                    print(f"    >> [GPU {gpu_id}] MAIN WINDOW bitti → skip-window={SKIP_CYCLES}\n")
                continue

            # ====== SKIP WINDOW ======
            if skip_rem > 0:
                bit_skip    = random.randrange(SKIP_BITS_MIN, SKIP_BITS_MAX+1)
                skip_amt    = 1 << bit_skip
                skip_start  = wrap_inc(last_main_start, skip_amt)
                start       = skip_start
                last_main_start = skip_start

                print(f"    >> [GPU {gpu_id}] [SKIP WINDOW] "
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
                    print(f"    >> [GPU {gpu_id}] SKIP-HIT! matched={matched}, window={initial_window}\n")
                else:
                    skip_rem -= 1
                    if skip_rem == 0:
                        start = random_start()
                        print(f"    >> [GPU {gpu_id}] SKIP WINDOW no-hit→ random_start\n")
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
                    print(f"    >> [GPU {gpu_id}] SEQ-HIT! matched={matched}, window={initial_window}\n")
                    break
                else:
                    start = wrap_inc(start, BLOCK_SIZE)
            else:
                start = random_start()

            if scan_ct % 10 == 0:
                print(f"[GPU {gpu_id} STATUS] scans={scan_ct}, next=0x{start:x}")

    except KeyboardInterrupt:
        print(f"\n>> [GPU {gpu_id}] Çıkıyor...")

def main():
    gpu_count = 4
    workers = []
    for gpu_id in range(gpu_count):
        p = Process(target=worker, args=(gpu_id,))
        p.start()
        workers.append(p)

    for p in workers:
        p.join()

if __name__ == "__main__":
    main()
