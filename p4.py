#!/usr/bin/env python3
import os
import sys
import time
import secrets
import subprocess
import threading
import pty
from math import gcd

# ====== KULLANICI AYARLARI ======
KEY_MIN      = int("400000000000000000", 16)
KEY_MAX      = int("7FFFFFFFFFFFFFFFFF", 16)
RANGE_BITS   = 39
BLOCK_SIZE   = 1 << RANGE_BITS
KEYSPACE_LEN = KEY_MAX - KEY_MIN + 1
MAX_OFFSET   = KEYSPACE_LEN - BLOCK_SIZE
N_BLOCKS     = KEYSPACE_LEN // BLOCK_SIZE

VANITY     = "./vanitysearch"
ALL_FILE   = "ALL1.txt"
PREFIX     = "1PWo3JeB9"

GPU_IDS    = [0, 1, 2, 3]


def wrap_inc(start: int, inc: int = BLOCK_SIZE) -> int:
    """KEY_MIN…KEY_MAX arasında wrap-around ile inc artışı."""
    off = (start - KEY_MIN + inc) % (MAX_OFFSET + 1)
    return KEY_MIN + off


def make_block_sequencer(gpu_id: int, ngpus: int):
    """Çakışmasız, permütasyon bazlı blok sıralayıcı."""
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
        start = KEY_MIN + idx * BLOCK_SIZE
        print(f">>> [GPU {gpu_id}] next_seq: idx={idx} start=0x{start:x}", flush=True)
        return start

    return next_start


def scan_at(start: int, gpu_id: int):
    """
    scan_start mesajı ve VanitySearch'ü gerçek TTY modunda çağır.
    -o ALL1.txt bayrağı ile sonuçları ALL1.txt'ye yazar.
    Public Addr satırlarını da yakalar.
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

    # PTY master/slave aç
    master_fd, slave_fd = pty.openpty()
    proc = subprocess.Popen(
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

    # PTY üzerinden gerçek zamanlı oku ve hem ekrana bas hem parse et
    while True:
        try:
            chunk = os.read(master_fd, 1024)
        except OSError:
            break
        if not chunk:
            break

        # VanitySearch'ün tüm çıktısını ekrana bas
        os.write(sys.stdout.fileno(), chunk)

        # Hit araması için satır tamponu
        buffer += chunk
        if b"\n" in buffer:
            parts = buffer.split(b"\n")
            for line in parts[:-1]:
                text = line.decode("utf-8", "ignore").strip()
                if text.startswith("Public Addr:"):
                    hit = True
                    addr = text.split()[-1]
            buffer = parts[-1]

    proc.wait()
    os.close(master_fd)
    return hit, addr


def worker(gpu_id: int, ngpus: int):
    """Her GPU için çalışan thread."""
    next_start = make_block_sequencer(gpu_id, ngpus)
    start = next_start()
    scan_count = 0

    print(f"\n→ GPU {gpu_id} başlatıldı (thread), CTRL-C ile durdurabilirsiniz.\n", flush=True)

    try:
        while True:
            hit, addr = scan_at(start, gpu_id)
            scan_count += 1
            if hit:
                print(f"[GPU {gpu_id}]   !! public-hit: {addr}", flush=True)
            if scan_count % 5 == 0:
                # beş taramada bir durum raporu
                print(f"[GPU {gpu_id}] [STATUS] scans={scan_count}, next will wrap_inc", flush=True)
            # sıradaki blok
            start = wrap_inc(start, BLOCK_SIZE)
            # veya eğer isterseniz skip/continue mantığı ekleyin
    except KeyboardInterrupt:
        print(f"\n>> GPU {gpu_id} durduruldu.", flush=True)


def main():
    ngpus = len(GPU_IDS)
    threads = []
    for gpu_id in GPU_IDS:
        t = threading.Thread(target=worker, args=(gpu_id, ngpus), daemon=True)
        threads.append(t)
        t.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n>> Tüm GPU thread'leri durduruluyor...", flush=True)


if __name__ == "__main__":
    main()
