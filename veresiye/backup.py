"""Otomatik yedekleme: saatlik, günlük ve aylık.

- Yedekler SQLite'ın güvenli `backup()` API'si ile alınır (çalışan veritabanının
  tutarlı anlık görüntüsü; WAL dahil).
- Arka planda tek bir daemon iş parçacığı her 60 saniyede bir kontrol eder.
- Uygulama kapalıysa kaçırılan yedekler, açılışta tamamlanır.
- Geri yükleme ÖNCESİ mevcut veritabanı otomatik olarak "on-yukleme" yedeğine
  kopyalanır; veri kaybı yaşanmaz.
- Eski yedek dosyaları cömertçe saklanır (saatlik: 72, günlük: 120, aylık: 24).
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import threading
import time
from datetime import datetime

from . import db as dbmod

SAATLIK_SAKLA = 72      # 3 gün
GUNLUK_SAKLA = 120      # 4 ay
AYLIK_SAKLA = 24        # 2 yıl
MANUEL_SAKLA = 30
ON_SAKLA = 10

KLASOR_SAKLA = {
    "saatlik": SAATLIK_SAKLA,
    "gunluk": GUNLUK_SAKLA,
    "aylik": AYLIK_SAKLA,
    "manuel": MANUEL_SAKLA,
    "on-yukleme": ON_SAKLA,
}


class YedekYoneticisi:
    def __init__(self, db_yolu: str | None = None, yedek_koku: str | None = None):
        self.db_yolu = db_yolu or dbmod.VERESIYE_DB
        self.yedek_koku = yedek_koku or dbmod.YEDEK_KOKU
        self._durdur = threading.Event()
        self._is_parcacigi: threading.Thread | None = None
        self._kilit = threading.Lock()

    # ------------------------------------------------------------------ #
    # Otomatik döngü
    # ------------------------------------------------------------------ #
    def baslat(self) -> None:
        if self._is_parcacigi and self._is_parcacigi.is_alive():
            return
        self._durdur.clear()
        self._is_parcacigi = threading.Thread(
            target=self._dongu, name="yedek-dongusu", daemon=True)
        self._is_parcacigi.start()

    def durdur(self) -> None:
        self._durdur.set()

    def _dongu(self) -> None:
        # Açılışta kaçırılan yedekleri tamamla
        try:
            self.kontrol_et()
        except Exception:
            pass
        while not self._durdur.wait(60):
            try:
                self.kontrol_et()
            except Exception:
                pass  # yedekleme hatası uygulamayı düşürmez

    def kontrol_et(self) -> list[dict]:
        """Saatlik/günlük/aylık yedek zamanı geldi mi bakar; gerekiyorsa alır."""
        simdi = datetime.now()
        yapilan = []
        with self._kilit:
            conn = dbmod.baglanti()
            try:
                def oku(k: str) -> str:
                    r = conn.execute("SELECT deger FROM ayarlar WHERE anahtar=?", (k,)).fetchone()
                    return r["deger"] if r else ""

                def yaz(k: str, v: str) -> None:
                    conn.execute(
                        "INSERT INTO ayarlar(anahtar, deger) VALUES (?,?) "
                        "ON CONFLICT(anahtar) DO UPDATE SET deger=excluded.deger", (k, v))
                    conn.commit()

                son_saatlik = oku("son_saatlik")
                gerekli_saatlik = (
                    not son_saatlik
                    or (simdi - datetime.fromisoformat(son_saatlik)).total_seconds() >= 3600
                )
                if gerekli_saatlik:
                    self.yedekle("saatlik")
                    yaz("son_saatlik", simdi.isoformat(timespec="seconds"))
                    yapilan.append("saatlik")

                bugun = simdi.strftime("%Y-%m-%d")
                if oku("son_gunluk") != bugun:
                    self.yedekle("gunluk")
                    yaz("son_gunluk", bugun)
                    yapilan.append("gunluk")

                bu_ay = simdi.strftime("%Y-%m")
                if oku("son_aylik") != bu_ay:
                    self.yedekle("aylik")
                    yaz("son_aylik", bu_ay)
                    yapilan.append("aylik")
            finally:
                conn.close()
        return yapilan

    # ------------------------------------------------------------------ #
    # Tek bir yedek alma
    # ------------------------------------------------------------------ #
    def yedekle(self, tur: str = "manuel", kaynak: str | None = None) -> dict:
        kaynak = kaynak or self.db_yolu
        if tur not in KLASOR_SAKLA:
            tur = "manuel"
        klasor = os.path.join(self.yedek_koku, tur)
        os.makedirs(klasor, exist_ok=True)

        simdi = datetime.now()
        if tur == "gunluk":
            ad = f"veresiye_{simdi.strftime('%Y-%m-%d')}.db"
        elif tur == "aylik":
            ad = f"veresiye_{simdi.strftime('%Y-%m')}.db"
        else:
            ad = f"veresiye_{simdi.strftime('%Y%m%d_%H%M%S')}.db"
        hedef = os.path.join(klasor, ad)
        # Aynı saniyede iki dosya çakışırsa sonek ekle
        sayac = 1
        while os.path.exists(hedef):
            hedef = os.path.join(klasor, ad.replace(".db", f"_{sayac}.db"))
            sayac += 1

        src = sqlite3.connect(kaynak, timeout=30)
        try:
            dst = sqlite3.connect(hedef)
            try:
                src.backup(dst)                    # tutarlı anlık görüntü
                dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                dst.close()
        finally:
            src.close()

        # Bütünlük kontrolü
        test = sqlite3.connect(hedef)
        try:
            sonuc = test.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            test.close()
        if sonuc != "ok":
            os.remove(hedef)
            raise RuntimeError(f"Yedek bütünlük kontrolünden geçmedi: {sonuc}")

        boyut = os.path.getsize(hedef)
        kayit_zamani = simdi.strftime("%Y-%m-%d %H:%M:%S")
        conn = dbmod.baglanti()
        try:
            conn.execute(
                "INSERT INTO yedekler(dosya, tur, boyut, zaman, sonuc) VALUES (?,?,?,?,?)",
                (hedef, tur, boyut, kayit_zamani, "tamam"),
            )
            conn.commit()
        finally:
            conn.close()

        self._don(durum=KLASOR_SAKLA[tur], klasor=klasor)

        return {"dosya": hedef, "tur": tur, "boyut": boyut, "zaman": kayit_zamani}

    # ------------------------------------------------------------------ #
    # Geri yükleme
    # ------------------------------------------------------------------ #
    def geri_yukle(self, yedek_dosya: str) -> None:
        if not os.path.exists(yedek_dosya):
            raise FileNotFoundError("Yedek dosyası bulunamadı.")
        # 1) Önce MEVCUT veri korunur
        self.yedekle("on-yukleme")
        # 2) Yedek doğrulanır
        test = sqlite3.connect(yedek_dosya)
        try:
            sonuc = test.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            test.close()
        if sonuc != "ok":
            raise RuntimeError(f"Yedek dosyası bozuk görünüyor: {sonuc}")
        # 3) Yedek, canlı veritabanına API üzerinden geri akıtılır (dosya silinmeden)
        src = sqlite3.connect(yedek_dosya, timeout=30)
        dst = sqlite3.connect(self.db_yolu, timeout=30)
        try:
            src.backup(dst)
            dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            dst.close()
            src.close()
        # 4) İşlem günlüğüne not düşülür
        conn = dbmod.baglanti()
        try:
            conn.execute(
                "INSERT INTO hareketler(zaman, islem, tablo, kayit_id, detay) VALUES (?,?,?,?,?)",
                (dbmod.simdi(), "geri_yukleme", "veresiye.db", None,
                 '{"dosya": "%s"}' % os.path.basename(yedek_dosya)),
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Liste ve döndürme
    # ------------------------------------------------------------------ #
    def liste(self) -> list[dict]:
        """Diskteki tüm yedek dosyaları (tür ve zamana göre)."""
        out = []
        if not os.path.isdir(self.yedek_koku):
            return out
        for tur in os.listdir(self.yedek_koku):
            klasor = os.path.join(self.yedek_koku, tur)
            if not os.path.isdir(klasor):
                continue
            for ad in os.listdir(klasor):
                yol = os.path.join(klasor, ad)
                if not os.path.isfile(yol):
                    continue
                st = os.stat(yol)
                out.append({
                    "tur": tur,
                    "ad": ad,
                    "yol": yol,
                    "boyut": st.st_size,
                    "zaman": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                })
        out.sort(key=lambda x: x["zaman"], reverse=True)
        return out

    def son_durum(self) -> dict:
        conn = dbmod.baglanti()
        try:
            def oku(k: str) -> str:
                r = conn.execute("SELECT deger FROM ayarlar WHERE anahtar=?", (k,)).fetchone()
                return r["deger"] if r else ""
            return {
                "son_saatlik": oku("son_saatlik"),
                "son_gunluk": oku("son_gunluk"),
                "son_aylik": oku("son_aylik"),
            }
        finally:
            conn.close()

    @staticmethod
    def _don(durum: int, klasor: str) -> None:
        """Eski yedekleri (sayısal sınırlar içinde) temizler — sadece yedek dosyaları."""
        try:
            dosyalar = [
                os.path.join(klasor, ad) for ad in os.listdir(klasor)
                if os.path.isfile(os.path.join(klasor, ad))
            ]
            dosyalar.sort(key=os.path.getmtime, reverse=True)
            for eskisi in dosyalar[durum:]:
                os.remove(eskisi)
        except Exception:
            pass
