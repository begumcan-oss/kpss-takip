"""İlan metnini kişi profilleriyle karşılaştırır, öncelik ve notları belirler."""
import re
from dataclasses import dataclass, field
from datetime import date

from .metin import AKADEMIK, PERSONEL_KELIMELERI, norm

ILLER_81 = [
    "Adana", "Adıyaman", "Afyonkarahisar", "Ağrı", "Aksaray", "Amasya", "Ankara", "Antalya",
    "Ardahan", "Artvin", "Aydın", "Balıkesir", "Bartın", "Batman", "Bayburt", "Bilecik",
    "Bingöl", "Bitlis", "Bolu", "Burdur", "Bursa", "Çanakkale", "Çankırı", "Çorum", "Denizli",
    "Diyarbakır", "Düzce", "Edirne", "Elazığ", "Erzincan", "Erzurum", "Eskişehir", "Gaziantep",
    "Giresun", "Gümüşhane", "Hakkari", "Hatay", "Iğdır", "Isparta", "İstanbul", "İzmir",
    "Kahramanmaraş", "Karabük", "Karaman", "Kars", "Kastamonu", "Kayseri", "Kilis", "Kırıkkale",
    "Kırklareli", "Kırşehir", "Kocaeli", "Konya", "Kütahya", "Malatya", "Manisa", "Mardin",
    "Mersin", "Muğla", "Muş", "Nevşehir", "Niğde", "Ordu", "Osmaniye", "Rize", "Sakarya",
    "Samsun", "Şanlıurfa", "Siirt", "Sinop", "Sivas", "Şırnak", "Tekirdağ", "Tokat", "Trabzon",
    "Tunceli", "Uşak", "Van", "Yalova", "Yozgat", "Zonguldak",
]

# Başka anlamları da olan / başka illerde de bulunan ilçe adları il tespitinde kullanılmaz
BELIRSIZ_ILCELER = {
    "merkez", "marmara", "akdeniz", "saray", "kemer", "aksu", "yenice", "yenisehir", "termal",
    "kiraz", "balya", "keles", "kinik", "kosk", "havsa", "meric", "enez", "vize", "mut", "ula",
    "can", "gomec", "fatih", "konak", "kemalpasa", "yildirim", "osmangazi", "nilufer", "erdemli",
    "edremit", "gonen", "ergene", "cesme", "menemen", "tire", "dikili", "selcuk", "menderes",
    "bayindir", "kuyucak", "kas", "kepez", "elmali", "aydincik", "saricam", "karatas",
    "imamoglu", "aladag", "adalar", "avcilar", "bagcilar", "gaziosmanpasa", "bahcelievler",
    "besiktas", "korfez", "erenler", "hendek", "kaynarca", "sogutlu", "kartal", "maltepe",
    "tuzla", "ceyhan", "seyhan", "karsiyaka", "altinova", "armutlu", "kestel", "biga",
}

AYLAR = {"ocak": 1, "subat": 2, "mart": 3, "nisan": 4, "mayis": 5, "haziran": 6, "temmuz": 7,
         "agustos": 8, "eylul": 9, "ekim": 10, "kasim": 11, "aralik": 12}
_TARIH_SAYI = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b")
_TARIH_YAZI = re.compile(r"\b(\d{1,2})\s+(" + "|".join(AYLAR) + r")\s+(20\d{2})\b")

ONLISANS = re.compile(r"on ?lisans")
HERHANGI = {
    "lisans": [r"herhangi bir lisans", r"lisans programlarinin herhangi", r"en az lisans",
               r"tum lisans programlari", r"lisans duzeyinde herhangi"],
    "onlisans": [r"herhangi bir on ?lisans", r"on ?lisans programlarinin herhangi",
                 r"en az on ?lisans", r"tum on ?lisans programlari", r"on ?lisans duzeyinde herhangi"],
}
DIGER_KADROLAR = ["memur", "uzman", "teknisyen", "tekniker", "muhendis", "sekreter", "sofor",
                  "zabita", "itfaiye", "koruma", "guvenlik gorevlisi", "programci", "veri hazirlama",
                  "bilgisayar isletmeni", "mimar", "tasarim", "is sagligi", "avukat", "ressam"]


