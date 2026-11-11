"""ÖSYM'de yeni bir KPSS tercih kılavuzu yayımlandığında PDF'i indirip ön tarama yapar."""
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .eslestir import HERHANGI
from .indir import http_get, pdf_metni
from .metin import norm
from .telegram import e

log = logging.getLogger("takip")


def _pdf_baglantilari(url):
    r = http_get(url)
    if "pdf" in r.headers.get("content-type", "").lower():
        return [url], r.content
    soup = BeautifulSoup(r.text, "lxml")
    linkler = []
    for a in soup.find_all("a", href=True):
        u = urljoin(r.url, a["href"])
        t = norm(a.get_text(" ", strip=True) + " " + u)
        if ".pdf" in u.lower() and ("klvz" in t or "kilavuz" in t or "tablo" in t):
            linkler.append(u)
    return linkler[:3], None


def analiz(metin, profil):
    hedef_iller = [norm(i) for i in profil["iller"]["oncelikli"] + profil["iller"]["diger"]]
    kod_aciklama = {}
    for m in re.finditer(r"(?m)^\s*(\d{4})\s+(.{10,400})$", metin):
        kod_aciklama.setdefault(m.group(1), norm(m.group(2)))
    satirlar = [s for s in metin.splitlines() if s.strip()]
    sonuc = []
    for kisi in profil["kisiler"]:
        yuksek = [norm(k) for k in kisi.get("yuksek_oncelik", [])]
        haric = [norm(h) for h in kisi.get("haric_ifadeler", [])]
        gruplar = {"Bölümüne özel": [], "Genel kadro": []}
        for kod, acik in kod_aciklama.items():
            temiz = acik
            for h in haric:
                temiz = temiz.replace(h, " ")
            if any(k in temiz for k in yuksek):
                gruplar["Bölümüne özel"].append(kod)
            elif any(re.search(d, acik) for d in HERHANGI[kisi["seviye"]]):
                gruplar["Genel kadro"].append(kod)
        parcalar = []
        for grup, kodlar in gruplar.items():
            if not kodlar:
                continue
            desen = re.compile(r"\b(" + "|".join(kodlar) + r")\b")
            eslesen = [s for s in satirlar if desen.search(s)
                       and any(il in norm(s) for il in hedef_iller)]
            parca = f"• {grup} (kod {', '.join(kodlar[:6])}): şehirlerinizde ~{len(eslesen)} satır"
            for s in eslesen[:4]:
                parca += f"\n   – {e(s.strip()[:140])}"
            parcalar.append(parca)
        sonuc.append((kisi, parcalar))
    return sonuc


def isle(aday, profil):
    """Telegram mesaj metni döndürür (her durumda en azından bir duyuru mesajı)."""
    mesaj = (f"🔔 <b>ÖSYM: KPSS tercih kılavuzu duyurusu</b>\n🏛 {e(aday.baslik)}\n"
             f"🔗 <a href=\"{e(aday.url)}\">Duyuruya git</a>")
    try:
        linkler, icerik = _pdf_baglantilari(aday.url)
        metin = ""
        if icerik:
            metin = pdf_metni(icerik, max_sayfa=3000)
        for u in linkler:
            if icerik:
                break
            try:
                metin += "\n" + pdf_metni(http_get(u, timeout=120).content, max_sayfa=3000)
            except Exception as ex:
                log.warning("Kılavuz indirilemedi: %s", ex)
        if not metin.strip():
            return mesaj + "\n\nKılavuz otomatik okunamadı, lütfen kendiniz kontrol edin."
        for kisi, parcalar in analiz(metin, profil):
            mesaj += f"\n\n{kisi.get('emoji', '')} <b>{e(kisi['ad'])}</b>"
            if not kisi.get("mezun", True):
                mesaj += "\n🎓 Tercih için mezun olmuş olmak gerekir"
            mesaj += "\n" + ("\n".join(parcalar) if parcalar else "• Otomatik taramada uygun kod bulunamadı")
        mesaj += "\n\n<i>Bu otomatik bir ön taramadır. Kesin bilgi için kılavuzu kontrol edin.</i>"
    except Exception as ex:
        log.warning("ÖSYM analizi başarısız: %s", ex)
        mesaj += "\n\nKılavuz otomatik okunamadı, lütfen kendiniz kontrol edin."
    return mesaj
