"""Türkçe metin normalleştirme ve ortak anahtar kelimeler."""
import hashlib
import re
import unicodedata

_BUYUK = str.maketrans({"İ": "i", "I": "ı"})
_ASCII = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def norm(s) -> str:
    """Küçük harf, Türkçe karakterleri sadeleştir, boşlukları tekle."""
    if not s:
        return ""
    s = unicodedata.normalize("NFC", str(s)).translate(_BUYUK).lower()
    s = s.replace("\u0307", "").translate(_ASCII)
    return re.sub(r"\s+", " ", s).strip()


def slug(s) -> str:
    return re.sub(r"[^a-z0-9]", "", norm(s))


def anahtar(*parcalar) -> str:
    return hashlib.sha1("|".join(parcalar).encode("utf-8")).hexdigest()[:16]


# Bir bağlantının ya da metnin personel alım ilanı olduğunu gösteren ifadeler
PERSONEL_KELIMELERI = [
    "personel alim", "personel alin", "memur alim", "memur alin", "isci alim",
    "isci alin", "eleman alim", "personel temin", "istihdam edil",
    "sozlesmeli personel", "surekli isci", "zabita memuru", "itfaiye eri",
    "kpss ile", "kpss puan", "atanmak uzere", "alim ilani", "alimi ilani",
    "personel ilani", "kadro ilani", "personel istihdam", "gecici isci", "is ilani", "kamu ilani",
]

# Bağlantı metninde geçerse ilan sayılmayacak ifadeler (sonuç, ihale vb.)
HARIC_BAGLANTI = [
    "ihale", "kiralama", "kiraya", "satis", "sonuc", "liste", "mulakat",
    "sinav yeri", "sozlu sinav", "yazili sinav", "kesin kayit", "evrak teslim",
    "iptal", "yerlestirme", "basarili aday", "kurs", "hazirlik", "yetistir", "egitim programi",
]

AKADEMIK = [
    "ogretim uyesi", "ogretim gorevlisi", "arastirma gorevlisi",
    "doktor ogretim", "docent", "profesor", "akademik personel",
]


def personel_baglantisi_mi(metin_n: str) -> bool:
    return any(k in metin_n for k in PERSONEL_KELIMELERI) and not any(
        h in metin_n for h in HARIC_BAGLANTI
    )


def kisa_hata(e) -> str:
    import requests
    if isinstance(e, requests.exceptions.Timeout):
        return "zaman aşımı"
    if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
        return f"HTTP {e.response.status_code}"
    if isinstance(e, requests.exceptions.ConnectionError):
        return "bağlantı kurulamadı"
    return type(e).__name__
