"""Web sayfası ve PDF indirme. Gerekirse sayfayı gerçek bir tarayıcıda (Playwright) açar."""
import io
import logging
import threading
from urllib.parse import urljoin

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings()
log = logging.getLogger("takip")

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
_yerel = threading.local()


def _oturum():
    if not hasattr(_yerel, "s"):
        s = requests.Session()
        s.headers.update({"User-Agent": UA, "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.5"})
        _yerel.s = s
    return _yerel.s


def http_get(url, timeout=25):
    s = _oturum()
    try:
        r = s.get(url, timeout=timeout, allow_redirects=True)
    except requests.exceptions.SSLError:
        # Bazı kamu sitelerinin sertifikaları eksik; yine de içeriği okuyalım
        r = s.get(url, timeout=timeout, allow_redirects=True, verify=False)
    r.raise_for_status()
    if (r.encoding or "").lower() in ("iso-8859-1", "ascii") and "html" in r.headers.get("content-type", ""):
        r.encoding = r.apparent_encoding
    return r


def pdf_metni(veri: bytes, max_sayfa=80) -> str:
    try:
        from pypdf import PdfReader
        okuyucu = PdfReader(io.BytesIO(veri))
        parcalar = []
        for i, sayfa in enumerate(okuyucu.pages):
            if i >= max_sayfa:
                break
            try:
                parcalar.append(sayfa.extract_text() or "")
            except Exception:
                continue
        return "\n".join(parcalar)
    except Exception as e:
        log.warning("PDF okunamadı: %s", e)
        return ""


class Tarayici:
    """JavaScript ile çalışan siteler için Playwright. Kurulu değilse sessizce devre dışı kalır."""

    def __init__(self):
        self._pw = None
        self._browser = None
        self.calisiyor = True

    def ac(self, url):
        if not self.calisiyor:
            return None
        try:
            if self._browser is None:
                from playwright.sync_api import sync_playwright
                self._pw = sync_playwright().start()
                self._browser = self._pw.chromium.launch()
            sayfa = self._browser.new_page(user_agent=UA, locale="tr-TR")
            try:
                sayfa.goto(url, wait_until="domcontentloaded", timeout=45000)
                try:
                    sayfa.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    pass
                sayfa.wait_for_timeout(2500)
                return sayfa.url, sayfa.content()
            finally:
                sayfa.close()
        except ImportError:
            log.warning("Playwright kurulu değil, tarayıcısız devam ediliyor.")
            self.calisiyor = False
            return None
        except Exception as e:
            log.warning("Tarayıcı %s adresini açamadı: %s", url, e)
            return None

    def kapat(self):
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass


def html_getir(url, render=False, tarayici=None, timeout=25):
    """(son_adres, html) döndürür."""
    if render and tarayici is not None:
        sonuc = tarayici.ac(url)
        if sonuc:
            return sonuc
    r = http_get(url, timeout=timeout)
    return r.url, r.text


def _pdf_mi(url, r=None):
    if r is not None and "pdf" in r.headers.get("content-type", "").lower():
        return True
    return url.lower().split("?")[0].endswith(".pdf")


def ilan_metni(url, render=False, tarayici=None, ek_pdf=2) -> str:
    """İlan sayfasının düz metnini (ve içindeki ilk birkaç PDF'in metnini) döndürür."""
    if render and tarayici is not None and not _pdf_mi(url):
        sonuc = tarayici.ac(url)
        if sonuc:
            son_url, html = sonuc
            return _html_isle(son_url, html, ek_pdf)
    r = http_get(url)
    if _pdf_mi(url, r):
        return pdf_metni(r.content)
    return _html_isle(r.url, r.text, ek_pdf)


def _html_isle(url, html, ek_pdf):
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    metin = soup.get_text(" ", strip=True)
    pdfler = []
    for a in soup.find_all("a", href=True):
        h = a["href"].strip()
        if ".pdf" in h.lower() or "dosya" in h.lower() or "indir" in h.lower():
            pdfler.append(urljoin(url, h))
    for p in pdfler[:ek_pdf]:
        try:
            r = http_get(p, timeout=30)
            if _pdf_mi(p, r):
                metin += "\n" + pdf_metni(r.content)
        except Exception:
            continue
    return metin[:400000]
