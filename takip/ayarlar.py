"""Ayar dosyalarını ve kalıcı durumu (görülen ilanlar vb.) yönetir."""
import json
import os
import pathlib
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import yaml

KOK = pathlib.Path(__file__).resolve().parent.parent
TR = ZoneInfo("Europe/Istanbul")


def simdi():
    return datetime.now(TR)


def bugun() -> date:
    return simdi().date()


def _yaml(yol):
    with open(yol, encoding="utf-8") as f:
        return yaml.safe_load(f)


def kaynaklar():
    return _yaml(KOK / "config" / "kaynaklar.yaml")["kaynaklar"]


def belediyeler():
    return _yaml(KOK / "config" / "belediyeler.yaml")


def profiller():
    s = os.environ.get("PROFILES_YAML", "").strip()
    if s:
        return yaml.safe_load(s)
    yol = KOK / "config" / "profiller.yaml"
    if yol.exists():
        return _yaml(yol)
    raise SystemExit("Profil bilgileri bulunamadı. GitHub'da PROFILES_YAML secret'ını ekleyin.")


class Durum:
    def __init__(self, ad="durum.json"):
        self.yol = KOK / "state" / ad
        self.d = {}
        if self.yol.exists():
            try:
                self.d = json.loads(self.yol.read_text(encoding="utf-8"))
            except Exception:
                self.d = {}
        for k in ("gorulen", "hata_sayac", "bos_sayac", "son_hatalar", "gunluk", "belediye_ilk"):
            self.d.setdefault(k, {})

    def goruldu_mu(self, anahtarlar):
        return any(k in self.d["gorulen"] for k in anahtarlar)

    def isaretle(self, anahtarlar):
        b = bugun().isoformat()
        for k in anahtarlar:
            self.d["gorulen"][k] = b

    def gunluk_say(self, n):
        b = bugun().isoformat()
        self.d["gunluk"][b] = self.d["gunluk"].get(b, 0) + n

    def kaydet(self):
        sinir = (bugun() - timedelta(days=200)).isoformat()
        self.d["gorulen"] = {k: v for k, v in self.d["gorulen"].items() if v >= sinir}
        gsinir = (bugun() - timedelta(days=30)).isoformat()
        self.d["gunluk"] = {k: v for k, v in self.d["gunluk"].items() if k >= gsinir}
        self.yol.parent.mkdir(parents=True, exist_ok=True)
        self.yol.write_text(json.dumps(self.d, ensure_ascii=False, indent=1, sort_keys=True),
                            encoding="utf-8")
