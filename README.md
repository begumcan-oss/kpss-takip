# KPSS İlan Takip Botu

Kamu ilan sitelerini ve belediye sitelerini düzenli olarak kontrol eder, size uygun ilanları Telegram grubunuza gönderir.

**Kontrol edilen yerler:** kamuilan.sbb.gov.tr, kariyerkapisi.gov.tr, ilan.gov.tr, resmigazete.gov.tr, iskur.gov.tr, yerelyonetimler.csb.gov.tr, ÖSYM tercih kılavuzları ve seçili 16 ildeki belediyelerin siteleri.

**Ne sıklıkla:** Ana siteler saatte bir, belediyeler günde üç kez (06:37, 12:37, 18:37). Her sabah 09:00'dan sonraki ilk çalışmada kısa bir durum raporu gelir.

---

## Kurulum

### 1. GitHub deposu oluşturun
1. github.com'da oturum açın, sağ üstteki **+** düğmesinden **New repository** seçin.
2. Repository name: `kpss-takip`
3. **Public** seçin. (Public depolarda otomatik çalışma ücretsiz ve sınırsızdır. Kişisel bilgileriniz koda değil, gizli bir "secret"a konacağı için görünmez.)
4. **Create repository** düğmesine basın.

### 2. Dosyaları yükleyin
1. İndirdiğiniz zip dosyasını bilgisayarınızda klasöre çıkarın.
2. Depo sayfasında **uploading an existing file** bağlantısına tıklayın.
3. `kpss-takip` klasörünün **içindeki her şeyi** (`.github` klasörü dahil) sürükleyip bırakın, ardından **Commit changes** düğmesine basın.

> Mac kullanıyorsanız `.github` klasörü gizli olabilir. Finder'da **Cmd + Shift + .** tuşlarına basınca görünür.

### 3. Gizli bilgileri (secret) ekleyin
Depoda **Settings → Secrets and variables → Actions → New repository secret** yolunu izleyin ve şunları ekleyin:

| Ad | Değer |
|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather'ın verdiği token |
| `PROFILES_YAML` | `PROFILLER_GIZLI.yaml` dosyasının tüm içeriği (kopyala-yapıştır) |

### 4. Telegram grup kimliğini bulun
1. Botu Telegram grubunuza ekleyin ve gruba `/start` yazın.
2. Depoda **Actions** sekmesine gidin. Çıkan uyarıda iş akışlarını etkinleştirmenizi isterse onaylayın.
3. Soldan **Telegram Kurulum Testi** seçin, **Run workflow** düğmesine basın.
4. Çalışma bitince üstüne tıklayın, **test → Telegram'ı kontrol et** adımını açın. Grubunuzun yanındaki eksi işaretli sayıyı (örneğin `-1001234567890`) kopyalayın.
5. Bu sayıyı `TELEGRAM_CHAT_ID` adıyla yeni bir secret olarak ekleyin.
6. Testi bir kez daha çalıştırın. Gruba deneme mesajı gelmelidir.

### 5. İlk çalıştırma
**Actions → KPSS Takip → Run workflow** yolunu izleyin, mod olarak **hepsi** seçip çalıştırın. Bundan sonra sistem kendi kendine çalışır.

İlk belediye taramasında sistem yaklaşık 250 belediyenin sitesini bulmaya çalışır, bu yüzden biraz uzun sürebilir. Belediye sitelerindeki eski duyurular gönderilmez, sadece başvurusu hâlâ açık olanlar ve sonradan çıkan yeni ilanlar gelir.

---

## Bir sorun olursa
- **Actions** sekmesinde kırmızı çarpı olan çalışmaya tıklayın, hata veren adımın yazısını kopyalayın.
- Aynı sayfanın altındaki **Artifacts** kısmından `ham-sayfalar-...` dosyasını indirin.
- Bu ikisini Claude'a gönderin; sitenin yapısına göre ayarlar düzeltilir.

Günlük durum raporunda "uzun süredir hiç ilan bulunamayanlar" listesinde bir site görünürse, o sitenin yapısı değişmiş olabilir. Aynı yöntemle düzeltilebilir.

## Ayarları değiştirmek
- **Kişi bilgileri, şehirler, öncelikler:** `PROFILES_YAML` secret'ını güncelleyin.
- **Bulunamayan bir belediyenin adresi:** `config/belediyeler.yaml` içindeki `elle_adresler` kısmına ekleyin.
- **Kaynak siteler:** `config/kaynaklar.yaml`.

## Mesajlardaki işaretler
⭐ yüksek öncelik · 🔹 orta öncelik · ▫️ genel kadro · 🔎 ayrıntılar okunamadı, kontrol edin
🎓 mezuniyet şartı · 🌐 dil belgesi · 🚗 ehliyet · 🪖 askerlik · ⚠️ dikkat edilmesi gereken bir şart
