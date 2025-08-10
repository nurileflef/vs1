import os
import time
import threading
import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv

# Ortam değişkenlerini yükle
load_dotenv()

# Telegram Bot Ayarları
BOT_TOKEN   = os.getenv("TELEGRAM_TOKEN")
CHAT_ID     = os.getenv("TELEGRAM_CHAT_ID")
SEND_URL    = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
OUTPUT_FILE = "ALL.txt"

class FileChangeHandler(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        self.lock = threading.Lock()

        if os.path.exists(OUTPUT_FILE):
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                lines = [l for l in f if l.strip()]
            self.processed_blocks = len(lines) // 3
        else:
            self.processed_blocks = 0

    def on_modified(self, event):
        if not event.src_path.endswith(OUTPUT_FILE):
            return

        time.sleep(0.1)

        with self.lock:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                lines = [l.rstrip("\n") for l in f if l.strip()]

            total_blocks = len(lines) // 3
            new_blocks = total_blocks - self.processed_blocks

            if new_blocks > 0:
                for block_index in range(self.processed_blocks, total_blocks):
                    start, end = 3*block_index, 3*block_index + 3
                    block_lines = lines[start:end]
                    text = "```\n" + "\n".join(block_lines) + "\n```"
                    payload = {
                        "chat_id": CHAT_ID,
                        "text": text,
                        "parse_mode": "Markdown"
                    }
                    resp = requests.post(SEND_URL, data=payload)
                    if resp.ok:
                        print(f"✅ Blok #{block_index+1} başarıyla gönderildi")
                    else:
                        print("❌ Gönderim hatası:", resp.text)

                self.processed_blocks = total_blocks

if __name__ == "__main__":
    open(OUTPUT_FILE, "a").close()

    observer = Observer()
    observer.schedule(FileChangeHandler(), path=".", recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
