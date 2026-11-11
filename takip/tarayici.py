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
from .metin import anahtar, kisa_hata, norm, personel_baglantisi_mi, HARIC_BAGLANTI

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
    on_metin: str = None      # RSS açıklaması ya da sayfadan ayrılmış ilan metni
    detay: bool = True        # False ise ilan sayfası ayrıca açılmaz, on_metin kullanılır
    surum: str = ""           # kaynak ayarındaki anahtar_surumu

    def anahtarlar(self):
        temiz = self.url.split("#")[0].rstrip("/")
        k = [anahtar("u" + self.surum, temiz)]
        b = norm(self.baslik)
        if len(b) >= 20:
            k.append(anahtar("b" + self.surum, self.kaynak, b))
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


def _kaydet(klasor, ad, ek, icerik):
    if not klasor:
        return
    p = pathlib.Path(klasor)
    p.mkdir(parents=True, exist_ok=True)
    yol = p / f"{re.sub(r'[^a-z0-9]+', '_', ad.lower())}{ek}"
    if isinstance(icerik, bytes):
        yol.write_bytes(icerik)
    else:
        yol.write_text(icerik, encoding="utf-8")


def rss_tara(ayar, timeout=25, hata_ayiklama_klasoru=None):
    """RSS/Atom beslemesindeki her öğeyi aday ilan olarak döndürür."""
    from .indir import http_get
    adaylar, son_hata = [], ""
    for url in ayar["rss"]:
        try:
            r = http_get(url, timeout=timeout)
        except Exception as e:
            son_hata = kisa_hata(e)
            continue
        icerik = r.content
        _kaydet(hata_ayiklama_klasoru, ayar["ad"], "_rss.txt", icerik)
        if b"<item" not in icerik and b"<entry" not in icerik:
            # RSS bağlantısını veren bir sayfa olabilir: içindeki besleme adresini bul
            soup = BeautifulSoup(r.text, "lxml")
            bag = [urljoin(r.url, a["href"]) for a in soup.find_all("a", href=True)
                   if "rss" in a["href"].lower() or "xml" in a["href"].lower()]
            bag += re.findall(r"https?://[^\s\"'<>]+(?:rss|xml)[^\s\"'<>]*", r.text, re.I)
            for b in bag[:3]:
                try:
                    r2 = http_get(b, timeout=timeout)
                    if b"<item" in r2.content or b"<entry" in r2.content:
                        icerik = r2.content
                        break
                except Exception:
                    continue
        soup = BeautifulSoup(icerik, "xml")
        for it in soup.find_all(["item", "entry"]):
            baslik = (it.find("title").get_text(" ", strip=True) if it.find("title") else "")
            link_el = it.find("link")
            link = ""
            if link_el is not None:
                link = link_el.get("href") or link_el.get_text(strip=True)
            aciklama = ""
            for etiket in ("description", "summary", "content"):
                el = it.find(etiket)
                if el is not None:
                    aciklama = el.get_text(" ", strip=True)
                    if "<" in aciklama:
                        aciklama = BeautifulSoup(aciklama, "lxml").get_text(" ", strip=True)
                    break
            if baslik and link:
                kategori = it.find("category")
                if kategori is not None:
                    aciklama = f"{kategori.get_text(' ', strip=True)}. {aciklama}"
                adaylar.append(Aday(baslik=baslik[:250], url=link, kaynak=ayar["ad"],
                                    tur=ayar.get("tur", "ana"), render=ayar.get("render", False),
                                    kpsssiz=ayar.get("kpsssiz", False), on_metin=aciklama,
                                    surum=str(ayar.get("anahtar_surumu", ""))))
    if not adaylar and son_hata:
        raise RuntimeError(f"siteye ulaşılamadı ({son_hata})")
    return adaylar


_RG_ILAN_NO = re.compile(r"\n\s*\d{3,6}/\d{1,3}-\d{1,3}\s*(?=\n)")
_RG_BASLIK = re.compile(r"(?m)^[^\n]{5,160}?(?:ndan|nden|dan|den|tan|ten):\s*$")


