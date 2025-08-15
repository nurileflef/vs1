#!/usr/bin/env python3
import os
import sys
import time
import threading
import secrets
import subprocess
import pty

# ====== AYARLAR ======
KEY_MIN    = int("400000000000000000", 16)
KEY_MAX    = int("7FFFFFFFFFFFFFFFFF", 16)
RANGE_BITS = 38
BLOCK_SIZE = 1 << RANGE_BITS
KEYSPACE   = KEY_MAX - KEY_MIN + 1
N_BLOCKS   = KEYSPACE // BLOCK_SIZE

VANITY   = "./vanitysearch"
ALL_FILE = "ALL1.txt"
PREFIX   = "1PWo3JeB9"

GPU_IDS  = [0, 1, 2, 3]


def wrap_inc(start: int) -> int:
    """Bir sonraki blok start adresine geç, wrap-around ile."""
    nxt = start + BLOCK_SIZE
    return KEY_MIN if nxt > KEY_MAX else nxt


def scan_at(start: int, gpu_id: int):
    """
    PTY üzerinden VanitySearch'ü çalıştırır,
    gerçek terminal çıktısını ekrana basar ve
    'Public Addr:' satırını yakalar.
    """
    hex_width = len(f"{KEY_MAX:x}")
    end = start + BLOCK_SIZE - 1

    # keyspace bilgisi
    print(f"[keyspace] range=2^{RANGE_BITS}", flush=True)
    print(f"[keyspace] start={start:0{hex_width}X}", flush=True)
    print(f"[keyspace] end={end:0{hex_width}X}\n", flush=True)

    cmd = [
        VANITY,
        "-gpuId", str(gpu_id),
        "-o", ALL_FILE,
        "-start", f"{start:x}",
        "-range", str(RANGE_BITS),
        PREFIX
    ]

    master_fd, slave_fd = pty.openpty()
    p = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True
    )
    os.close(slave_fd)

    hit = False
    addr = None
    buffer = b""

    while True:
        try:
            chunk = os.read(master_fd, 1024)
        except OSError:
            break
        if not chunk:
            break

        # VanitySearch çıktısını direkt göster
        os.write(sys.stdout.fileno(), chunk)

        # 'Public Addr:' parse
        buffer += chunk
        if b"\n" in buffer:
            lines = buffer.split(b"\n")
            for line in lines[:-1]:
                text = line.decode("utf-8", "ignore").strip()
                if text.startswith("Public Addr:"):
                    hit = True
                    addr = text.split()[-1]
            buffer = lines[-1]

    p.wait()
    os.close(master_fd)
    return hit, addr


def worker(gpu_id: int):
    """
    Her GPU için:
      - Rastgele bir blok scan,
      - Hit → 5 ardışık block scan,
      - Ardından 5 blok skip scan,
      - Tekrar rastgele başlayarak döngü.
    """
    print(f"[GPU {gpu_id}] Worker PID={os.getpid()} başladı", flush=True)

    current_start = None
    window_rem    = 0
    skip_rem      = 0

    try:
        while True:
            # 1) Window modu: hit sonrası ardışık 5 blok
            if window_rem > 0:
                current_start = wrap_inc(current_start)
                print(f"[GPU {gpu_id}] → WINDOW scan ({window_rem} left) @0x{current_start:x}", flush=True)
                hit, addr = scan_at(current_start, gpu_id)
                if hit:
                    print(f"[GPU {gpu_id}]   !! window-hit: {addr}", flush=True)
                window_rem -= 1
                # window biter bitmez skip moduna geç
                if window_rem == 0:
                    skip_rem = 5
                continue

            # 2) Skip modu: window bittikten sonra 5 blok atlayarak scan
            if skip_rem > 0:
                current_start = wrap_inc(current_start)
                print(f"[GPU {gpu_id}] → SKIP scan ({skip_rem} left) @0x{current_start:x}", flush=True)
                hit, addr = scan_at(current_start, gpu_id)
                if hit:
                    print(f"[GPU {gpu_id}]   !! skip-hit: {addr}", flush=True)
                skip_rem -= 1
                # skip bittiğinde tekrar rastgele moda dön
                continue

            # 3) Random modu: yeni rastgele blok
            rand_blk      = secrets.randbelow(N_BLOCKS)
            current_start = KEY_MIN + rand_blk * BLOCK_SIZE
            print(f"[GPU {gpu_id}] → RANDOM block #{rand_blk} @0x{current_start:x}", flush=True)
            hit, addr = scan_at(current_start, gpu_id)
            if hit:
                print(f"[GPU {gpu_id}]   !! hit: {addr}", flush=True)
                window_rem = 5
            # hit yoksa direkt loop devam, yeniden random
    except KeyboardInterrupt:
        print(f"[GPU {gpu_id}] durduruldu", flush=True)


def main():
    # unbuffered stdout
    sys.stdout.reconfigure(line_buffering=True)

    threads = []
    for gid in GPU_IDS:
        t = threading.Thread(target=worker, args=(gid,), daemon=True)
        threads.append(t)
        t.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n>> Tüm GPU thread'leri durduruluyor...", flush=True)


if __name__ == "__main__":
    main()

