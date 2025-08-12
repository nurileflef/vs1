import random
import subprocess
import multiprocessing

# Ayarlar
FOUND_FILE = "ALL.txt"
PREFIX = "1PWo3JeB9"
RANGE_SIZE = 40

LOWER_BOUND = 0x400000000000000000
UPPER_BOUND = 0x7FFFFFFFFFFFFFFFFF

def generate_random_start():
    """Rastgele bir başlangıç adresi üret"""
    return hex(random.randint(LOWER_BOUND, UPPER_BOUND - (1 << RANGE_SIZE)))[2:].upper()

def gpu_worker(gpu_id):
    """Her GPU için bağımsız random range araması yapar"""
    print(f"🎯 GPU {gpu_id} başlatıldı.")

    while True:
        random_start = generate_random_start()
        print(f"🚀 GPU {gpu_id} – tarama: {random_start} (2^{RANGE_SIZE})")

        try:
            subprocess.run([
                "./vanitysearch",
                "-gpuId", str(gpu_id),
                "-o", FOUND_FILE,
                "-start", random_start,
                "-range", str(RANGE_SIZE),
                PREFIX
            ], check=True)
        except subprocess.CalledProcessError as e:
            print(f"❌ GPU {gpu_id} hata verdi: {e}")

        print(f"✅ GPU {gpu_id} tamamladı: {random_start}")
        print("----------------------------")

def main():
    num_gpus = 4  # 4 GPU kullanılacak
    processes = []

    for gpu_id in range(num_gpus):
        p = multiprocessing.Process(target=gpu_worker, args=(gpu_id,))
        p.start()
        processes.append(p)

    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        print("🛑 Tüm işlemler durduruluyor...")
        for p in processes:
            p.terminate()

if __name__ == "__main__":
    main()
