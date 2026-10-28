# Kuyumcu Veresiye Premium

Kuyumcular için **premium veresiye takip programı**. Web arayüzlüdür: ana bilgisayarda
çalışır, **aynı Wi-Fi ağındaki tabletten** tarayıcı ile erişilir. Tamamen çevrimdışı
çalışır, harici internet servisi kullanmaz.

## Temel Güvence Kuralları

| Kural | Uygulama |
|---|---|
| **Veri asla silinmez** | Satış/ödeme *iptal edilir* (silinmez, üzeri çizili listede durur), müşteri *arşivlenir* |
| **İşlem günlüğü** | Her ekleme/iptal/değişiklik salt-ekleme `hareketler` tablosuna yazılır (İşlem Geçmişi sayfası) |
| **Saatlik yedek** | Her saat başı otomatik (son 72 yedek saklanır) |
| **Günlük yedek** | Gün değişince otomatik (son 120 gün saklanır) |
| **Aylık yedek** | Ay değişince otomatik (2 yıl saklanır) |
| **Kapalıyken bile** | Kaçırılan yedek, bir sonraki açılışta tamamlanır |
| **Geri yükleme güvenliği** | Geri yüklemeden MEVCUT veriler otomatik "on-yukleme" yedeğine kopyalanır |

## Özellikler

- **Panel**: toplam TL/altın alacak, günlük/aylık tahsilat, çek/senet portföyü, tedarikçi
  borcu, kasa girişi, ödeme sözü vermiş borçlular, vadesi geçen müşteriler, son işlemler
- **Müşteriler**: arama, borçlu filtresi, kredi limiti, limit aşımı uyarısı, **kategori**,
  **ödeme sözü tarihi + notu**, arşiv
- **Veresiye satışları**: TL **veya gram altın**, vadeli/vadesiz, açıklama, iptal (sebepli)
- **Peşin satış**: veresiyeden ayrı tutulur, **kasa defterine otomatik** gelir yazar
- **Ürün kataloğu**: sık satılan ürünler TL fiyatı/gram miktarıyla kaydet; satış formunda
  ürünü seçince tutar otomatik dolar
- **Tahsilatlar**: nakit/kart/havale/altın; TL↔altın borç dönüşümü güncel gram fiyatla
- **Kasa defteri**: TL tahsilatlar + peşin satışlar otomatik gelir; manuel gelir/gider,
  kategori, yürüyen bakiye, giren/çıkan/net özeti
- **Çek & senet defteri**: portföy takibi, vadeye kalan gün, "Tahsil" işaretince müşteriye
  otomatik tahsilat oluşur, geri alınca tahsilat otomatik iptal olur, karşılıksız/karşı
  tarafa hamle durumları
- **Tedarikçiler**: veresiye aldığınız kişi/firmaların borç defteri (alış + ödeme + ekstre)
- **Hesap ekstresi**: yürüyen bakiyeli, yazdırmaya hazır (imza satırlı); tedarikçi ekstresi de
- **Hatırlatma**: WhatsApp / Ara butonları + hazır hatırlatma metni muhafaza bandında
- **Raporlar**: son 6 ay özeti (veresiye TL/altın + peşin sütunu), en borçlular,
  CSV dışa aktarma (Excel uyumlu UTF-8, satış şekli sütunu dahil)
- **Gram fiyat yönetimi**: günlük fiyat girilir/geçmiş görüntülenir
- **İşlem geçmişi**: tüm modüllerin salt-ekleme denetim kaydı (kim ne yapıp neyi değiştirdi)
- **PIN kilidi** (isteğe bağlı): tabletten erişimi korur
- **Tablet erişimi**: `http://<bilgisayar-ip>:8765` — aynı ağdan tüm cihazlarla

## Kurulum ve Çalıştırma

### Web sürümü (tabletli)

```bat
cd kuyumcu-veresiye
pip install -r requirements.txt
python baslat.py
```

veya çift tıklayın: **`baslat.bat`**

Uygulama kendi tarayıcısında açılır. Ekranda yazan **Tablet adresi**ni aynı ağdaki
tabletten tarayıcıya yazarak kullanabilirsiniz.

### Masaüstü sürümü (tkinter)

```bat
python masaustu.py
```

veya çift tıklayın: **`masaustu.bat`**

Masaüstü sürümü web sürümüyle **aynı `veresiye.db` dosyasını paylaşır**
(ikisinden aynı anda kayıt girilebilir). Panel, müşteriler, satış ekleme,
tahsilat, ekstre (iptal dahil), ürünler, gram fiyat, işlem geçmişi ve yedek
sekmelerine sahiptir; premium koyu + altın tema kullanır.

### Tek Dosya EXE Üretimi

```bat
pip install pyinstaller
pyinstaller kuyumcu_veresiye.spec      :: web sürümü -> dist\KuyumcuVeresiye.exe
pyinstaller kuyumcu_masaustu.spec      :: masaüstü   -> dist\KuyumcuVeresiyeMasaustu.exe
```

Çıktı: `dist\KuyumcuVeresiye.exe` — exe'nin yanında `veresiye.db` ve `yedekler\`
klasörü oluşur. **Taşırsanız yedeklerle birlikte taşıyın.**

## Veriler Nerede?

- `veresiye.db` — ana veritabanı (proje/exe yanında)
- `yedekler\saatlik|gunluk|aylik|manuel|on-yukleme\` — yedek dosyaları
- `gizli_anahtar.txt` — oturum anahtarı (silinirse yeni üretilir, veriye zarar vermez)

**Öneri:** haftada bir `Yedek & Güvenlik → Tam JSON Yedeği` indirip harici bir diske
kopyalayın; `yedekler` klasörünü de düzenli olarak başka bir diske yedekleyin.

## Teknik Notlar

- Python 3.10+ · Flask · SQLite (WAL modu, yedekleme SQLite `backup()` API'si ile)
- Arayüz: özel CSS (harici CDN/JS yok — tamamen çevrimdışı, dokunmatik dostu)
- Hiçbir kayıt `DELETE` edilmez; yalnızca yedek *dosyaları* sayısallaştırılır (rotasyon)