# Ayrıntısı okunamayan ilanlarda başlıkta geçerse "size uymuyor" sayılacak ifadeler
BASLIK_UYUMSUZ = ["uzman yardimci", "denetmen yardimci", "mufettis yardimci", "yurt disi", "yurtdisi egitim",
                  "bilisim personel", "avukat", "kutuphaneci", "programci", "cozumleyici", "kalkinma ajansi",
                  "hemsire", "ebe ", "doktor", "hekim", "eczaci", "veteriner", "psikolog", "ogretmen",
                  "pilot", "astsubay", "subay", "uzman erbas", "polis", "bekci", "guvenlik korucusu"]


@dataclass
class KisiSonuc:
    kisi: dict
    seviye: int          # 0 yüksek, 1 orta, 2 genel
    etiket: str
    notlar: list = field(default_factory=list)


@dataclass
class Degerlendirme:
    gonder: bool
    neden: str = ""
    kisiler: list = field(default_factory=list)
    iller: list = field(default_factory=list)
    oncelikli_il: bool = False
    son_basvuru: date = None
    kontrol_et: bool = False
    ek_notlar: list = field(default_factory=list)


def _tarihler(s):
    for g, a, y in _TARIH_SAYI.findall(s):
        try:
            yield date(int(y), int(a), int(g))
        except ValueError:
            pass
    for g, ay, y in _TARIH_YAZI.findall(s):
        try:
            yield date(int(y), AYLAR[ay], int(g))
        except ValueError:
            pass


_EN_AYLAR = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
             "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}


def baslik_tarihi(baslik):
    """Başlıktaki en yeni tarihi (yoksa yılı) döndürür."""
    bn = norm(baslik)
    tarihler = list(_tarihler(bn))
    for g, ay, y in re.findall(r"\b(\d{1,2})\s+(" + "|".join(_EN_AYLAR) + r")\s+(20\d{2})\b", bn):
        try:
            tarihler.append(date(int(y), _EN_AYLAR[ay], int(g)))
        except ValueError:
            pass
    if tarihler:
        return max(tarihler)
    yillar = [int(y) for y in re.findall(r"\b(20\d{2})\b", bn)]
    return date(max(yillar), 12, 31) if yillar else None


def eski_mi(baslik, bugun, gun=60):
    from datetime import timedelta
    t = baslik_tarihi(baslik)
    return bool(t and t < bugun - timedelta(days=gun))


def son_basvuru_bul(tn, bugun=None):
    from datetime import timedelta
    ust = (bugun + timedelta(days=240)) if bugun else None

    def topla(desen, once, sonra):
        bulunan = []
        for m in re.finditer(desen, tn):
            pencere = tn[max(0, m.start() - once): m.end() + sonra]
            bulunan += [d for d in _tarihler(pencere) if not ust or d <= ust]
        return bulunan

    tarihler = topla(r"son basvuru", 40, 120) or topla(r"basvuru", 120, 160)
    return max(tarihler) if tarihler else None


def lisans_var(tn):
    for m in re.finditer(r"lisans", tn):
        once = tn[max(0, m.start() - 7): m.start()]
        if once.endswith("on") or once.endswith("on ") or once.endswith("yuksek ") or once.endswith("yuksek"):
            continue
        sonra = tn[m.end(): m.end() + 4]
        if sonra.startswith("ustu"):
            continue
        return True
    return False


def il_bul(tn, il_listesi, ilce_haritasi):
    bulunan = set()
    for il in il_listesi:
        if re.search(r"\b" + re.escape(norm(il)) + r"\b", tn):
            bulunan.add(il)
    for ilce_n, il in ilce_haritasi.items():
        if re.search(r"\b" + re.escape(ilce_n) + r"\b", tn):
            bulunan.add(il)
    return bulunan


