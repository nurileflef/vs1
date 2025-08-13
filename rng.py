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

def generate_random_start_int():
    safe_upper = UPPER_BOUND - (1 << (SKIP_MAX + 1)) - (1 << RANGE_SIZE)
    return random.randint(LOWER_BOUND, safe_upper)

def format_hex(x):
    return hex(x)[2:].upper()

def gpu_worker(gpu_id):
    print("GPU {} started.".format(gpu_id))
    while True:
        start_int = generate_random_start_int()
        base_hex = format_hex(start_int)
        print("GPU {} start: {}".format(gpu_id, base_hex))
        for i in range(NUM_SKIPS):
            skip_bits = random.randint(SKIP_MIN, SKIP_MAX)
            start_int += (1 << skip_bits)
            hex_start = format_hex(start_int)
            print("GPU {} skip #{}: +2^{} -> {}".format(gpu_id, i+1, skip_bits, hex_start))
            try:
                subprocess.run([
                    "./vanitysearch",
                    "-gpuId", str(gpu_id),
                    "-o", FOUND_FILE,
                    "-start", hex_start,
                    "-range", str(RANGE_SIZE),
                    PREFIX
                ], check=True)
            except subprocess.CalledProcessError as e:
                print("GPU {} error: {}".format(gpu_id, e))
            print("GPU {} done #{}: {}".format(gpu_id, i+1, hex_start))
        print("-" * 33)

def main():
    num_gpus = 4
    processes = []
    for gpu_id in range(num_gpus):
        p = multiprocessing.Process(target=gpu_worker, args=(gpu_id,))
        p.start()
        processes.append(p)
    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        print("Stopping all processes...")
        for p in processes:
            p.terminate()

if __name__ == "__main__":
    main()
