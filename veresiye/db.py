"""SQLite katmanı: şema, bağlantı ve yol yardımcıları.

Kural: Hiçbir kayıt fiziksel olarak SİLİNMEZ.
- İptal edilen satış/ödeme `durum='iptal'` olarak kalır (işlem geçmişinde görünür).
- Müşteri arşivlenir, silinmez.
- Tüm değişiklikler `hareketler` (salt-ekleme) tablosuna yazılır.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime

# --------------------------------------------------------------------------- #
# Yollar
# --------------------------------------------------------------------------- #
def paket_koku() -> str:
    """Şablon/statik dosyaların kökü (PyInstaller one-file'da _MEIPASS)."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def proje_koku() -> str:
    """Veri kökü: veritabanı, yedekler, gizli anahtar (yanında çalışılan klasör)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


VERESIYE_DB = os.path.join(proje_koku(), "veresiye.db")
YEDEK_KOKU = os.path.join(proje_koku(), "yedekler")


# --------------------------------------------------------------------------- #
# Şema
# --------------------------------------------------------------------------- #
SCHEMA = """
CREATE TABLE IF NOT EXISTS ayarlar (
    anahtar  TEXT PRIMARY KEY,
    deger    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS musteriler (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ad          TEXT NOT NULL,
    telefon     TEXT NOT NULL DEFAULT '',
    adres       TEXT NOT NULL DEFAULT '',
    notlar      TEXT NOT NULL DEFAULT '',
    limit_tl    REAL NOT NULL DEFAULT 0,
    kategori    TEXT NOT NULL DEFAULT '',
    sozu_tarih  TEXT NOT NULL DEFAULT '',
    sozu_not    TEXT NOT NULL DEFAULT '',
    durum       TEXT NOT NULL DEFAULT 'aktif',      -- aktif | arsiv
    olusturma   TEXT NOT NULL,
    guncelleme  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS fiyatlar (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tarih        TEXT NOT NULL UNIQUE,              -- YYYY-MM-DD
    gram_fiyat   REAL NOT NULL,                     -- TL / gram
    kaynak       TEXT NOT NULL DEFAULT 'manuel',
    kayit_zamani TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS satislar (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    musteri_id    INTEGER NOT NULL,
    tarih         TEXT NOT NULL,                    -- YYYY-MM-DD
    vade          TEXT NOT NULL DEFAULT '',         -- YYYY-MM-DD (boş = vadeli değil)
    para_birimi   TEXT NOT NULL,                    -- tl | altin
    tutar         REAL NOT NULL,                    -- TL tutarı veya gram miktarı
    gram_fiyat    REAL NOT NULL DEFAULT 0,          -- satış anındaki gram fiyatı (TL/gr)
    aciklama      TEXT NOT NULL DEFAULT '',
    sekl          TEXT NOT NULL DEFAULT 'veresiye', -- veresiye | pesin
    urun_id       INTEGER NOT NULL DEFAULT 0,
    durum         TEXT NOT NULL DEFAULT 'aktif',    -- aktif | iptal
    iptal_sebebi  TEXT NOT NULL DEFAULT '',
    kayit_zamani  TEXT NOT NULL,
    guncelleme    TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (musteri_id) REFERENCES musteriler(id)
);

CREATE TABLE IF NOT EXISTS odemeler (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    musteri_id    INTEGER NOT NULL,
    tarih         TEXT NOT NULL,                    -- YYYY-MM-DD
    para_birimi   TEXT NOT NULL,                    -- ödenen tutarın birimi: tl | altin
    tutar         REAL NOT NULL,
    hedef         TEXT NOT NULL,                    -- hangi borca uygulanıyor: tl | altin
    uygulanan     REAL NOT NULL,                    -- hedef birime çevrilmiş miktar
    kur           REAL NOT NULL DEFAULT 0,          -- çevrimde kullanılan gram fiyat
    yontem        TEXT NOT NULL DEFAULT 'nakit',    -- nakit | kart | havale | altin
    aciklama      TEXT NOT NULL DEFAULT '',
    durum         TEXT NOT NULL DEFAULT 'aktif',    -- aktif | iptal
    iptal_sebebi  TEXT NOT NULL DEFAULT '',
    kayit_zamani  TEXT NOT NULL,
    guncelleme    TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (musteri_id) REFERENCES musteriler(id)
);

-- Katalog: ürünler ve birim fiyatları
CREATE TABLE IF NOT EXISTS urunler (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ad            TEXT NOT NULL,
    birim         TEXT NOT NULL DEFAULT 'adet',
    tl_fiyat      REAL NOT NULL DEFAULT 0,
    gr_miktar     REAL NOT NULL DEFAULT 0,
    notlar        TEXT NOT NULL DEFAULT '',
    durum         TEXT NOT NULL DEFAULT 'aktif',    -- aktif | arsiv
    kayit_zamani  TEXT NOT NULL,
    guncelleme    TEXT NOT NULL DEFAULT ''
);

-- Tedarikçiler (bizim borcumuz)
CREATE TABLE IF NOT EXISTS tedarikciler (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ad          TEXT NOT NULL,
    telefon     TEXT NOT NULL DEFAULT '',
    notlar      TEXT NOT NULL DEFAULT '',
    durum       TEXT NOT NULL DEFAULT 'aktif',      -- aktif | arsiv
    olusturma   TEXT NOT NULL,
    guncelleme  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS alislar (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tedarikci_id  INTEGER NOT NULL,
    tarih         TEXT NOT NULL,
    tutar         REAL NOT NULL,
    aciklama      TEXT NOT NULL DEFAULT '',
    durum         TEXT NOT NULL DEFAULT 'aktif',    -- aktif | iptal
    iptal_sebebi  TEXT NOT NULL DEFAULT '',
    kayit_zamani  TEXT NOT NULL,
    guncelleme    TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (tedarikci_id) REFERENCES tedarikciler(id)
);

CREATE TABLE IF NOT EXISTS tedarik_odemeler (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tedarikci_id  INTEGER NOT NULL,
    tarih         TEXT NOT NULL,
    tutar         REAL NOT NULL,
    yontem        TEXT NOT NULL DEFAULT 'nakit',
    aciklama      TEXT NOT NULL DEFAULT '',
    durum         TEXT NOT NULL DEFAULT 'aktif',    -- aktif | iptal
    iptal_sebebi  TEXT NOT NULL DEFAULT '',
    kayit_zamani  TEXT NOT NULL,
    guncelleme    TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (tedarikci_id) REFERENCES tedarikciler(id)
);

-- Çek & Senet defteri
CREATE TABLE IF NOT EXISTS cekler (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tur           TEXT NOT NULL DEFAULT 'cek',      -- cek | senet
    musteri_id    INTEGER NOT NULL,
    banka         TEXT NOT NULL DEFAULT '',
    belge_no      TEXT NOT NULL DEFAULT '',
    tutar         REAL NOT NULL,
    tarih         TEXT NOT NULL,                    -- portföye alma tarihi
    vade          TEXT NOT NULL,
    durum         TEXT NOT NULL DEFAULT 'portfoy',  -- portfoy | tahsil | karsi_hamle | karsiliksiz
    notlar        TEXT NOT NULL DEFAULT '',
    odeme_id      INTEGER NOT NULL DEFAULT 0,       -- tahsil işaretinde oluşan tahsilat
    kayit_zamani  TEXT NOT NULL,
    guncelleme    TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (musteri_id) REFERENCES musteriler(id)
);

-- Kasa defteri (manuel gelir/gider; tahsilat ve peşin satışlar otomatik eklenir)
CREATE TABLE IF NOT EXISTS kasa (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tarih         TEXT NOT NULL,
    tur           TEXT NOT NULL,                    -- gelir | gider
    kategori      TEXT NOT NULL DEFAULT '',
    tutar         REAL NOT NULL,
    aciklama      TEXT NOT NULL DEFAULT '',
    durum         TEXT NOT NULL DEFAULT 'aktif',    -- aktif | iptal
    iptal_sebebi  TEXT NOT NULL DEFAULT '',
    kayit_zamani  TEXT NOT NULL,
    guncelleme    TEXT NOT NULL DEFAULT ''
);

-- Salt-ekleme işlem günlüğü: asla güncellenmez, asla silinmez.
CREATE TABLE IF NOT EXISTS hareketler (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    zaman    TEXT NOT NULL,
    islem    TEXT NOT NULL,
    tablo    TEXT NOT NULL DEFAULT '',
    kayit_id INTEGER,
    detay    TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS yedekler (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    dosya  TEXT NOT NULL,
    tur    TEXT NOT NULL,                           -- saatlik | gunluk | aylik | manuel | on-yukleme
    boyut  INTEGER NOT NULL DEFAULT 0,
    zaman  TEXT NOT NULL,
    sonuc  TEXT NOT NULL DEFAULT 'tamam'
);

CREATE INDEX IF NOT EXISTS ix_satis_musteri  ON satislar(musteri_id);
CREATE INDEX IF NOT EXISTS ix_odeme_musteri  ON odemeler(musteri_id);
CREATE INDEX IF NOT EXISTS ix_satis_tarih    ON satislar(tarih);
CREATE INDEX IF NOT EXISTS ix_odeme_tarih    ON odemeler(tarih);
CREATE INDEX IF NOT EXISTS ix_hareket_zaman  ON hareketler(zaman);
CREATE INDEX IF NOT EXISTS ix_alis_tedarikci ON alislar(tedarikci_id);
CREATE INDEX IF NOT EXISTS ix_todeme_arsivi  ON tedarik_odemeler(tedarikci_id);
CREATE INDEX IF NOT EXISTS ix_cek_durum      ON cekler(durum);
CREATE INDEX IF NOT EXISTS ix_kasa_tarih     ON kasa(tarih);
"""


def _migrasyon(conn) -> None:
    """Eski veritabanlarına yeni sütunları ekler (veri kaybı olmadan)."""
    for tablo, sutun, ddl in [
        ("musteriler", "kategori",   "TEXT NOT NULL DEFAULT ''"),
        ("musteriler", "sozu_tarih", "TEXT NOT NULL DEFAULT ''"),
        ("musteriler", "sozu_not",   "TEXT NOT NULL DEFAULT ''"),
        ("satislar",   "sekl",       "TEXT NOT NULL DEFAULT 'veresiye'"),
        ("satislar",   "urun_id",    "INTEGER NOT NULL DEFAULT 0"),
    ]:
        mevcut = [r[1] for r in conn.execute(f"PRAGMA table_info({tablo})")]
        if mevcut and sutun not in mevcut:
            conn.execute(f"ALTER TABLE {tablo} ADD COLUMN {sutun} {ddl}")


def baglanti(yol: str | None = None) -> sqlite3.Connection:
    """Kısa ömürlü, satır-nesnesi döndüren bağlantı açar."""
    hedef = yol or VERESIYE_DB
    os.makedirs(os.path.dirname(hedef), exist_ok=True)
    conn = sqlite3.connect(hedef, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    """Şemayı oluşturur, varsayılan ayarları tohumlar, eski DB'yi migrate eder."""
    conn = baglanti()
    try:
        conn.executescript(SCHEMA)
        _migrasyon(conn)
        varsayilan = {
            "dukkan_adi": "HACILAR KUYUMCULUK",
            "gram_fiyat": "0",
            "vade_gun": "30",
            "pin_hash": "",          # boş = PIN kilidi kapalı
            "pin_tuz": "",
            "son_saatlik": "",
            "son_gunluk": "",
            "son_aylik": "",
        }
        for k, v in varsayilan.items():
            conn.execute("INSERT OR IGNORE INTO ayarlar(anahtar, deger) VALUES (?, ?)", (k, v))
        conn.commit()
    finally:
        conn.close()


def simdi() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
