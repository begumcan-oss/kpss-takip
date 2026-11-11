"""KPSS ilan takip sistemi — ana akış.

Kullanım:
    python -m takip.main --mod ana        # ana ilan siteleri
    python -m takip.main --mod belediye   # belediye siteleri
    python -m takip.main --mod hepsi
    python -m takip.main --mod ana --kuru # mesaj göndermeden dener
"""
import argparse
import logging
from concurrent.futures import ThreadPoolExecutor

from . import ayarlar, belediye, osym
from .eslestir import degerlendir, eski_mi, ilce_haritasi_yap
from .metin import norm
from .indir import Tarayici, ilan_metni
from .telegram import Telegram, e

log = logging.getLogger("takip")
MAX_DETAY = 120      # bir çalıştırmada okunacak en fazla yeni ilan
MAX_MESAJ = 40       # bir çalıştırmada gönderilecek en fazla mesaj
BASLIK = {0: "⭐ YÜKSEK ÖNCELİK", 1: "🔹 ORTA ÖNCELİK", 2: "▫️ GENEL KADRO", 3: "🔎 KONTROL EDİN"}


def mesaj_yap(aday, d, profil):
    en_iyi = min((k.seviye for k in d.kisiler), default=3)
    bas = BASLIK[en_iyi]
    if aday.kpsssiz:
        bas += " · KPSS'siz"
    s = [f"<b>{bas}</b>", f"🏛 {e(aday.baslik)}"]
    if d.iller:
        il = ", ".join(d.iller)
        s.append(f"📍 <b>{e(il)}</b> (öncelikli şehir)" if d.oncelikli_il else f"📍 {e(il)}")
    else:
        s.append("📍 İl belirtilmemiş")
    if d.son_basvuru:
        s.append(f"⏳ Son başvuru: {d.son_basvuru:%d.%m.%Y}")
    for k in d.kisiler:
        s.append(f"\n{k.kisi.get('emoji', '')} <b>{e(k.kisi['ad'])}</b>: {e(k.etiket)}")
        s.extend(f"   {e(n)}" for n in k.notlar)
    if d.kontrol_et:
        hepsi = "".join(k.get("emoji", "") for k in profil["kisiler"])
        s.append(f"\n{hepsi} Ayrıntılar otomatik okunamadı, ikiniz de kontrol edin.")
    s.extend(e(n) for n in d.ek_notlar)
    s.append(f"\n🔗 <a href=\"{e(aday.url)}\">İlana git</a>")
    s.append(f"<i>Kaynak: {e(aday.kaynak)}</i>")
    return "\n".join(s)


def _metinleri_getir(adaylar, tarayici):
    sonuc = {a.url: a.on_metin for a in adaylar if not a.detay}
    tarayicili = [a for a in adaylar if a.detay and a.render and a.tur != "osym"]
    duz = [a for a in adaylar if a.detay and not a.render and a.tur != "osym"]

    def getir(a):
        try:
            return a.url, ilan_metni(a.url) + " " + (a.on_metin or "")
        except Exception as ex:
            log.info("İlan okunamadı %s: %s", a.url, ex)
            return a.url, a.on_metin  # sayfa açılmazsa en azından RSS açıklamasıyla değerlendir

    with ThreadPoolExecutor(max_workers=10) as ex:
        for url, metin in ex.map(getir, duz):
            sonuc[url] = metin
    for a in tarayicili:
        try:
            sonuc[a.url] = ilan_metni(a.url, render=True, tarayici=tarayici) + " " + (a.on_metin or "")
        except Exception as ex:
            log.info("İlan okunamadı %s: %s", a.url, ex)
            sonuc[a.url] = a.on_metin
    return sonuc


def saglik_raporu(durum, tg):
    s = ayarlar.simdi()
    b = s.date().isoformat()
    if s.hour < 9 or durum.d.get("son_saglik") == b:
        return
    from datetime import timedelta
    dun = (s.date() - timedelta(days=1)).isoformat()
    gonderilen = durum.d["gunluk"].get(dun, 0)
    satirlar = ["🩺 <b>Günlük durum raporu</b>", f"• Dün gönderilen ilan: {gonderilen}"]
    hatalar = durum.d["son_hatalar"].get("ana", [])
    satirlar.append("• Sorunlu kaynaklar: " + (e(", ".join(hatalar)) if hatalar else "yok, hepsi çalışıyor"))
    bos = [k for k, v in durum.d["bos_sayac"].items() if v >= 24]
    if bos:
        satirlar.append("• Uzun süredir hiç ilan bulunamayanlar (yapısı değişmiş olabilir): " + e(", ".join(bos)))
    bd = durum.d.get("belediye_durum")
    if bd:
        satirlar.append(f"• Belediyeler: {bd['bulunan']}/{bd['toplam']} sitesi bulundu, "
                        f"son taramada {len(bd['erisilemeyen'])} site erişilemedi")
        if s.weekday() == 0 and bd["bulunamayan"]:
            satirlar.append("• Sitesi bulunamayanlar: " + e(", ".join(bd["bulunamayan"][:60])))
    tg.gonder("\n".join(satirlar))
    durum.d["son_saglik"] = b