def ilce_haritasi_yap(belediye_ayar):
    harita = {}
    for il, ilceler in (belediye_ayar or {}).get("iller", {}).items():
        for ilce in ilceler:
            n = norm(ilce)
            if len(n) >= 5 and n not in BELIRSIZ_ILCELER:
                harita[n] = il
    return harita


def _puan_turleri(tn):
    turler = set()
    for m in re.finditer(r"\bkpss\s*-?\s*p\s?(\d{1,3})\b|\bkpssp(\d{1,3})\b|\bp\s?(\d{1,3})\s+puan", tn):
        t = next(g for g in m.groups() if g)
        turler.add(f"P{int(t)}")
    return turler


def _asgari_puan(tn):
    sayilar = []
    desenler = [r"(?:en az|asgari|minimum)\s*(\d{2}(?:[.,]\d+)?)\s*(?:\(.*?\)\s*)?puan",
                r"(\d{2}(?:[.,]\d+)?)\s*(?:ve|veya)\s*uzeri\s*puan",
                r"puan[^.]{0,40}?(\d{2}(?:[.,]\d+)?)\s*(?:ve|veya)\s*uzeri"]
    for d in desenler:
        for m in re.finditer(d, tn):
            try:
                v = float(m.group(1).replace(",", "."))
                if 40 <= v <= 100:
                    sayilar.append(v)
            except ValueError:
                pass
    return min(sayilar) if sayilar else None


def _yas_siniri(tn):
    sinirlar = [int(x) for x in re.findall(r"(\d{2})\s*yasini\s*(?:doldurmamis|bitirmemis)", tn)]
    sinirlar += [int(x) for x in re.findall(r"(\d{2})\s*yasindan\s*gun\s*almamis", tn)]
    sinirlar = [s for s in sinirlar if 18 <= s <= 65]
    return max(sinirlar) if sinirlar else None


def _askerlik_sarti(tn):
    for m in re.finditer(r"askerli[a-z]*\s+(?:hizmetini\s+)?(?:yapmis|tamamlamis)", tn):
        pencere = tn[m.start(): m.end() + 120]
        if re.search(r"ertelen|tecil|muaf|yedek sinif", pencere):
            continue
        return True
    return False


def _dil_notu(tn):
    m = re.search(r"\b(yds|e-yds|yokdil|kpds|uds|toefl|ielts)\b", tn)
    if not m and "yabanci dil" not in tn:
        return None
    if m:
        p = re.search(r"\b(yds|e-yds|yokdil|kpds|uds)\b[^0-9]{0,40}?(\d{2,3})\b", tn)
        if p and 30 <= int(p.group(2)) <= 100:
            return f"{p.group(1).upper()} en az {p.group(2)} puan"
        return m.group(1).upper()
    return "yabancı dil şartı geçiyor"


def _ehliyet_siniflari(tn):
    if "surucu belgesi" not in tn and "ehliyet" not in tn:
        return None
    siniflar = set(re.findall(
        r"\(?\b(a1|a2|b1|be|c1e|c1|ce|d1e|d1|de|a|b|c|d|f|g|m)\b\)?\s*sinif", tn))
    return {s.upper() for s in siniflar}


def _herhangi(tn, seviye):
    return any(re.search(d, tn) for d in HERHANGI[seviye])


