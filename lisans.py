"""HACILAR KUYUMCULUK — demo + lisans modülü.

Kural:
- Program ilk açıldığında 24 saatlik (1 günlük) sınırsız demo başlar.
- Demo bitince anahtar istenir; geçerli anahtar girilirse program kalıcı açılır.
- Anahtar üretimi yalnızca bayi (sahip) aracıyla yapılır: anahtar_uretici.exe.

Dayanıklılık: demo başlangıcı hem veritabanına hem Windows kayıt defterine
yazılır; biri silinse bile deneme sıfırlanamaz (en eski tarih geçerlidir).
Saat geri alınırsa (yani "son kontrol" zamanından eski bir an görülürse)
deneme bitmiş sayılır.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

from veresiye import db as vdb

DEMO_SANIYE = 24 * 60 * 60          # 1 gün
KONTROL_PAYI = 6 * 60 * 60          # saat geri alma toleransı
ONEK = "HACILAR"
BAYI_METNI = "Lisans anahtarı almak için satıcınızla iletişime geçin."

# Gizli HMAC anahtarı (obfuscate: XOR 0x5C) — değiştirmeyin.
_PARCA = [
    0xB3, 0x74, 0xD5, 0x4B, 0x32, 0xD4, 0x8F, 0xCD, 0xC8, 0x3B, 0xEF, 0x25,
    0x49, 0xC0, 0x9B, 0x44, 0xAF, 0x60, 0xB8, 0x35, 0xF1, 0x6C, 0x94, 0x00,
    0x15, 0xC2, 0xD7, 0x57, 0x12, 0xB7, 0xF4, 0xF6,
]
ALFABE = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"   # RFC 4648 base32


def _gizli() -> bytes:
    return bytes(b ^ 0x5C for b in _PARCA)


def _imza(tohum: str) -> str:
    diger = hmac.new(_gizli(), tohum.encode("utf-8"), hashlib.sha256).digest()
    return base64.b32encode(diger).decode("ascii").rstrip("=")[:15]


def _normal(girdi: str) -> str:
    a = (girdi or "").upper().replace(" ", "")
    for ayrac in ("-", "–"):
        a = a.replace(ayrac, "")
    if a.startswith(ONEK):
        a = a[len(ONEK):]
    return a


def uret(tohum: str | None = None) -> str:
    """Bayi aracı: geçerli bir lisans anahtarı üretir."""
    tohum = (tohum or "").upper().strip()
    if len(tohum) != 5 or any(k not in ALFABE for k in tohum):
        tohum = "".join(ALFABE[b % len(ALFABE)] for b in os.urandom(5))
    payload = (tohum + _imza(tohum))[:20]
    return ONEK + "-" + "-".join(payload[i:i + 5] for i in range(0, 20, 5))


def anahtar_gecerli_mi(girdi: str) -> bool:
    a = _normal(girdi)
    if len(a) != 20:
        return False
    tohum, imza = a[:5], a[5:]
    if any(k not in ALFABE for k in a):
        return False
    return hmac.compare_digest(imza, _imza(tohum))


# --------------------------------------------------------------------------- #
# Kalıcılık: veritabanı (ayarlar) + Windows kayıt defteri (HKCU)
# --------------------------------------------------------------------------- #
def _reg():
    try:
        import winreg
    except ImportError:
        return None
    try:
        return winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                r"Software\HacilarKuyumculuk")
    except OSError:
        return None


def _reg_yaz(ad: str, deger: str) -> None:
    try:
        import winreg
    except ImportError:
        return
    k = _reg()
    if k is not None:
        try:
            winreg.SetValueEx(k, ad, 0, winreg.REG_SZ, deger)
        except OSError:
            pass


def _reg_oku(ad: str) -> str:
    try:
        import winreg
    except ImportError:
        return ""
    k = _reg()
    if k is None:
        return ""
    try:
        return str(winreg.QueryValueEx(k, ad)[0] or "")
    except OSError:
        return ""


def _ayar_yaz(anahtar: str, deger: str) -> None:
    try:
        conn = vdb.baglanti()
        conn.execute("INSERT INTO ayarlar(anahtar, deger) VALUES (?, ?) "
                     "ON CONFLICT(anahtar) DO UPDATE SET deger=excluded.deger",
                     (anahtar, deger))
        conn.commit()
        conn.close()
    except Exception:
        pass


def _ayar_oku(anahtar: str) -> str:
    try:
        conn = vdb.baglanti()
        satir = conn.execute("SELECT deger FROM ayarlar WHERE anahtar=?",
                             (anahtar,)).fetchone()
        conn.close()
        return str(satir[0]) if satir else ""
    except Exception:
        return ""


def _tarih_al(*degerler: str) -> float | None:
    import datetime
    en_eski: float | None = None
    for d in degerler:
        d = (d or "").strip()
        if not d:
            continue
        try:
            t = datetime.datetime.strptime(d[:19], "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            continue
        en_eski = t if en_eski is None else min(en_eski, t)
    return en_eski


def calistir() -> None:
    """İlk açılışta demoyu başlatır; her açılışta kontrol izini günceller."""
    simdi = time.time()
    baslangic = _tarih_al(_ayar_oku("demo_baslangic"), _reg_oku("DemoBaslangic"))
    if baslangic is None:
        damga = time.strftime("%Y-%m-%d %H:%M:%S")
        _ayar_yaz("demo_baslangic", damga)
        _reg_yaz("DemoBaslangic", damga)
        baslangic = simdi
    if simdi < baslangic:
        _ayar_yaz("demo_baslangic", time.strftime("%Y-%m-%d %H:%M:%S",
                                                  time.localtime(simdi)))
        _reg_yaz("DemoBaslangic", time.strftime("%Y-%m-%d %H:%M:%S",
                                                time.localtime(simdi)))
    _ayar_yaz("demo_son_kontrol", time.strftime("%Y-%m-%d %H:%M:%S"))
    _reg_yaz("DemoSonKontrol", time.strftime("%Y-%m-%d %H:%M:%S"))


def saklanan_anahtarlar() -> list[str]:
    out = [_ayar_oku("lisans_anahtar"), _reg_oku("Lisans")]
    return [a for a in out if a]


def etkinlestir(girdi: str) -> bool:
    if not anahtar_gecerli_mi(girdi):
        return False
    a = _normal(girdi)
    grup = ONEK + "-" + "-".join(a[i:i + 5] for i in range(0, 20, 5))
    _ayar_yaz("lisans_anahtar", grup)
    _reg_yaz("Lisans", grup)
    return True


def durum() -> dict:
    """{'lisansli': bool, 'demo_aktif': bool, 'tam_erisim': bool,
       'kalan_yazi': str, 'not': str}"""
    lisansli = any(anahtar_gecerli_mi(a) for a in saklanan_anahtarlar())
    if lisansli:
        return {"lisansli": True, "demo_aktif": True, "tam_erisim": True,
                "kalan_yazi": "Lisanslı", "not": ""}

    baslangic = _tarih_al(_ayar_oku("demo_baslangic"), _reg_oku("DemoBaslangic"))
    simdi = time.time()
    son = _tarih_al(_ayar_oku("demo_son_kontrol"), _reg_oku("DemoSonKontrol"))
    not_ = ""
    if baslangic is None:
        calistir()
        baslangic = simdi
    if son is not None and simdi < son - KONTROL_PAYI:
        return {"lisansli": False, "demo_aktif": False, "tam_erisim": False,
                "kalan_yazi": "bitti", "not": "Sistem saati geri alınmış; demo bitti."}

    kalan = DEMO_SANIYE - (simdi - baslangic)
    if kalan > 0:
        saat = int(kalan // 3600)
        dk = int((kalan % 3600) // 60)
        return {"lisansli": False, "demo_aktif": True, "tam_erisim": True,
                "kalan_yazi": f"DEMO — {saat}sa {dk:02d}dk kaldı", "not": ""}
    return {"lisansli": False, "demo_aktif": False, "tam_erisim": False,
            "kalan_yazi": "bitti", "not": not_}
