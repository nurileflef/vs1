import random
import subprocess
import multiprocessing

FOUND_FILE = "ALL.txt"
PREFIX = "1PWo3JeB9"
RANGE_SIZE = 40

LOWER_BOUND = 0x400000000000000000
UPPER_BOUND = 0x7FFFFFFFFFFFFFFFFF
NUM_SKIPS = 15
SKIP_MIN = 51
SKIP_MAX = 64

def generate_start():
    block_size = 1 << RANGE_SIZE
    while True:
        prefix = random.getrandbits(32)
        start = prefix << RANGE_SIZE
        if LOWER_BOUND <= start <= UPPER_BOUND - block_size:
            return start

def format_hex(x):
    return hex(x)[2:].upper()

def gpu_worker(gpu_id):
    print(f"GPU {gpu_id} started")
    while True:
        start_int = generate_start()
        print(f"GPU {gpu_id} start: {format_hex(start_int)}")
        for i in range(NUM_SKIPS):
            skip = random.randint(SKIP_MIN, SKIP_MAX)
            start_int += 1 << skip
            hs = format_hex(start_int)
            print(f"GPU {gpu_id} skip#{i+1}: +2^{skip} -> {hs}")
            try:
                subprocess.run([
                    "./vanitysearch",
                    "-gpuId", str(gpu_id),
                    "-o", FOUND_FILE,
                    "-start", hs,
                    "-range", str(RANGE_SIZE),
                    PREFIX
                ], check=True)
            except subprocess.CalledProcessError as e:
                print(f"GPU {gpu_id} error: {e}")
            print(f"GPU {gpu_id} done#{i+1}: {hs}")
        print("-" * 33)

def main():
    num_gpus = 4
    procs = []
    for gpu_id in range(num_gpus):
        p = multiprocessing.Process(target=gpu_worker, args=(gpu_id,))
        p.start()
        procs.append(p)
    try:
        for p in procs:
            p.join()
    except KeyboardInterrupt:
        for p in procs:
            p.terminate()

if __name__ == "__main__":
    main()