def kisi_degerlendir(kisi, tn, bilgi):
    seviye = kisi["seviye"]
    lis, onl = bilgi["lisans"], bilgi["onlisans"]
    seviye_var = lis if seviye == "lisans" else onl
    hic_seviye_yok = not lis and not onl

    tn_temiz = tn
    for h in kisi.get("haric_ifadeler", []):
        tn_temiz = tn_temiz.replace(norm(h), " ")

    yuksek = [norm(k) for k in kisi.get("yuksek_oncelik", [])]
    orta = [norm(k) for k in kisi.get("orta_oncelik", [])]
    notlar, sonuc_seviye = [], None

    if any(k in tn_temiz for k in yuksek) and (seviye_var or hic_seviye_yok):
        sonuc_seviye = 0
    elif any(k in tn for k in yuksek) and (seviye_var or hic_seviye_yok):
        sonuc_seviye = 1
        notlar.append("⚠️ Bölüm adı tam olarak seninki olmayabilir, kontrol et")
    elif any(k in tn for k in orta) and (seviye_var or hic_seviye_yok):
        sonuc_seviye = 1
    elif kisi.get("genel_kadro", True) and _herhangi(tn, seviye):
        sonuc_seviye = 2

    if sonuc_seviye is None:
        return None

    etiketler = kisi.get("etiketler", {})
    etiket = {0: etiketler.get("yuksek", "⭐ Yüksek öncelik"),
              1: etiketler.get("orta", "🔹 Orta öncelik"),
              2: etiketler.get("genel", "▫️ Genel kadro")}[sonuc_seviye]

    # Notlar
    if not kisi.get("mezun", True) and "mezun" in tn:
        notlar.append("🎓 Mezuniyet şartı var (başvuru tarihine kadar mezun olmak gerekebilir)")

    puanlar = {k.upper(): float(v) for k, v in (kisi.get("puanlar") or {}).items()}
    turler = bilgi["puan_turleri"]
    if turler and puanlar and not (turler & set(puanlar)):
        notlar.append(f"⚠️ İstenen puan türü: {', '.join(sorted(turler))} (sende bu tür yok)")
    if bilgi["asgari_puan"] and puanlar:
        ortak = turler & set(puanlar)
        puan = max(puanlar[t] for t in ortak) if ortak else max(puanlar.values())
        if puan < bilgi["asgari_puan"]:
            notlar.append(f"⚠️ Asgari puan şartı {bilgi['asgari_puan']:g} görünüyor, puanın {puan:.2f}".replace(".", ","))

    dil = bilgi["dil"]
    if dil:
        ek = f" ({kisi['dil']})" if kisi.get("dil") else ""
        notlar.append(f"🌐 Dil belgesi isteniyor: {dil}{ek}")

    siniflar = bilgi["ehliyet"]
    if siniflar is not None:
        sahip = {s.upper() for s in kisi.get("ehliyet", [])}
        if siniflar:
            var = sorted(siniflar & sahip)
            yok = sorted(siniflar - sahip)
            parca = []
            if var:
                parca.append(f"{', '.join(var)} sende var")
            if yok:
                parca.append(f"{', '.join(yok)} sende yok")
            notlar.append(f"🚗 Ehliyet isteniyor: {', '.join(sorted(siniflar))} ({'; '.join(parca)})")
        else:
            notlar.append(f"🚗 Sürücü belgesi isteniyor (sende {', '.join(sorted(sahip)) or 'yok'})")

    if kisi.get("cinsiyet") == "erkek" and kisi.get("askerlik") != "yapti" and bilgi["askerlik"]:
        notlar.append("🪖 Askerliğini yapmış olmak isteniyor, tecilli durum yetmeyebilir")

    yas = kisi.get("yas_ust")
    if yas and bilgi["yas_siniri"] and yas >= bilgi["yas_siniri"]:
        notlar.append(f"⚠️ Yaş sınırı {bilgi['yas_siniri']} görünüyor")

    if kisi.get("cinsiyet") == "kadin" and bilgi["sadece_erkek"]:
        notlar.append("⚠️ İlanda erkek aday şartı geçiyor (bazı kadrolar için olabilir)")
    if kisi.get("cinsiyet") == "erkek" and bilgi["sadece_kadin"]:
        notlar.append("⚠️ İlanda kadın aday şartı geçiyor (bazı kadrolar için olabilir)")

    return KisiSonuc(kisi=kisi, seviye=sonuc_seviye, etiket=etiket, notlar=notlar)