def ilan_sayfasini_bol(url, kaynak, timeout=30):
    """Resmî Gazete'nin 'Çeşitli İlanlar' gibi çok ilanlı sayfasını tek tek ilanlara böler."""
    from .indir import http_get
    r = http_get(url, timeout=timeout)
    soup = BeautifulSoup(r.text, "lxml")
    alt_ilanlar = []
    for metin_, u in baglantilar(r.url, r.text):
        if re.search(r"\d{8}-\d+-\d+\.(htm|pdf)", u):
            alt_ilanlar.append(Aday(baslik=metin_ or u, url=u, kaynak=kaynak))
    if alt_ilanlar:
        log.info("%s: bölümde %d ayrı ilan bağlantısı var", kaynak, len(alt_ilanlar))
        return alt_ilanlar
    for t in soup(["script", "style"]):
        t.decompose()
    metin = re.sub(r"[ \t\xa0]+", " ", soup.get_text("\n"))
    metin = re.sub(r"\n\s*\n+", "\n", metin)
    parcalar = _RG_ILAN_NO.split(metin)
    if len(parcalar) < 2:
        basliklar = [m.start() for m in _RG_BASLIK.finditer(metin)]
        parcalar = [metin[a:b] for a, b in zip(basliklar, basliklar[1:] + [len(metin)])] or [metin]
    log.info("%s: sayfa %d parçaya bölündü", kaynak, len(parcalar))
    adaylar = []
    for i, p in enumerate(parcalar):
        p = p.strip()
        if len(p) < 150:
            continue
        m = _RG_BASLIK.search(p)
        if m:
            devam = re.sub(r"\s+", " ", p[m.end():m.end() + 160]).strip()
            baslik = f"{m.group(0).strip()} {devam[:110]}…"
        else:
            baslik = re.sub(r"\s+", " ", p[:120])
        adaylar.append(Aday(baslik=baslik, url=f"{r.url}#ilan-{i + 1}", kaynak=kaynak,
                            on_metin=p[:60000], detay=False))
    return adaylar


def kaynak_tara(ayar, tarayici=None, hata_ayiklama_klasoru=None, timeout=25):
    """Bir kaynağı tarar, Aday listesi döndürür. Hiçbir sayfa açılamazsa hata fırlatır."""
    if ayar.get("rss"):
        return rss_tara(ayar, timeout, hata_ayiklama_klasoru)
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
    acilan, takip_sayisi, son_hata = 0, 0, ""
    kok_alanlar = {_alan(u) for u in ayar["baslangic"]}

    while kuyruk:
        url, d = kuyruk.pop(0)
        if url in ziyaret:
            continue
        ziyaret.add(url)
        try:
            son_url, html = html_getir(url, render=render, tarayici=tarayici, timeout=timeout,
                                       bekle=ayar.get("bekle", 2500))
        except Exception as e:
            son_hata = kisa_hata(e)
            log.info("%s: %s açılamadı (%s)", ad, url, e)
            sonuc = tarayici.ac(url) if (tarayici is not None and not render) else None
            if not sonuc:
                continue
            son_url, html = sonuc
            log.info("%s: tarayıcıyla açıldı", ad)
        acilan += 1
        if hata_ayiklama_klasoru and d == 0:
            p = pathlib.Path(hata_ayiklama_klasoru)
            p.mkdir(parents=True, exist_ok=True)
            (p / f"{re.sub(r'[^a-z0-9]+', '_', ad.lower())}.html").write_text(html, encoding="utf-8")
            if render and tarayici is not None and getattr(tarayici, "son_istekler", None):
                _kaydet(p, ad, "_istekler.txt", "\n".join(tarayici.son_istekler))

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
                                      kpsssiz=ayar.get("kpsssiz", False),
                                      surum=str(ayar.get("anahtar_surumu", "")))
                continue
            if d < derinlik and takip_sayisi < max_takip and u not in ziyaret:
                ayni_site = _alan(u) in kok_alanlar or any(_alan(u).endswith(k) for k in kok_alanlar)
                takip_et = (takip_desen and takip_desen.search(u)) or (
                    takip_kel and any(k in mn for k in takip_kel))
                if ayni_site and takip_et:
                    kuyruk.append((u, d + 1))
                    takip_sayisi += 1

    if acilan == 0:
        raise RuntimeError(f"siteye ulaşılamadı ({son_hata or 'bilinmiyor'})")
    if ayar.get("bolumle"):
        bolunmus = []
        for a in adaylar.values():
            try:
                if hata_ayiklama_klasoru:
                    from .indir import http_get
                    _kaydet(hata_ayiklama_klasoru, ad, "_bolum.html", http_get(a.url).text)
                bolunmus.extend(ilan_sayfasini_bol(a.url, ad))
            except Exception as e:
                log.info("%s: %s bölünemedi (%s)", ad, a.url, e)
        return bolunmus
    return list(adaylar.values())
