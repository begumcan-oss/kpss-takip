"""Bir sitenin sayfalarındaki bağlantıları tarayıp olası ilanları bulan genel tarayıcı.

Her kaynağın ayarı config/kaynaklar.yaml dosyasındadır. Bir site yapısını
değiştirirse çoğu zaman sadece o dosyayı düzeltmek yeterli olur.
"""
import logging
import pathlib
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .indir import html_getir
from .metin import anahtar, norm, personel_baglantisi_mi, HARIC_BAGLANTI

log = logging.getLogger("takip")


@dataclass
class Aday:
    baslik: str
    url: str
    kaynak: str
    tur: str = "ana"          # ana / belediye / osym
    il: str = None            # belediye ilanlarında belediyenin ili
    render: bool = False
    kpsssiz: bool = False
    ilk_tarama: bool = False  # site ilk kez taranıyorsa eski duyurular gönderilmez
    site: str = ""

    def anahtarlar(self):
        temiz = self.url.split("#")[0].rstrip("/")
        k = [anahtar("u", temiz)]
        b = norm(self.baslik)
        if len(b) >= 20:
            k.append(anahtar("b", self.kaynak, b))
        return k


def _baglanti_metni(a):
    t = a.get_text(" ", strip=True)
    if len(t) < 12:
        ust = a.find_parent(["tr", "li", "article", "div"])
        if ust is not None:
            ut = ust.get_text(" ", strip=True)
            if 0 < len(ut) <= 300:
                t = ut
    if not t:
        t = a.get("title") or ""
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s*(detay|detaylar|incele|tıklayınız|devamı|devamını oku|ilana git)\s*$", "", t, flags=re.I)
    return t[:250]


def baglantilar(taban, html):
    soup = BeautifulSoup(html, "lxml")
    cikti, gorulen = [], set()
    for a in soup.find_all("a", href=True):
        h = a["href"].strip()
        if not h or h.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        u = urljoin(taban, h).split("#")[0]
        if u in gorulen or not u.startswith("http"):
            continue
        gorulen.add(u)
        cikti.append((_baglanti_metni(a), u))
    return cikti


def _alan(u):
    h = urlparse(u).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def kaynak_tara(ayar, tarayici=None, hata_ayiklama_klasoru=None, timeout=25):
    """Bir kaynağı tarar, Aday listesi döndürür. Hiçbir sayfa açılamazsa hata fırlatır."""
    ad = ayar["ad"]
    render = ayar.get("render", False)
    aday_desen = re.compile(ayar["aday_url_desen"], re.I) if ayar.get("aday_url_desen") else None
    takip_desen = re.compile(ayar["takip_url_desen"], re.I) if ayar.get("takip_url_desen") else None
    takip_kel = [norm(k) for k in ayar.get("takip_kelimeleri", [])]
    ozel = [norm(k) for k in ayar.get("aday_metin_kelimeleri", [])]
    metin_filtresi = ayar.get("metin_filtresi", True)
    derinlik = ayar.get("derinlik", 1)
    max_takip = ayar.get("max_takip", 6)

    kuyruk = [(u, 0) for u in ayar["baslangic"]]
    ziyaret, adaylar = set(), {}
    acilan, takip_sayisi = 0, 0
    kok_alanlar = {_alan(u) for u in ayar["baslangic"]}

    while kuyruk:
        url, d = kuyruk.pop(0)
        if url in ziyaret:
            continue
        ziyaret.add(url)
        try:
            son_url, html = html_getir(url, render=render, tarayici=tarayici, timeout=timeout)
        except Exception as e:
            log.info("%s: %s açılamadı (%s)", ad, url, e)
            continue
        acilan += 1
        if hata_ayiklama_klasoru and d == 0:
            p = pathlib.Path(hata_ayiklama_klasoru)
            p.mkdir(parents=True, exist_ok=True)
            (p / f"{re.sub(r'[^a-z0-9]+', '_', ad.lower())}.html").write_text(html, encoding="utf-8")

        for metin, u in baglantilar(son_url, html):
            mn = norm(metin)
            if ozel:
                aday_mi = all(k in mn for k in ozel)
            else:
                url_uygun = bool(aday_desen.search(u)) if aday_desen else True
                if metin_filtresi:
                    metin_uygun = personel_baglantisi_mi(mn)
                else:
                    metin_uygun = not any(h in mn for h in HARIC_BAGLANTI)
                aday_mi = url_uygun and metin_uygun
            if aday_mi:
                if u not in adaylar:
                    adaylar[u] = Aday(baslik=metin or u, url=u, kaynak=ad,
                                      tur=ayar.get("tur", "ana"), render=render,
                                      kpsssiz=ayar.get("kpsssiz", False))
                continue
            if d < derinlik and takip_sayisi < max_takip and u not in ziyaret:
                ayni_site = _alan(u) in kok_alanlar or any(_alan(u).endswith(k) for k in kok_alanlar)
                takip_et = (takip_desen and takip_desen.search(u)) or (
                    takip_kel and any(k in mn for k in takip_kel))
                if ayni_site and takip_et:
                    kuyruk.append((u, d + 1))
                    takip_sayisi += 1

    if acilan == 0:
        raise RuntimeError("siteye ulaşılamadı")
    return list(adaylar.values())