def degerlendir(aday, metin, profil, bugun, ilce_haritasi):
    baslik_n = norm(aday.baslik)
    tn = norm(f"{aday.baslik} {metin}")

    if any(k in baslik_n for k in AKADEMIK):
        return Degerlendirme(False, "akademik ilan")
    if eski_mi(aday.baslik, bugun):
        return Degerlendirme(False, "eski ilan")
    if not any(k in tn for k in PERSONEL_KELIMELERI):
        return Degerlendirme(False, "personel ilanı değil")

    ek_notlar = []
    haric = [norm(h) for h in profil.get("haric_kadrolar", ["destek personeli"])]
    for h in haric:
        if h in tn:
            kalan = tn.replace(h, " ")
            if not any(k in kalan for k in DIGER_KADROLAR):
                return Degerlendirme(False, f"sadece {h}")
            ek_notlar.append("ℹ️ İlanda destek personeli kadroları da var, onlar hariç tutuldu")

    il_cfg = profil["iller"]
    hedef = list(il_cfg["oncelikli"]) + list(il_cfg["diger"])
    bulunan = il_bul(tn, ILLER_81, ilce_haritasi)
    if aday.il:
        bulunan.add(aday.il)
    hedef_bulunan = [il for il in hedef if il in bulunan]
    if bulunan and not hedef_bulunan:
        return Degerlendirme(False, "şehirler dışında")

    sadece_baslik = getattr(aday, "baslikla", False) and len(tn) - len(baslik_n) < 600
    son = None if sadece_baslik else son_basvuru_bul(tn, bugun)
    if son and son < bugun:
        return Degerlendirme(False, "başvuru süresi geçmiş")

    erkek = bool(re.search(r"(sadece|yalnizca|yalniz) erkek|\berkek olmak|cinsiyet[^.]{0,25}\berkek", tn))
    kadin = bool(re.search(r"(sadece|yalnizca|yalniz) (kadin|bayan)|\b(kadin|bayan) olmak|cinsiyet[^.]{0,25}\b(kadin|bayan)", tn))
    bilgi = {
        "lisans": lisans_var(tn),
        "onlisans": bool(ONLISANS.search(tn)),
        "puan_turleri": _puan_turleri(tn),
        "asgari_puan": _asgari_puan(tn),
        "dil": _dil_notu(tn),
        "ehliyet": _ehliyet_siniflari(tn),
        "askerlik": _askerlik_sarti(tn),
        "yas_siniri": _yas_siniri(tn),
        "sadece_erkek": erkek and not kadin,
        "sadece_kadin": kadin and not erkek,
    }

    kisiler = [s for s in (kisi_degerlendir(k, tn, bilgi) for k in profil["kisiler"]) if s]
    oncelikli = any(il in il_cfg["oncelikli"] for il in hedef_bulunan)
    d = Degerlendirme(True, "", kisiler, hedef_bulunan, oncelikli, son, False, ek_notlar)

    if kisiler:
        return d
    if aday.tur == "belediye" and not bilgi["lisans"] and not bilgi["onlisans"]:
        d.kontrol_et = True
        return d
    if sadece_baslik:
        uyumsuz = [k for k in BASLIK_UYUMSUZ if k in baslik_n]
        if "muhendis" in baslik_n and "tekniker" not in baslik_n:
            uyumsuz.append("muhendis")
        if "a grubu" in tn:
            uyumsuz.append("A grubu")
        if uyumsuz:
            return Degerlendirme(False, f"başlığa göre uymuyor ({uyumsuz[0]})")
        d.kontrol_et = True
        d.ek_notlar.append("ℹ️ Bu sitenin ayrıntıları otomatik okunamıyor, başlığa göre size uygun olabilir")
        return d
    return Degerlendirme(False, "profile uymuyor")
