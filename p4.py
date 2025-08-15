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
RANGE_BITS = 39
BLOCK_SIZE = 1 << RANGE_BITS
KEYSPACE   = KEY_MAX - KEY_MIN + 1
MAX_OFFSET = KEYSPACE - BLOCK_SIZE

VANITY   = "./vanitysearch"
ALL_FILE = "ALL1.txt"
PREFIX   = "1PWo3JeB9"

GPU_IDS  = [0, 1, 2, 3]


def wrap_inc(start: int) -> int:
    """Bir sonraki blok başlangıcına, wrap-around ile geçiş."""
    off   = (start - KEY_MIN + BLOCK_SIZE) % (MAX_OFFSET + 1)
    return KEY_MIN + off


def scan_at(start: int, gpu_id: int):
    """
    PTY üzerinden VanitySearch'ü çalıştırır, gerçek terminal çıktısını ekrana basar
    ve 'Public Addr:' satırını yakalar.
    """
    print(f">>> [GPU {gpu_id}] scan start=0x{start:x}", flush=True)
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
        stdin = subprocess.DEVNULL,
        stdout = slave_fd,
        stderr = slave_fd,
        close_fds = True
    )
    os.close(slave_fd)

    hit    = False
    addr   = None
    buffer = b""

    # PTY master'dan oku, ekrana bas ve parse et
    while True:
        try:
            chunk = os.read(master_fd, 1024)
        except OSError:
            break
        if not chunk:
            break

        # VanitySearch'ün tüm çıktısını göster
        os.write(sys.stdout.fileno(), chunk)

        # 'Public Addr:' yakalamak için tamponu kontrol et
        buffer += chunk
        if b"\n" in buffer:
            lines = buffer.split(b"\n")
            for line in lines[:-1]:
                text = line.decode("utf-8", "ignore").strip()
                if text.startswith("Public Addr:"):
                    hit  = True
                    addr = text.split()[-1]
            buffer = lines[-1]

    p.wait()
    os.close(master_fd)
    return hit, addr


def worker(gpu_id: int):
    """
    Her GPU için:
      - Rastgele bir blokla başlar,
      - Eğer hit yoksa yeniden rastgele bir blok seçer,
      - Eğer hit varsa 5 blok art arda tarar, sonra tekrar rastgele başlar.
    """
    print(f"[GPU {gpu_id}] Worker PID={os.getpid()} başlatıldı", flush=True)

    current_start = None
    window_rem    = 0

    try:
        while True:
            if window_rem == 0:
                # Yeni rastgele başlangıç
                offset        = secrets.randbelow(MAX_OFFSET + 1)
                current_start = KEY_MIN + offset
                print(f"[GPU {gpu_id}] → RANDOM start @0x{current_start:x}", flush=True)

                hit, addr = scan_at(current_start, gpu_id)
                if hit:
                    print(f"[GPU {gpu_id}]   !! hit: {addr}", flush=True)
                    window_rem = 5
                # hit yoksa loop devam, tekrar rastgele
                continue

            # window_rem > 0: ardışık 5 blok
            current_start = wrap_inc(current_start)
            print(f"[GPU {gpu_id}] → WINDOW scan @{window_rem} left @0x{current_start:x}", flush=True)
            hit, addr = scan_at(current_start, gpu_id)
            if hit:
                print(f"[GPU {gpu_id}]   !! window-hit: {addr}", flush=True)
            window_rem -= 1
            # window dolunca, sıradaki loop yine rastgele'ye döner

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
        print("\n>> Tüm GPU thread'leri sonlandırılıyor...", flush=True)


if __name__ == "__main__":
    main()
