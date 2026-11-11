"""Telegram'a mesaj gönderme."""
import html
import logging
import os
import time

import requests

log = logging.getLogger("takip")


def e(s) -> str:
    return html.escape(str(s), quote=False)


class Telegram:
    def __init__(self, kuru=False):
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        self.sohbet = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        self.kuru = kuru
        self.gonderilen = 0
        if not kuru and not (self.token and self.sohbet):
            log.warning("TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID yok; mesajlar sadece kayda yazılacak.")
            self.kuru = True

    def gonder(self, metin: str) -> bool:
        if self.kuru:
            print("----- MESAJ (gönderilmedi) -----\n" + metin + "\n")
            self.gonderilen += 1
            return True
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        veri = {"chat_id": self.sohbet, "text": metin[:4000], "parse_mode": "HTML",
                "disable_web_page_preview": True}
        for _ in range(4):
            try:
                r = requests.post(url, json=veri, timeout=30)
            except Exception as ex:
                log.warning("Telegram'a ulaşılamadı: %s", ex)
                time.sleep(5)
                continue
            if r.status_code == 200:
                self.gonderilen += 1
                time.sleep(3.2)  # grup sınırı: dakikada ~20 mesaj
                return True
            if r.status_code == 429:
                bekle = r.json().get("parameters", {}).get("retry_after", 10)
                time.sleep(bekle + 1)
                continue
            log.warning("Telegram hatası %s: %s", r.status_code, r.text[:200])
            return False
        return False
