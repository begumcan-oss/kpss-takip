"""Seçilen illerdeki belediyelerin sitelerini bulur ve duyuru sayfalarını tarar."""
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from bs4 import BeautifulSoup

from .ayarlar import KOK, bugun
from .indir import http_get
from .metin import norm, slug
from .tarayici import kaynak_tara

log = logging.getLogger("takip")
ADRES_DOSYASI = KOK / "state" / "belediye_adresleri.json"


def liste(ayar):
    """[(anahtar, il, ilçe)] — ilçe 'Merkez' ise il/büyükşehir belediyesidir."""
    cikti = []
    for il, ilceler in ayar["iller"].items():
        cikti.append((f"{il}/İl belediyesi", il, "Merkez"))
        for ilce in ilceler:
            if norm(ilce) == "merkez":
                continue
            cikti.append((f"{il}/{ilce}", il, ilce))
    return cikti


def _adaylar(il, ilce):
    s, i = slug(ilce), slug(il)
    if norm(ilce) == "merkez":
        return [f"https://www.{i}.bel.tr", f"https://{i}.bel.tr"]
    return [f"https://www.{s}.bel.tr", f"https://{s}.bel.tr", f"https://www.{s}{i}.bel.tr",
            f"https://www.{s}-{i}.bel.tr", f"https://www.{s}-bld.gov.tr"]


def _dogrula(url, il, ilce):
    try:
        r = http_get(url, timeout=15)
    except Exception:
        return None
    soup = BeautifulSoup(r.text, "lxml")
    metin = norm(soup.get_text(" ", strip=True)[:300000])
    if "belediye" not in metin or norm(il) not in metin:
        return None
    if norm(ilce) != "merkez" and norm(ilce) not in metin:
        return None
    return r.url


def _bul(oge, elle):
    anahtar, il, ilce = oge
    if anahtar in elle:
        return elle[anahtar]
    for u in _adaylar(il, ilce):
        sonuc = _dogrula(u, il, ilce)
        if sonuc:
            return sonuc
    return None


def adresleri_guncelle(ayar):
    try:
        onbellek = json.loads(ADRES_DOSYASI.read_text(encoding="utf-8"))
    except Exception:
        onbellek = {}
    elle = ayar.get("elle_adresler") or {}
    b = bugun()
    tekrar_dene = (b - timedelta(days=14)).isoformat()
    yapilacak = [o for o in liste(ayar)
                 if o[0] in elle
                 or o[0] not in onbellek
                 or (onbellek[o[0]].get("url") is None and onbellek[o[0]].get("tarih", "") < tekrar_dene)]
    if yapilacak:
        log.info("Belediye adresi aranıyor: %d", len(yapilacak))
        with ThreadPoolExecutor(max_workers=16) as ex:
            for oge, url in zip(yapilacak, ex.map(lambda o: _bul(o, elle), yapilacak)):
                onbellek[oge[0]] = {"url": url, "tarih": b.isoformat()}
    ADRES_DOSYASI.parent.mkdir(parents=True, exist_ok=True)
    ADRES_DOSYASI.write_text(json.dumps(onbellek, ensure_ascii=False, indent=1, sort_keys=True),
                             encoding="utf-8")
    return onbellek


def tara_hepsi(ayar, durum):
    adresler = adresleri_guncelle(ayar)
    tarama = ayar.get("tarama", {})
    isler = []
    for anahtar, il, ilce in liste(ayar):
        url = (adresler.get(anahtar) or {}).get("url")
        if url:
            isler.append((anahtar, il, url))

    def tek(is_):
        anahtar, il, url = is_
        cfg = {"ad": anahtar, "baslangic": [url], "tur": "belediye", "render": False,
               "takip_kelimeleri": tarama.get("takip_kelimeleri",
                                              ["duyuru", "ilan", "insan kaynak", "personel"]),
               "derinlik": 1, "max_takip": tarama.get("max_takip", 4), "metin_filtresi": True}
        try:
            adaylar = kaynak_tara(cfg, timeout=15)
            for a in adaylar:
                a.il, a.site = il, anahtar
            return anahtar, adaylar, None
        except Exception as e:
            return anahtar, [], str(e)

    tum, erisilemeyen = [], []
    with ThreadPoolExecutor(max_workers=16) as ex:
        for anahtar, adaylar, hata in ex.map(tek, isler):
            if hata:
                erisilemeyen.append(anahtar)
                continue
            ilk = anahtar not in durum.d["belediye_ilk"]
            for a in adaylar:
                a.ilk_tarama = ilk
            durum.d["belediye_ilk"].setdefault(anahtar, bugun().isoformat())
            tum.extend(adaylar)

    bulunamayan = [k for k, _, _ in liste(ayar) if not (adresler.get(k) or {}).get("url")]
    istatistik = {"toplam": len(liste(ayar)), "bulunan": len(isler),
                  "erisilemeyen": erisilemeyen, "bulunamayan": bulunamayan,
                  "tarih": bugun().isoformat()}
    return tum, istatistik