def calistir(mod, kuru=False):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    profil = ayarlar.profiller()
    bel_ayar = ayarlar.belediyeler()
    durum = ayarlar.Durum()
    tg = Telegram(kuru=kuru)
    bugun = ayarlar.bugun()
    ilce_haritasi = ilce_haritasi_yap(bel_ayar)
    log.info("Profil yüklendi: %d kişi. Mod: %s", len(profil["kisiler"]), mod)

    if not durum.d.get("kuruldu"):
        adlar = " ve ".join(f"{k.get('emoji', '')} {k['ad']}" for k in profil["kisiler"])
        if tg.gonder(f"✅ <b>KPSS takip sistemi çalışmaya başladı</b>\n{e(adlar)} için uygun ilanlar buraya gelecek."):
            durum.d["kuruldu"] = bugun.isoformat()

    adaylar, tarayici = [], None
    if mod in ("ana", "hepsi"):
        tarayici = Tarayici()
        hatalar = []
        for kaynak in ayarlar.kaynaklar():
            try:
                bulunan = ayarlar_kaynak_tara(kaynak, tarayici)
                log.info("%s: %d olası ilan", kaynak["ad"], len(bulunan))
                durum.d["bos_sayac"][kaynak["ad"]] = 0 if bulunan else durum.d["bos_sayac"].get(kaynak["ad"], 0) + 1
                adaylar.extend(bulunan)
            except Exception as ex:
                log.warning("%s: %s", kaynak["ad"], ex)
                neden = str(ex).split("(")[-1].rstrip(")") if "(" in str(ex) else ""
                hatalar.append(f"{kaynak['ad']} ({neden})" if neden else kaynak["ad"])
        durum.d["son_hatalar"]["ana"] = hatalar

    if mod in ("belediye", "hepsi"):
        bulunan, istatistik = belediye.tara_hepsi(bel_ayar, durum)
        log.info("Belediyeler: %d/%d site tarandı, %d olası ilan",
                 istatistik["bulunan"] - len(istatistik["erisilemeyen"]), istatistik["toplam"], len(bulunan))
        durum.d["belediye_durum"] = istatistik
        adaylar.extend(bulunan)

    tekil, gorulen_url = [], set()
    for a in adaylar:
        if a.url in gorulen_url or durum.goruldu_mu(a.anahtarlar()):
            continue
        gorulen_url.add(a.url)
        tekil.append(a)
    log.info("Yeni olası ilan: %d", len(tekil))
    tekil = tekil[:MAX_DETAY]

    metinler = _metinleri_getir(tekil, tarayici)
    gonderilecek = []
    for a in tekil:
        if a.tur == "osym":
            bn = norm(a.baslik)
            if "ekpss" in bn or "engelli" in bn or eski_mi(a.baslik, bugun, gun=30):
                durum.isaretle(a.anahtarlar())
                continue
            gonderilecek.append(((-1, 0), a, osym.isle(a, profil)))
            continue
        metin = metinler.get(a.url)
        if metin is None:
            k = a.anahtarlar()[0]
            durum.d["hata_sayac"][k] = durum.d["hata_sayac"].get(k, 0) + 1
            if durum.d["hata_sayac"][k] >= 3:
                durum.isaretle(a.anahtarlar())
                durum.d["hata_sayac"].pop(k, None)
            continue
        d = degerlendir(a, metin, profil, bugun, ilce_haritasi)
        if not d.gonder or (a.ilk_tarama and d.son_basvuru is None):
            durum.isaretle(a.anahtarlar())
            continue
        en_iyi = min((k.seviye for k in d.kisiler), default=3)
        gonderilecek.append(((en_iyi, 0 if d.oncelikli_il else 1), a, mesaj_yap(a, d, profil)))

    gonderilecek.sort(key=lambda x: x[0])
    sayi = 0
    for _, a, metin in gonderilecek[:MAX_MESAJ]:
        if tg.gonder(metin):
            durum.isaretle(a.anahtarlar())
            sayi += 1
    if len(gonderilecek) > MAX_MESAJ:
        log.info("%d ilan bir sonraki çalıştırmaya kaldı", len(gonderilecek) - MAX_MESAJ)
    durum.gunluk_say(sayi)
    log.info("Gönderilen ilan mesajı: %d", sayi)

    if tarayici:
        tarayici.kapat()
    saglik_raporu(durum, tg)
    durum.kaydet()


def ayarlar_kaynak_tara(kaynak, tarayici):
    from .tarayici import kaynak_tara
    return kaynak_tara(kaynak, tarayici=tarayici, hata_ayiklama_klasoru=ayarlar.KOK / "debug")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--mod", default="ana", choices=["ana", "belediye", "hepsi"])
    p.add_argument("--kuru", action="store_true", help="Telegram'a göndermeden dene")
    arg = p.parse_args()
    calistir(arg.mod, arg.kuru)
