#!/usr/bin/env python3
import secrets
import random
import subprocess
import re
import time

# ====== KULLANICI AYARLARI ======
KEY_MIN        = int("400000000000000000", 16)
KEY_MAX        = int("7FFFFFFFFFFFFFFFFF",    16)
RANGE_BITS     = 40
BLOCK_SIZE     = 1 << RANGE_BITS
KEYSPACE_LEN   = KEY_MAX - KEY_MIN + 1
MAX_OFFSET     = KEYSPACE_LEN - BLOCK_SIZE

VANITY         = "./vanitysearch"
GPU_ID         = 0
ALL_FILE       = "ALL1.txt"
PREFIX         = "1PWo3JeB"

# continuation tablosu
CONTINUE_MAP = {
    "1PWo3JeB9jr": 100,
    "1PWo3JeB9j":   25,
    "1PWo3JeB9":     2,
    "1PWo3JeB":      1,
}
DEFAULT_CONTINUE = 1

# skip-window ayarları
SKIP_CYCLES    = 8
SKIP_BITS_MIN  = 55
SKIP_BITS_MAX  = 64


def random_start() -> int:
    """
    9 hex haneyi (36 bit) rastgele seç, gerisi sıfır olacak şekilde oluştur.
    KEY_MIN…KEY_MAX-BLOCK_SIZE+1 aralığında kalmasını sağlar.
    Örn: 0x[9_HEX_RANDOM]000000000
    """
    NIBBLES    = 9              # rastgele atılacak hex basamağı sayısı
    SHIFT_BITS = NIBBLES * 4    # 36 bit

    # 9 hex hane aralığı içinde hi_min…hi_max sınırları
    hi_min = KEY_MIN >> SHIFT_BITS
    hi_max = (KEY_MAX - BLOCK_SIZE + 1) >> SHIFT_BITS

    # bu aralıkta rastgele 9-hex hane
    hi = secrets.randbelow(hi_max - hi_min + 1) + hi_min
    start = hi << SHIFT_BITS

    print(f">>> random_start → start=0x{start:0{NIBBLES + (SHIFT_BITS//4)}x}")
    return start


def wrap_inc(start: int, inc: int) -> int:
    """
    start + inc miktarını KEY_MIN…KEY_MAX aralığına wrap eder.
    """
    off = (start - KEY_MIN + inc) % (MAX_OFFSET + 1)
    return KEY_MIN + off


def scan_at(start: int):
    """
    VanitySearch-Bitcrack'i verilen start ve RANGE_BITS ile çalıştırıp
    public & private anahtar vurup vurmadığını döner.
    """
    hexstart = format(start, 'x')
    print(f">>> scan start=0x{hexstart}")

    p = subprocess.Popen(
        [VANITY,
         "-gpuId", str(GPU_ID),
         "-o", ALL_FILE,
         "-start", hexstart,
         "-range", str(RANGE_BITS),
         PREFIX],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    header_done = False
    hit = False
    addr = priv = None

    for line in p.stdout:
        # başlık kısmını bastır, sonra sonuç satırlarını yakala
        if not header_done:
            print(line, end="", flush=True)
            if line.startswith("GPU:"):
                header_done = True
            continue

        if line.startswith("Public Addr:"):
            hit, addr = True, line.split()[-1].strip()
            print(f"   !! public-hit: {addr}")

        if "Priv (HEX):" in line and hit:
            m = re.search(r"0x\s*([0-9A-Fa-f]+)", line)
            if m:
                priv = m.group(1).zfill(64)
                print(f"   >> privkey: {priv}")

    p.wait()
    return hit, addr, priv


def main():
    scan_ct         = 0
    initial_window  = 0
    window_rem      = 0
    skip_rem        = 0
    last_main_start = 0
    start           = random_start()

    print("\n→ CTRL-C to stop\n")
    try:
        while True:
            # 1) MAIN WINDOW
            if window_rem > 0:
                last_main_start = start
                hit, addr, priv = scan_at(start)
                scan_ct += 1

                if hit and priv:
                    matched = next((p for p in CONTINUE_MAP if addr.startswith(p)), PREFIX)
                    new_win = CONTINUE_MAP.get(matched, DEFAULT_CONTINUE)
                    if new_win > initial_window:
                        initial_window = new_win
                        print(f"   >> nadir hit! window={initial_window}")

                window_rem -= 1
                print(f"   >> [MAIN WINDOW] {initial_window-window_rem}/{initial_window}")

                if window_rem > 0:
                    start = wrap_inc(start, BLOCK_SIZE)
                else:
                    skip_rem = SKIP_CYCLES
                    print(f"   >> MAIN WINDOW bitti → skip-window={SKIP_CYCLES}\n")
                continue

            # 2) SKIP WINDOW
            if skip_rem > 0:
                bit_skip    = random.randrange(SKIP_BITS_MIN, SKIP_BITS_MAX+1)
                skip_amt    = 1 << bit_skip
                skip_start  = wrap_inc(last_main_start, skip_amt)
                start       = skip_start
                last_main_start = skip_start

                print(f"   >> [SKIP WINDOW] "
                      f"{SKIP_CYCLES-skip_rem+1}/{SKIP_CYCLES}: "
                      f"{bit_skip}-bit skip → 0x{start:x}")

                hit, addr, priv = scan_at(start)
                scan_ct += 1

                if hit and priv:
                    matched = next((p for p in CONTINUE_MAP if addr.startswith(p)), PREFIX)
                    new_win = CONTINUE_MAP.get(matched, DEFAULT_CONTINUE)
                    if new_win > initial_window:
                        initial_window = new_win
                    window_rem = initial_window
                    skip_rem   = SKIP_CYCLES
                    start      = wrap_inc(start, BLOCK_SIZE)
                    print(f"   >> SKIP-HIT! matched={matched}, window={initial_window}\n")
                else:
                    skip_rem -= 1
                    if skip_rem == 0:
                        start = random_start()
                        print(f"   >> SKIP WINDOW no-hit → random_start\n")
                continue

            # 3) SEQ WINDOW (DEFAULT_CONTINUE)
            for _ in range(DEFAULT_CONTINUE):
                hit, addr, priv = scan_at(start)
                scan_ct += 1
                if hit and priv:
                    matched        = next((p for p in CONTINUE_MAP if addr.startswith(p)), PREFIX)
                    initial_window = CONTINUE_MAP.get(matched, DEFAULT_CONTINUE)
                    window_rem     = initial_window
                    start          = wrap_inc(start, BLOCK_SIZE)
                    print(f"   >> SEQ-HIT! matched={matched}, window={initial_window}\n")
                    break
                else:
                    start = wrap_inc(start, BLOCK_SIZE)
            else:
                start = random_start()

            if scan_ct % 10 == 0:
                print(f"[STATUS] scans={scan_ct}, next=0x{start:x}\n")

    except KeyboardInterrupt:
        print("\n>> Exiting")


if __name__ == "__main__":
    main()


