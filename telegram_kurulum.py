"""Telegram kurulumunu kontrol eder: botu doğrular, grup kimliğini (chat ID) bulur, deneme mesajı atar."""
import os
import sys

import requests

token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
sohbet = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
if not token:
    sys.exit("HATA: TELEGRAM_BOT_TOKEN secret'ı eklenmemiş.")

api = f"https://api.telegram.org/bot{token}"
ben = requests.get(f"{api}/getMe", timeout=20).json()
if not ben.get("ok"):
    sys.exit("HATA: Token geçersiz görünüyor. BotFather'dan aldığınız token'ı kontrol edin.")
print(f"Bot bulundu: @{ben['result']['username']}")

if not sohbet:
    guncellemeler = requests.get(f"{api}/getUpdates", timeout=20).json().get("result", [])
    gruplar = {}
    for g in guncellemeler:
        m = g.get("message") or g.get("my_chat_member") or g.get("channel_post") or {}
        c = m.get("chat") or {}
        if c.get("type") in ("group", "supergroup"):
            gruplar[c["id"]] = c.get("title", "")
    if not gruplar:
        print("\nHenüz grup bulunamadı. Botu gruba ekleyin, gruba /start yazın ve bu testi tekrar çalıştırın.")
    else:
        print("\nBulunan gruplar (TELEGRAM_CHAT_ID olarak eksi işaretiyle birlikte sayıyı kullanın):")
        for i, t in gruplar.items():
            print(f"  {i}   ->   {t}")
    sys.exit(0)

r = requests.post(f"{api}/sendMessage", json={"chat_id": sohbet,
                  "text": "✅ Deneme mesajı: KPSS takip botu bu gruba mesaj gönderebiliyor."}, timeout=20).json()
if r.get("ok"):
    print("Deneme mesajı gönderildi. Telegram grubunuzu kontrol edin.")
else:
    sys.exit(f"HATA: Mesaj gönderilemedi: {r.get('description')}")
