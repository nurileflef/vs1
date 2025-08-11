import subprocess
import secrets
import multiprocessing
import sys
import time

# Ayarlar
FOUND_FILE = "ALL.txt"
PREFIX = "1PWo3JeB"
RANGE_SIZE = 40

LOWER_BOUND = 0x400000000000000000
UPPER_BOUND = 0x7fffffffffffffffff


def generate_random_start():
    low = LOWER_BOUND >> RANGE_SIZE
    high = UPPER_BOUND >> RANGE_SIZE
    count = high - low + 1
    if count <= 0:
        raise ValueError("Invalid range: high < low")
    val = secrets.randbelow(count) + low
    return format(val << RANGE_SIZE, 'X')


def run_gpu(gpu_id):
    print(f"🎯 GPU {gpu_id} başlatılıyor (range: {hex(LOWER_BOUND)} – {hex(UPPER_BOUND)})")

    while True:
        try:
            random_start = generate_random_start()
        except Exception as e:
            print(f"🛑 GPU {gpu_id} – random start hatası: {e}")
            break

        print(f"🚀 GPU {gpu_id} – scanning: {random_start} (2^{RANGE_SIZE} keys)")

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
            print(f"❌ GPU {gpu_id} – vanitysearch çalıştırma hatası: {e}")
            break

        print(f"✅ GPU {gpu_id} tamamlandı: {random_start}")
        print("----------------------------")

        # İsteğe bağlı: bir süre beklemeden sürekli devam eder
        # time.sleep(0.1)


if __name__ == "__main__":
    try:
        gpu_ids = [0, 1, 2, 3]
        processes = []

        for gpu in gpu_ids:
            p = multiprocessing.Process(target=run_gpu, args=(gpu,))
            p.start()
            processes.append(p)

        for p in processes:
            p.join()

    except KeyboardInterrupt:
        print("\n🛑 Kullanıcı tarafından durduruldu. Süreçler sonlandırılıyor...")
        for p in processes:
            p.terminate()
        sys.exit(0)
