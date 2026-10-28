"""İş mantığı: müşteriler, veresiye satışları, tahsilatlar, fiyatlar, raporlar.

Para birimi modeli:
- Her satış kendi para biriminde borç yaratır (TL veya gram altın).
- Tahsilat, "hedef" borca uygulanır. Para birimi farklıysa tahsilat anındaki
  gram fiyatla çevrilir ve `uygulanan` alanı hedef birime çevrilmiş miktarı tutar.
- Bakiye = satışlar - tahsilatlar (hedef bazında).
- Ödemeler FIFO uygulanır: en eski satış önce kapanır (vade gecikmesi hesabı için).
"""
from __future__ import annotations

import csv
import io
import json
from contextlib import contextmanager
from datetime import date, datetime

from . import db as dbmod


# --------------------------------------------------------------------------- #
# Yardımcılar
# --------------------------------------------------------------------------- #
@contextmanager
def db():
    conn = dbmod.baglanti()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def simdi() -> str:
    return dbmod.simdi()


def bugun() -> str:
    return date.today().isoformat()


def audit(conn, islem: str, tablo: str = "", kayit_id=None, detay: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO hareketler(zaman, islem, tablo, kayit_id, detay) VALUES (?,?,?,?,?)",
        (simdi(), islem, tablo, kayit_id, json.dumps(detay or {}, ensure_ascii=False)),
    )


def ayar_oku(conn, anahtar: str, varsayilan: str = "") -> str:
    satir = conn.execute("SELECT deger FROM ayarlar WHERE anahtar=?", (anahtar,)).fetchone()
    return satir["deger"] if satir else varsayilan


def ayar_yaz(conn, anahtar: str, deger: str) -> None:
    conn.execute(
        "INSERT INTO ayarlar(anahtar, deger) VALUES (?,?) "
        "ON CONFLICT(anahtar) DO UPDATE SET deger=excluded.deger",
        (anahtar, deger),
    )


# --------------------------------------------------------------------------- #
# Gram fiyatı
# --------------------------------------------------------------------------- #
def fiyat_getir(tarih: str | None = None) -> float:
    """`tarih` (veya bugün) itibarıyla geçerli gram fiyatı; yoksa son kayıt."""
    hedef = tarih or bugun()
    with db() as conn:
        satir = conn.execute(
            "SELECT gram_fiyat FROM fiyatlar WHERE tarih<=? ORDER BY tarih DESC LIMIT 1",
            (hedef,),
        ).fetchone()
        if not satir:
            satir = conn.execute(
                "SELECT gram_fiyat FROM fiyatlar ORDER BY tarih DESC LIMIT 1"
            ).fetchone()
        if satir:
            return float(satir["gram_fiyat"])
        return float(ayar_oku(conn, "gram_fiyat", "0") or 0)


def fiyat_kaydet(tarih: str, gram_fiyat: float, kaynak: str = "manuel") -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO fiyatlar(tarih, gram_fiyat, kaynak, kayit_zamani) VALUES (?,?,?,?) "
            "ON CONFLICT(tarih) DO UPDATE SET gram_fiyat=excluded.gram_fiyat, "
            "kaynak=excluded.kaynak, kayit_zamani=excluded.kayit_zamani",
            (tarih, gram_fiyat, kaynak, simdi()),
        )
        ayar_yaz(conn, "gram_fiyat", str(gram_fiyat))
        audit(conn, "fiyat_guncelle", "fiyatlar", detay={"tarih": tarih, "fiyat": gram_fiyat})


def fiyat_gecmisi(limit: int = 30) -> list[dict]:
    with db() as conn:
        satirlar = conn.execute(
            "SELECT tarih, gram_fiyat, kaynak, kayit_zamani FROM fiyatlar "
            "ORDER BY tarih DESC LIMIT ?", (limit,),
        ).fetchall()
        return [dict(s) for s in satirlar]


# --------------------------------------------------------------------------- #
# Bakiye hesapları (FIFO)
# --------------------------------------------------------------------------- #
def _fifo_acik(satislar: list[dict], odeme_toplam: float) -> list[dict]:
    """Ödemeyi en eski satıştan başlayarak uygular; ödenmemiş kısımları döndürür."""
    kalan = odeme_toplam
    acik = []
    for s in sorted(satislar, key=lambda x: (x["tarih"], x["id"])):
        if kalan >= s["tutar"] - 1e-9:
            kalan -= s["tutar"]
            continue
        acik.append({**s, "acik_kalan": s["tutar"] - kalan})
        kalan = 0.0
    return acik


def musteri_bakiye(conn, musteri_id: int) -> dict:
    """Tek müşterinin bakiyesi + en eski ödenmemiş vade (FIFO)."""
    satislar = [
        dict(r)
        for r in conn.execute(
            "SELECT id, tarih, vade, para_birimi, tutar FROM satislar "
            "WHERE musteri_id=? AND durum='aktif' AND sekl!='pesin'", (musteri_id,)
        )
    ]
    odemeler = conn.execute(
        "SELECT hedef, COALESCE(SUM(uygulanan),0) AS toplam FROM odemeler "
        "WHERE musteri_id=? AND durum='aktif' GROUP BY hedef", (musteri_id,)
    ).fetchall()
    odl = {r["hedef"]: float(r["toplam"]) for r in odemeler}

    tl_satis = [s for s in satislar if s["para_birimi"] == "tl"]
    gr_satis = [s for s in satislar if s["para_birimi"] == "altin"]

    tl_borc = sum(s["tutar"] for s in tl_satis) - odl.get("tl", 0.0)
    gr_borc = sum(s["tutar"] for s in gr_satis) - odl.get("altin", 0.0)

    # En eski ödenmemiş vade (para birimi bağımsız, FIFO)
    en_eski = ""
    if tl_borc > 1e-9:
        for s in _fifo_acik(tl_satis, odl.get("tl", 0.0)):
            if s["vade"]:
                en_eski = s["vade"] if not en_eski else min(en_eski, s["vade"])
    if gr_borc > 1e-9:
        for s in _fifo_acik(gr_satis, odl.get("altin", 0.0)):
            if s["vade"]:
                en_eski = s["vade"] if not en_eski else min(en_eski, s["vade"])

    gecikme = 0
    borclu = (tl_borc > 1e-9) or (gr_borc > 1e-9)
    if borclu and en_eski and en_eski < bugun():
        gecikme = (date.fromisoformat(bugun()) - date.fromisoformat(en_eski)).days

    return {
        "tl_borc": round(tl_borc, 2),
        "altin_borc": round(gr_borc, 4),
        "en_eski_vade": en_eski if borclu else "",
        "gecikme_gun": gecikme,
        "borclu": borclu,
    }


# --------------------------------------------------------------------------- #
# Müşteriler
# --------------------------------------------------------------------------- #
def musteriler(q: str = "", durum: str = "aktif", sadece_borclu: bool = False) -> list[dict]:
    with db() as conn:
        sql = "SELECT * FROM musteriler WHERE durum=?"
        params: list = [durum]
        if q:
            sql += " AND (ad LIKE ? OR telefon LIKE ? OR adres LIKE ?)"
            params += [f"%{q}%"] * 3
        satirlar = [dict(r) for r in conn.execute(sql + " ORDER BY ad COLLATE NOCASE", params)]
        for m in satirlar:
            m.update(musteri_bakiye(conn, m["id"]))
        if sadece_borclu:
            satirlar = [m for m in satirlar if m["borclu"]]
        return satirlar


def musteri_getir(musteri_id: int) -> dict | None:
    with db() as conn:
        satir = conn.execute("SELECT * FROM musteriler WHERE id=?", (musteri_id,)).fetchone()
        if not satir:
            return None
        m = dict(satir)
        m.update(musteri_bakiye(conn, musteri_id))
        return m


def musteri_ekle(ad: str, telefon: str = "", adres: str = "", notlar: str = "",
                 limit_tl: float = 0.0, kategori: str = "") -> int:
    ad = (ad or "").strip()
    if not ad:
        raise ValueError("Müşteri adı boş olamaz.")
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO musteriler(ad, telefon, adres, notlar, limit_tl, kategori, "
            "durum, olusturma) VALUES (?,?,?,?,?,?,'aktif',?)",
            (ad, telefon.strip(), adres.strip(), notlar.strip(), limit_tl,
             kategori.strip(), simdi()),
        )
        audit(conn, "musteri_ekle", "musteriler", cur.lastrowid, {"ad": ad})
        return cur.lastrowid


def musteri_guncelle(musteri_id: int, ad: str, telefon: str, adres: str,
                     notlar: str, limit_tl: float, kategori: str = "",
                     sozu_tarih: str = "", sozu_not: str = "") -> None:
    ad = (ad or "").strip()
    if not ad:
        raise ValueError("Müşteri adı boş olamaz.")
    with db() as conn:
        eski = conn.execute("SELECT * FROM musteriler WHERE id=?", (musteri_id,)).fetchone()
        if not eski:
            raise ValueError("Müşteri bulunamadı.")
        conn.execute(
            "UPDATE musteriler SET ad=?, telefon=?, adres=?, notlar=?, limit_tl=?, "
            "kategori=?, sozu_tarih=?, sozu_not=?, guncelleme=? WHERE id=?",
            (ad, telefon.strip(), adres.strip(), notlar.strip(), limit_tl,
             kategori.strip(), sozu_tarih or "", sozu_not or "", simdi(), musteri_id),
        )
        audit(conn, "musteri_guncelle", "musteriler", musteri_id,
              {"oncesi": dict(eski),
               "sonrasi": {"ad": ad, "telefon": telefon, "limit_tl": limit_tl,
                           "kategori": kategori, "sozu_tarih": sozu_tarih}})


def musteri_durum(musteri_id: int, durum: str) -> None:
    """Müşteriyi arşivler veya geri alır. SİLME YOKTUR."""
    if durum not in ("aktif", "arsiv"):
        raise ValueError("Geçersiz durum.")
    with db() as conn:
        conn.execute("UPDATE musteriler SET durum=?, guncelleme=? WHERE id=?",
                     (durum, simdi(), musteri_id))
        audit(conn, "musteri_arsivle" if durum == "arsiv" else "musteri_geri_al",
              "musteriler", musteri_id, {"durum": durum})


# --------------------------------------------------------------------------- #
# Veresiye satışları
# --------------------------------------------------------------------------- #
def satis_ekle(musteri_id: int, tarih: str, para_birimi: str, tutar: float,
               vade: str = "", aciklama: str = "", gram_fiyat: float | None = None,
               sekl: str = "veresiye", urun_id: int = 0) -> int:
    if para_birimi not in ("tl", "altin"):
        raise ValueError("Para birimi TL veya gram altın olmalı.")
    if sekl not in ("veresiye", "pesin"):
        sekl = "veresiye"
    if tutar <= 0:
        raise ValueError("Tutar sıfırdan büyük olmalı.")
    if sekl == "pesin":
        vade = ""
    if sekl == "veresiye" and vade and vade < tarih:
        raise ValueError("Vade tarihi satış tarihinden önce olamaz.")
    with db() as conn:
        if not conn.execute("SELECT 1 FROM musteriler WHERE id=?", (musteri_id,)).fetchone():
            raise ValueError("Müşteri bulunamadı.")
        gf = gram_fiyat
        if para_birimi == "altin":
            gf = float(gf) if gf else fiyat_getir(tarih)
        else:
            gf = float(gf or 0)
        cur = conn.execute(
            "INSERT INTO satislar(musteri_id, tarih, vade, para_birimi, tutar, gram_fiyat, "
            "aciklama, sekl, urun_id, kayit_zamani) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (musteri_id, tarih, vade or "", para_birimi, tutar, gf,
             (aciklama or "").strip(), sekl, urun_id, simdi()),
        )
        audit(conn, ("pesin_satis_ekle" if sekl == "pesin" else "satis_ekle"),
              "satislar", cur.lastrowid,
              {"musteri_id": musteri_id, "pb": para_birimi, "tutar": tutar,
               "vade": vade, "aciklama": aciklama, "sekl": sekl})
        return cur.lastrowid


def satis_iptal(satis_id: int, sebep: str) -> None:
    """Satış iptal edilir; kayıt silinmez, geçmişte kalır."""
    if not (sebep or "").strip():
        raise ValueError("İptal için sebep girmelisiniz.")
    with db() as conn:
        eski = conn.execute("SELECT * FROM satislar WHERE id=?", (satis_id,)).fetchone()
        if not eski:
            raise ValueError("Satış bulunamadı.")
        if eski["durum"] != "aktif":
            raise ValueError("Bu satış zaten iptal edilmiş.")
        conn.execute("UPDATE satislar SET durum='iptal', iptal_sebebi=?, guncelleme=? WHERE id=?",
                     (sebep.strip(), simdi(), satis_id))
        audit(conn, "satis_iptal", "satislar", satis_id,
              {"oncesi": dict(eski), "sebep": sebep.strip()})


def satislar(musteri_id: int | None = None, baslangic: str = "", bitis: str = "",
             para_birimi: str = "", durum: str = "aktif", limit: int = 0,
             sekl: str = "") -> list[dict]:
    with db() as conn:
        sql = ("SELECT s.*, m.ad AS musteri_ad FROM satislar s "
               "JOIN musteriler m ON m.id=s.musteri_id WHERE 1=1")
        params: list = []
        if musteri_id:
            sql += " AND s.musteri_id=?"
            params.append(musteri_id)
        if baslangic:
            sql += " AND s.tarih>=?"
            params.append(baslangic)
        if bitis:
            sql += " AND s.tarih<=?"
            params.append(bitis)
        if para_birimi:
            sql += " AND s.para_birimi=?"
            params.append(para_birimi)
        if sekl:
            sql += " AND s.sekl=?"
            params.append(sekl)
        if durum:
            sql += " AND s.durum=?"
            params.append(durum)
        sql += " ORDER BY s.tarih DESC, s.id DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return [dict(r) for r in conn.execute(sql, params)]


# --------------------------------------------------------------------------- #
# Tahsilatlar
# --------------------------------------------------------------------------- #
def odeme_ekle(musteri_id: int, tarih: str, para_birimi: str, tutar: float,
               hedef: str, yontem: str = "nakit", aciklama: str = "",
               kur: float | None = None) -> int:
    if para_birimi not in ("tl", "altin"):
        raise ValueError("Para birimi TL veya gram altın olmalı.")
    if hedef not in ("tl", "altin"):
        raise ValueError("Hedef borç TL veya altın olmalı.")
    if tutar <= 0:
        raise ValueError("Tutar sıfırdan büyük olmalı.")

    with db() as conn:
        if not conn.execute("SELECT 1 FROM musteriler WHERE id=?", (musteri_id,)).fetchone():
            raise ValueError("Müşteri bulunamadı.")

        if para_birimi == hedef:
            uygulanan, kullanilan_kur = tutar, float(kur or 0)
        else:
            kullanilan_kur = float(kur) if kur else fiyat_getir(tarih)
            if kullanilan_kur <= 0:
                raise ValueError("Çevrim için güncel gram fiyatı gerekli (Ayarlar'dan girin).")
            # tl ile altın borcu kapatma: tutar / kur  |  altın ile tl borcu kapatma: tutar * kur
            uygulanan = (tutar / kullanilan_kur) if para_birimi == "tl" else (tutar * kullanilan_kur)

        cur = conn.execute(
            "INSERT INTO odemeler(musteri_id, tarih, para_birimi, tutar, hedef, uygulanan, "
            "kur, yontem, aciklama, kayit_zamani) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (musteri_id, tarih, para_birimi, tutar, hedef, round(uygulanan, 6),
             kullanilan_kur, yontem, (aciklama or "").strip(), simdi()),
        )
        audit(conn, "odeme_ekle", "odemeler", cur.lastrowid,
              {"musteri_id": musteri_id, "pb": para_birimi, "tutar": tutar,
               "hedef": hedef, "uygulanan": uygulanan, "kur": kullanilan_kur})
        return cur.lastrowid


def odeme_iptal(odeme_id: int, sebep: str) -> None:
    if not (sebep or "").strip():
        raise ValueError("İptal için sebep girmelisiniz.")
    with db() as conn:
        eski = conn.execute("SELECT * FROM odemeler WHERE id=?", (odeme_id,)).fetchone()
        if not eski:
            raise ValueError("Tahsilat bulunamadı.")
        if eski["durum"] != "aktif":
            raise ValueError("Bu tahsilat zaten iptal edilmiş.")
        conn.execute("UPDATE odemeler SET durum='iptal', iptal_sebebi=?, guncelleme=? WHERE id=?",
                     (sebep.strip(), simdi(), odeme_id))
        audit(conn, "odeme_iptal", "odemeler", odeme_id,
              {"oncesi": dict(eski), "sebep": sebep.strip()})


def odemeler(musteri_id: int | None = None, baslangic: str = "", bitis: str = "",
             durum: str = "aktif", limit: int = 0) -> list[dict]:
    with db() as conn:
        sql = ("SELECT o.*, m.ad AS musteri_ad FROM odemeler o "
               "JOIN musteriler m ON m.id=o.musteri_id WHERE 1=1")
        params: list = []
        if musteri_id:
            sql += " AND o.musteri_id=?"
            params.append(musteri_id)
        if baslangic:
            sql += " AND o.tarih>=?"
            params.append(baslangic)
        if bitis:
            sql += " AND o.tarih<=?"
            params.append(bitis)
        if durum:
            sql += " AND o.durum=?"
            params.append(durum)
        sql += " ORDER BY o.tarih DESC, o.id DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return [dict(r) for r in conn.execute(sql, params)]


# --------------------------------------------------------------------------- #
# Hesap ekstresi
# --------------------------------------------------------------------------- #
def ekstre(musteri_id: int) -> dict:
    """Küçükten büyüğe sıralı, yürüyen bakiyeli hesap ekstresi."""
    with db() as conn:
        m = conn.execute("SELECT * FROM musteriler WHERE id=?", (musteri_id,)).fetchone()
        if not m:
            raise ValueError("Müşteri bulunamadı.")
        satislar = [dict(r) for r in conn.execute(
            "SELECT * FROM satislar WHERE musteri_id=? AND durum='aktif'", (musteri_id,))]
        odemeler = [dict(r) for r in conn.execute(
            "SELECT * FROM odemeler WHERE musteri_id=? AND durum='aktif'", (musteri_id,))]
        iptaller = [dict(r) for r in conn.execute(
            "SELECT 'satis' AS tur, id, tarih, tutar, para_birimi, iptal_sebebi, kayit_zamani "
            "FROM satislar WHERE musteri_id=? AND durum='iptal' "
            "UNION ALL SELECT 'odeme', id, tarih, tutar, para_birimi, iptal_sebebi, kayit_zamani "
            "FROM odemeler WHERE musteri_id=? AND durum='iptal' ORDER BY tarih",
            (musteri_id, musteri_id))]

        satirlar = []
        for s in satislar:
            satirlar.append({
                "tur": "satis", "id": s["id"], "tarih": s["tarih"], "vade": s["vade"],
                "aciklama": s["aciklama"], "para_birimi": s["para_birimi"],
                "borc": s["tutar"], "tahsilat": 0.0, "gram_fiyat": s["gram_fiyat"],
                "zaman": s["kayit_zamani"],
            })
        for o in odemeler:
            satirlar.append({
                "tur": "odeme", "id": o["id"], "tarih": o["tarih"], "vade": "",
                "aciklama": (o["aciklama"] or o["yontem"]),
                "para_birimi": o["hedef"], "borc": 0.0,
                "tahsilat": o["uygulanan"], "gram_fiyat": o["kur"],
                "zaman": o["kayit_zamani"],
            })
        satirlar.sort(key=lambda r: (r["tarih"], r["zaman"], r["tur"], r["id"]))

        tl, gr = 0.0, 0.0
        for r in satirlar:
            if r["para_birimi"] == "tl":
                tl += r["borc"] - r["tahsilat"]
            else:
                gr += r["borc"] - r["tahsilat"]
            r["tl_bakiye"] = round(tl, 2)
            r["altin_bakiye"] = round(gr, 4)

        bakiye = musteri_bakiye(conn, musteri_id)
        return {
            "musteri": dict(m),
            "satirlar": satirlar,
            "iptaller": [dict(r) for r in iptaller],
            "bakiye": bakiye,
        }


# --------------------------------------------------------------------------- #
# Panel (gösterge) verisi
# --------------------------------------------------------------------------- #
def panel() -> dict:
    with db() as conn:
        musteriler_list = [dict(r) for r in conn.execute(
            "SELECT * FROM musteriler WHERE durum='aktif'")]
        for m in musteriler_list:
            m.update(musteri_bakiye(conn, m["id"]))

        tl_toplam = sum(m["tl_borc"] for m in musteriler_list)
        gr_toplam = sum(m["altin_borc"] for m in musteriler_list)
        borclu = [m for m in musteriler_list if m["borclu"]]
        gecikmis = sorted([m for m in borclu if m["gecikme_gun"] > 0],
                          key=lambda x: -x["gecikme_gun"])

        bugun_tarih = bugun()
        ay_bas = bugun_tarih[:8] + "01"

        def tahsilat_tlpk(bas: str, bit: str) -> tuple[float, float, float]:
            """(TL tahsilat, altın tahsilat(gr), güncel fiyatla TL eşdeğeri)"""
            rows = conn.execute(
                "SELECT hedef, SUM(uygulanan) AS t FROM odemeler "
                "WHERE durum='aktif' AND tarih>=? AND tarih<=? GROUP BY hedef",
                (bas, bit),
            ).fetchall()
            d = {r["hedef"]: float(r["t"]) for r in rows}
            tl = d.get("tl", 0.0)
            gr = d.get("altin", 0.0)
            return tl, gr, tl + gr * fiyat_getir()

        bugun_tl, bugun_gr, bugun_esdeger = tahsilat_tlpk(bugun_tarih, bugun_tarih)
        ay_tl, ay_gr, ay_esdeger = tahsilat_tlpk(ay_bas, bugun_tarih)

        satis_ay = conn.execute(
            "SELECT para_birimi, SUM(tutar) AS t FROM satislar "
            "WHERE durum='aktif' AND sekl='veresiye' AND tarih>=? AND tarih<=? "
            "GROUP BY para_birimi", (ay_bas, bugun_tarih),
        ).fetchall()
        satis_d = {r["para_birimi"]: float(r["t"]) for r in satis_ay}

        pesin_ay = conn.execute(
            "SELECT COALESCE(SUM(tutar),0) AS t FROM satislar "
            "WHERE durum='aktif' AND sekl='pesin' AND para_birimi='tl' "
            "AND tarih>=? AND tarih<=?", (ay_bas, bugun_tarih),
        ).fetchone()["t"]

        # Çek & senet portföyü
        cek_portfoy = conn.execute(
            "SELECT tur, COUNT(*) AS adet, COALESCE(SUM(tutar),0) AS toplam "
            "FROM cekler WHERE durum='portfoy' GROUP BY tur"
        ).fetchall()
        portfoy = {r["tur"]: {"adet": r["adet"], "toplam": float(r["toplam"])}
                   for r in cek_portfoy}

        # Tedarikçi borcumuz (bizim dış borcumuz)
        tedarik_borc = conn.execute(
            "SELECT COALESCE((SELECT COALESCE(SUM(tutar),0) FROM alislar a "
            "JOIN tedarikciler t ON t.id=a.tedarikci_id WHERE a.durum='aktif' AND t.durum='aktif'),0) "
            "- COALESCE((SELECT COALESCE(SUM(o.tutar),0) FROM tedarik_odemeler o "
            "JOIN tedarikciler t ON t.id=o.tedarikci_id WHERE o.durum='aktif' AND t.durum='aktif'),0)"
        ).fetchone()[0]

        # Ödeme sözü vermiş borçlu müşteriler
        sozlu = []
        for m in conn.execute(
            "SELECT * FROM musteriler "
            "WHERE durum='aktif' AND sozu_tarih!='' AND sozu_tarih>=?",
            (bugun_tarih,)):
            b = musteri_bakiye(conn, m["id"])
            if b["borclu"]:
                sozlu.append({**dict(m), **b})

        son_satislar = [dict(r) for r in conn.execute(
            "SELECT s.*, m.ad AS musteri_ad FROM satislar s JOIN musteriler m ON m.id=s.musteri_id "
            "ORDER BY s.kayit_zamani DESC LIMIT 6")]
        son_odemeler = [dict(r) for r in conn.execute(
            "SELECT o.*, m.ad AS musteri_ad FROM odemeler o JOIN musteriler m ON m.id=o.musteri_id "
            "ORDER BY o.kayit_zamani DESC LIMIT 6")]

        son_yedek = conn.execute(
            "SELECT * FROM yedekler ORDER BY id DESC LIMIT 1").fetchone()

        return {
            "musteri_sayisi": len(musteriler_list),
            "borclu_sayisi": len(borclu),
            "tl_toplam": round(tl_toplam, 2),
            "gr_toplam": round(gr_toplam, 4),
            "gr_deger": round(gr_toplam * fiyat_getir(), 2),
            "genel_deger": round(tl_toplam + gr_toplam * fiyat_getir(), 2),
            "gecikmis": gecikmis[:8],
            "gecikmis_sayisi": len(gecikmis),
            "bugun_tl": round(bugun_tl, 2),
            "bugun_gr": round(bugun_gr, 4),
            "bugun_esdeger": round(bugun_esdeger, 2),
            "ay_tl": round(ay_tl, 2),
            "ay_gr": round(ay_gr, 4),
            "ay_esdeger": round(ay_esdeger, 2),
            "ay_satis_tl": round(satis_d.get("tl", 0.0), 2),
            "ay_satis_gr": round(satis_d.get("altin", 0.0), 4),
            "ay_pesin_tl": round(float(pesin_ay), 2),
            "cek_portfoy": {
                "cek_adet": portfoy.get("cek", {}).get("adet", 0),
                "cek_toplam": round(portfoy.get("cek", {}).get("toplam", 0.0), 2),
                "senet_adet": portfoy.get("senet", {}).get("adet", 0),
                "senet_toplam": round(portfoy.get("senet", {}).get("toplam", 0.0), 2),
            },
            "tedarik_borc": round(float(tedarik_borc), 2),
            "odeme_sozleri": sozlu,
            "kasa_bugun": round(kasa_ozet_tarih(bugun_tarih, bugun_tarih), 2),
            "son_hareketler": _son_hareketler(son_satislar, son_odemeler),
            "son_yedek": dict(son_yedek) if son_yedek else None,
            "gram_fiyat": fiyat_getir(),
        }


def _son_hareketler(satislar: list[dict], odemeler: list[dict]) -> list[dict]:
    liste = []
    for s in satislar:
        liste.append({
            "tur": "Satış", "zaman": s["kayit_zamani"], "tarih": s["tarih"],
            "musteri": s["musteri_ad"], "pb": s["para_birimi"], "tutar": s["tutar"],
            "durum": s["durum"], "id": s["id"],
        })
    for o in odemeler:
        liste.append({
            "tur": "Tahsilat", "zaman": o["kayit_zamani"], "tarih": o["tarih"],
            "musteri": o["musteri_ad"], "pb": o["para_birimi"], "tutar": o["tutar"],
            "durum": o["durum"], "id": o["id"],
        })
    liste.sort(key=lambda x: x["zaman"], reverse=True)
    return liste[:8]


# --------------------------------------------------------------------------- #
# Raporlar
# --------------------------------------------------------------------------- #
def rapor_aylik(ay_sayisi: int = 6) -> list[dict]:
    """Son N ayın satış/tahsilat özeti (TL eşdeğeri)."""
    with db() as conn:
        bugun = date.today()
        sonuclar = []
        for i in range(ay_sayisi):
            y = bugun.year
            m = bugun.month - i
            while m <= 0:
                m += 12
                y -= 1
            bas = f"{y:04d}-{m:02d}-01"
            bit = f"{y:04d}-{m:02d}-31"
            s = {r["para_birimi"]: float(r["t"]) for r in conn.execute(
                "SELECT para_birimi, SUM(tutar) AS t FROM satislar "
                "WHERE durum='aktif' AND sekl='veresiye' AND tarih>=? AND tarih<=? "
                "GROUP BY para_birimi", (bas, bit))}
            pesin = float(conn.execute(
                "SELECT COALESCE(SUM(tutar),0) FROM satislar "
                "WHERE durum='aktif' AND sekl='pesin' AND para_birimi='tl' "
                "AND tarih>=? AND tarih<=?", (bas, bit)).fetchone()[0])
            o = {r["hedef"]: float(r["t"]) for r in conn.execute(
                "SELECT hedef, SUM(uygulanan) AS t FROM odemeler "
                "WHERE durum='aktif' AND tarih>=? AND tarih<=? GROUP BY hedef", (bas, bit))}
            sonuclar.append({
                "ay": f"{y:04d}-{m:02d}",
                "satis_tl": round(s.get("tl", 0.0), 2),
                "satis_gr": round(s.get("altin", 0.0), 4),
                "pesin_tl": round(pesin, 2),
                "tahsilat_tl": round(o.get("tl", 0.0), 2),
                "tahsilat_gr": round(o.get("altin", 0.0), 4),
            })
        return sonuclar


def en_borclular(limit: int = 15) -> list[dict]:
    liste = musteriler(durum="aktif", sadece_borclu=True)
    liste.sort(key=lambda m: -(m["tl_borc"] + m["altin_borc"] * fiyat_getir()))
    return liste[:limit]


def yaslandirma() -> dict:
    """Vadesi geçen alacakların gün aralıklarına göre dökümü (yaşlandırma).

    TL borçlar esas alınır; altın borç güncel gram fiyatıyla TL'ye çevrilir.
    """
    kur = fiyat_getir()
    kova = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    gecikenler: list[dict] = []
    for m in musteriler(durum="aktif", sadece_borclu=True):
        gun = int(m.get("gecikme_gun") or 0)
        if gun <= 0:
            continue   # vadesi henüz gelmemiş
        deger = float(m["tl_borc"]) + float(m["altin_borc"]) * kur
        aralik = ("0-30" if gun <= 30 else
                  "31-60" if gun <= 60 else
                  "61-90" if gun <= 90 else "90+")
        kova[aralik] = round(kova[aralik] + deger, 2)
        gecikenler.append(m)
    gecikenler.sort(key=lambda m: -int(m.get("gecikme_gun") or 0))
    return {"kova": kova, "gecikenler": gecikenler}


def tahsilat_orani(ay_sayisi: int = 3) -> float:
    """Son N ayda veresiye satışlarına karşı tahsilat yüzdesi (TL)."""
    rapor = rapor_aylik(ay_sayisi)
    satis = sum(float(r["satis_tl"]) for r in rapor)
    tahsilat = sum(float(r["tahsilat_tl"]) for r in rapor)
    if satis <= 0:
        return 0.0
    return round(100.0 * tahsilat / satis, 1)


def hareket_gecmisi(limit: int = 200) -> list[dict]:
    with db() as conn:
        satirlar = conn.execute(
            "SELECT * FROM hareketler ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in satirlar:
            d = dict(r)
            try:
                d["detay_nesne"] = json.loads(d["detay"])
            except Exception:
                d["detay_nesne"] = {}
            out.append(d)
        return out


# --------------------------------------------------------------------------- #
# Dışa aktarma (CSV)
# --------------------------------------------------------------------------- #
def _csv_satirlari(basliklar: list[str], satirlar: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(basliklar)
    w.writerows(satirlar)
    return "﻿" + buf.getvalue()   # Excel için UTF-8 BOM


def csv_musteriler() -> str:
    satirlar = [[m["id"], m["ad"], m["telefon"], m["tl_borc"], m["altin_borc"],
                 m["en_eski_vade"], m["gecikme_gun"], m["limit_tl"]]
                for m in musteriler(durum="")]
    return _csv_satirlari(
        ["ID", "Ad Soyad", "Telefon", "TL Borç", "Altın Borç (gr)", "En Eski Vade",
         "Gecikme (gün)", "Limit (TL)"], satirlar)


def csv_satislar(baslangic: str = "", bitis: str = "") -> str:
    satirlar = [[s["id"], s["musteri_ad"], s["tarih"], s["vade"], s["para_birimi"],
                 s["tutar"], s["gram_fiyat"], s["aciklama"], s["sekl"], s["durum"]]
                for s in satislar(baslangic=baslangic, bitis=bitis, durum="")]
    return _csv_satirlari(
        ["ID", "Müşteri", "Tarih", "Vade", "Para Birimi", "Tutar", "Gram Fiyat",
         "Açıklama", "Satış Şekli", "Durum"], satirlar)


def csv_odemeler(baslangic: str = "", bitis: str = "") -> str:
    satirlar = [[o["id"], o["musteri_ad"], o["tarih"], o["para_birimi"], o["tutar"],
                 o["hedef"], o["uygulanan"], o["kur"], o["yontem"], o["durum"]]
                for o in odemeler(baslangic=baslangic, bitis=bitis, durum="")]
    return _csv_satirlari(
        ["ID", "Müşteri", "Tarih", "Ödenen PB", "Tutar", "Hedef Borç", "Uygulanan",
         "Kur (TL/gr)", "Yöntem", "Durum"], satirlar)


def tam_disa_aktarim() -> dict:
    """Tüm verilerin JSON yedeği (indirilebilir)."""
    with db() as conn:
        return {
            "olusturma": simdi(),
            "surum": "2.0",
            "musteriler": [dict(r) for r in conn.execute("SELECT * FROM musteriler")],
            "satislar": [dict(r) for r in conn.execute("SELECT * FROM satislar")],
            "odemeler": [dict(r) for r in conn.execute("SELECT * FROM odemeler")],
            "fiyatlar": [dict(r) for r in conn.execute("SELECT * FROM fiyatlar")],
            "ayarlar": [dict(r) for r in conn.execute("SELECT * FROM ayarlar")],
            "hareketler": [dict(r) for r in conn.execute("SELECT * FROM hareketler")],
            "urunler": [dict(r) for r in conn.execute("SELECT * FROM urunler")],
            "tedarikciler": [dict(r) for r in conn.execute("SELECT * FROM tedarikciler")],
            "alislar": [dict(r) for r in conn.execute("SELECT * FROM alislar")],
            "tedarik_odemeler": [dict(r) for r in conn.execute("SELECT * FROM tedarik_odemeler")],
            "cekler": [dict(r) for r in conn.execute("SELECT * FROM cekler")],
            "kasa": [dict(r) for r in conn.execute("SELECT * FROM kasa")],
        }


# --------------------------------------------------------------------------- #
# Ürün kataloğu (birim fiyat yönetimi)
# --------------------------------------------------------------------------- #
def urunler(q: str = "", durum: str = "aktif") -> list[dict]:
    with db() as conn:
        sql = "SELECT * FROM urunler WHERE durum=?"
        params: list = [durum]
        if q:
            sql += " AND (ad LIKE ? OR notlar LIKE ?)"
            params += [f"%{q}%"] * 2
        return [dict(r) for r in conn.execute(sql + " ORDER BY ad COLLATE NOCASE", params)]


def urun_getir(urun_id: int) -> dict | None:
    with db() as conn:
        r = conn.execute("SELECT * FROM urunler WHERE id=?", (urun_id,)).fetchone()
        return dict(r) if r else None


def urun_ekle(ad: str, birim: str = "adet", tl_fiyat: float = 0.0,
              gr_miktar: float = 0.0, notlar: str = "") -> int:
    ad = (ad or "").strip()
    if not ad:
        raise ValueError("Ürün adı boş olamaz.")
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO urunler(ad, birim, tl_fiyat, gr_miktar, notlar, kayit_zamani) "
            "VALUES (?,?,?,?,?,?)",
            (ad, birim.strip(), tl_fiyat, gr_miktar, notlar.strip(), simdi()),
        )
        audit(conn, "urun_ekle", "urunler", cur.lastrowid, {"ad": ad})
        return cur.lastrowid


def urun_guncelle(urun_id: int, ad: str, birim: str, tl_fiyat: float,
                  gr_miktar: float, notlar: str = "") -> None:
    ad = (ad or "").strip()
    if not ad:
        raise ValueError("Ürün adı boş olamaz.")
    with db() as conn:
        eski = conn.execute("SELECT * FROM urunler WHERE id=?", (urun_id,)).fetchone()
        if not eski:
            raise ValueError("Ürün bulunamadı.")
        conn.execute(
            "UPDATE urunler SET ad=?, birim=?, tl_fiyat=?, gr_miktar=?, notlar=?, "
            "guncelleme=? WHERE id=?",
            (ad, birim.strip(), tl_fiyat, gr_miktar, notlar.strip(), simdi(), urun_id),
        )
        audit(conn, "urun_fiyat_guncelle", "urunler", urun_id,
              {"oncesi": dict(eski), "sonrasi": {"ad": ad, "tl_fiyat": tl_fiyat,
                                                 "gr_miktar": gr_miktar}})


def urun_durum(urun_id: int, durum: str) -> None:
    if durum not in ("aktif", "arsiv"):
        raise ValueError("Geçersiz durum.")
    with db() as conn:
        conn.execute("UPDATE urunler SET durum=?, guncelleme=? WHERE id=?",
                     (durum, simdi(), urun_id))
        audit(conn, "urun_arsivle" if durum == "arsiv" else "urun_geri_al",
              "urunler", urun_id, {"durum": durum})


# --------------------------------------------------------------------------- #
# Tedarikçiler (bizim borcumuz)
# --------------------------------------------------------------------------- #
def _tedarik_bakiye(conn, tedarikci_id: int) -> dict:
    alis = float(conn.execute(
        "SELECT COALESCE(SUM(tutar),0) FROM alislar "
        "WHERE tedarikci_id=? AND durum='aktif'", (tedarikci_id,)).fetchone()[0])
    odeme = float(conn.execute(
        "SELECT COALESCE(SUM(tutar),0) FROM tedarik_odemeler "
        "WHERE tedarikci_id=? AND durum='aktif'", (tedarikci_id,)).fetchone()[0])
    borc = alis - odeme
    return {"alis_toplam": round(alis, 2), "odeme_toplam": round(odeme, 2),
            "borc": round(borc, 2), "borclu": borc > 0.004,
            "avans": borc < -0.004}


def tedarikciler(q: str = "", durum: str = "aktif") -> list[dict]:
    with db() as conn:
        sql = "SELECT * FROM tedarikciler WHERE durum=?"
        params: list = [durum]
        if q:
            sql += " AND (ad LIKE ? OR telefon LIKE ?)"
            params += [f"%{q}%"] * 2
        liste = [dict(r) for r in conn.execute(sql + " ORDER BY ad COLLATE NOCASE", params)]
        for t in liste:
            t.update(_tedarik_bakiye(conn, t["id"]))
        return liste


def tedarikci_getir(tedarikci_id: int) -> dict | None:
    with db() as conn:
        r = conn.execute("SELECT * FROM tedarikciler WHERE id=?", (tedarikci_id,)).fetchone()
        if not r:
            return None
        t = dict(r)
        t.update(_tedarik_bakiye(conn, tedarikci_id))
        return t


def tedarikci_ekle(ad: str, telefon: str = "", notlar: str = "") -> int:
    ad = (ad or "").strip()
    if not ad:
        raise ValueError("Tedarikçi adı boş olamaz.")
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO tedarikciler(ad, telefon, notlar, olusturma) VALUES (?,?,?,?)",
            (ad, telefon.strip(), notlar.strip(), simdi()),
        )
        audit(conn, "tedarikci_ekle", "tedarikciler", cur.lastrowid, {"ad": ad})
        return cur.lastrowid


def tedarikci_duzenle(tedarikci_id: int, ad: str, telefon: str, notlar: str) -> None:
    ad = (ad or "").strip()
    if not ad:
        raise ValueError("Tedarikçi adı boş olamaz.")
    with db() as conn:
        eski = conn.execute("SELECT * FROM tedarikciler WHERE id=?",
                            (tedarikci_id,)).fetchone()
        if not eski:
            raise ValueError("Tedarikçi bulunamadı.")
        conn.execute("UPDATE tedarikciler SET ad=?, telefon=?, notlar=?, guncelleme=? "
                     "WHERE id=?", (ad, telefon.strip(), notlar.strip(), simdi(), tedarikci_id))
        audit(conn, "tedarikci_duzenle", "tedarikciler", tedarikci_id, {"ad": ad})


def tedarikci_durum(tedarikci_id: int, durum: str) -> None:
    if durum not in ("aktif", "arsiv"):
        raise ValueError("Geçersiz durum.")
    with db() as conn:
        conn.execute("UPDATE tedarikciler SET durum=?, guncelleme=? WHERE id=?",
                     (durum, simdi(), tedarikci_id))
        audit(conn, "tedarikci_arsivle" if durum == "arsiv" else "tedarikci_geri_al",
              "tedarikciler", tedarikci_id, {"durum": durum})


def tedarik_ekstre(tedarikci_id: int) -> dict:
    with db() as conn:
        t = conn.execute("SELECT * FROM tedarikciler WHERE id=?",
                         (tedarikci_id,)).fetchone()
        if not t:
            raise ValueError("Tedarikçi bulunamadı.")
        alislar = [dict(r) for r in conn.execute(
            "SELECT id, tarih, tutar, aciklama, kayit_zamani FROM alislar "
            "WHERE tedarikci_id=? AND durum='aktif'", (tedarikci_id,))]
        odemeler = [dict(r) for r in conn.execute(
            "SELECT id, tarih, tutar, yontem, aciklama, kayit_zamani FROM tedarik_odemeler "
            "WHERE tedarikci_id=? AND durum='aktif'", (tedarikci_id,))]
        iptaller = [dict(r) for r in conn.execute(
            "SELECT 'alis' AS tur, id, tarih, tutar, iptal_sebebi FROM alislar "
            "WHERE tedarikci_id=? AND durum='iptal' "
            "UNION ALL SELECT 'odeme', id, tarih, tutar, iptal_sebebi FROM tedarik_odemeler "
            "WHERE tedarikci_id=? AND durum='iptal' ORDER BY tarih",
            (tedarikci_id, tedarikci_id))]

        satirlar = []
        for a in alislar:
            satirlar.append({"tur": "alis", "id": a["id"], "tarih": a["tarih"],
                             "aciklama": a["aciklama"], "borc": a["tutar"],
                             "odeme": 0.0, "zaman": a["kayit_zamani"]})
        for o in odemeler:
            satirlar.append({"tur": "odeme", "id": o["id"], "tarih": o["tarih"],
                             "aciklama": (o["aciklama"] or o["yontem"]),
                             "borc": 0.0, "odeme": o["tutar"],
                             "zaman": o["kayit_zamani"]})
        satirlar.sort(key=lambda r: (r["tarih"], r["zaman"], r["tur"], r["id"]))

        bakiye = 0.0
        for r in satirlar:
            bakiye += r["borc"] - r["odeme"]
            r["bakiye"] = round(bakiye, 2)

        return {"tedarikci": dict(t), "satirlar": satirlar,
                "iptaller": iptaller, "bakiye": bakiye}


def alis_ekle(tedarikci_id: int, tarih: str, tutar: float, aciklama: str = "") -> int:
    tutar = float(tutar)
    if tutar <= 0:
        raise ValueError("Tutar sıfırdan büyük olmalı.")
    with db() as conn:
        if not conn.execute("SELECT 1 FROM tedarikciler WHERE id=?",
                            (tedarikci_id,)).fetchone():
            raise ValueError("Tedarikçi bulunamadı.")
        cur = conn.execute(
            "INSERT INTO alislar(tedarikci_id, tarih, tutar, aciklama, kayit_zamani) "
            "VALUES (?,?,?,?,?)",
            (tedarikci_id, tarih, tutar, (aciklama or "").strip(), simdi()),
        )
        audit(conn, "alis_ekle", "alislar", cur.lastrowid,
              {"tedarikci_id": tedarikci_id, "tutar": tutar})
        return cur.lastrowid


def alis_iptal(alis_id: int, sebep: str) -> None:
    if not (sebep or "").strip():
        raise ValueError("İptal için sebep girmelisiniz.")
    with db() as conn:
        eski = conn.execute("SELECT * FROM alislar WHERE id=?", (alis_id,)).fetchone()
        if not eski:
            raise ValueError("Alış bulunamadı.")
        if eski["durum"] != "aktif":
            raise ValueError("Bu alış zaten iptal edilmiş.")
        conn.execute("UPDATE alislar SET durum='iptal', iptal_sebebi=?, guncelleme=? "
                     "WHERE id=?", (sebep.strip(), simdi(), alis_id))
        audit(conn, "alis_iptal", "alislar", alis_id,
              {"oncesi": dict(eski), "sebep": sebep.strip()})


def tedarik_odeme_ekle(tedarikci_id: int, tarih: str, tutar: float,
                       yontem: str = "nakit", aciklama: str = "") -> int:
    tutar = float(tutar)
    if tutar <= 0:
        raise ValueError("Tutar sıfırdan büyük olmalı.")
    with db() as conn:
        if not conn.execute("SELECT 1 FROM tedarikciler WHERE id=?",
                            (tedarikci_id,)).fetchone():
            raise ValueError("Tedarikçi bulunamadı.")
        cur = conn.execute(
            "INSERT INTO tedarik_odemeler(tedarikci_id, tarih, tutar, yontem, aciklama, "
            "kayit_zamani) VALUES (?,?,?,?,?,?)",
            (tedarikci_id, tarih, tutar, yontem, (aciklama or "").strip(), simdi()),
        )
        audit(conn, "tedarik_odeme_ekle", "tedarik_odemeler", cur.lastrowid,
              {"tedarikci_id": tedarikci_id, "tutar": tutar})
        return cur.lastrowid


def tedarik_odeme_iptal(odeme_id: int, sebep: str) -> None:
    if not (sebep or "").strip():
        raise ValueError("İptal için sebep girmelisiniz.")
    with db() as conn:
        eski = conn.execute("SELECT * FROM tedarik_odemeler WHERE id=?",
                            (odeme_id,)).fetchone()
        if not eski:
            raise ValueError("Ödeme bulunamadı.")
        if eski["durum"] != "aktif":
            raise ValueError("Bu ödeme zaten iptal edilmiş.")
        conn.execute("UPDATE tedarik_odemeler SET durum='iptal', iptal_sebebi=?, "
                     "guncelleme=? WHERE id=?", (sebep.strip(), simdi(), odeme_id))
        audit(conn, "tedarik_odeme_iptal", "tedarik_odemeler", odeme_id,
              {"oncesi": dict(eski), "sebep": sebep.strip()})


# --------------------------------------------------------------------------- #
# Çek & Senet defteri
# --------------------------------------------------------------------------- #
CEK_DURUMLERI = {
    "portfoy": "Portföyde",
    "tahsil": "Tahsil Edildi",
    "karsi_hamle": "Karşı Tarafa Hamle",
    "karsiliksiz": "Karşılıksız",
}


def cekler(tur: str = "", durum: str = "") -> list[dict]:
    with db() as conn:
        sql = ("SELECT c.*, m.ad AS musteri_ad FROM cekler c "
               "JOIN musteriler m ON m.id=c.musteri_id WHERE 1=1")
        params: list = []
        if tur:
            sql += " AND c.tur=?"
            params.append(tur)
        if durum:
            sql += " AND c.durum=?"
            params.append(durum)
        satirlar = [dict(r) for r in conn.execute(sql + " ORDER BY c.vade ASC, c.id DESC", params)]
        for c in satirlar:
            if c["tarih"]:
                try:
                    c["gun_kaldi"] = (date.fromisoformat(c["vade"]) - date.today()).days
                except ValueError:
                    c["gun_kaldi"] = None
            else:
                c["gun_kaldi"] = None
        return satirlar


def cek_ekle(tur: str, musteri_id: int, banka: str, belge_no: str, tutar: float,
             tarih: str, vade: str, notlar: str = "") -> int:
    if tur not in ("cek", "senet"):
        raise ValueError("Tür çek veya senet olmalı.")
    tutar = float(tutar)
    if tutar <= 0:
        raise ValueError("Tutar sıfırdan büyük olmalı.")
    if not vade:
        raise ValueError("Vade tarihi zorunlu.")
    with db() as conn:
        if not conn.execute("SELECT 1 FROM musteriler WHERE id=?", (musteri_id,)).fetchone():
            raise ValueError("Müşteri bulunamadı.")
        cur = conn.execute(
            "INSERT INTO cekler(tur, musteri_id, banka, belge_no, tutar, tarih, vade, "
            "notlar, kayit_zamani) VALUES (?,?,?,?,?,?,?,?,?)",
            (tur, musteri_id, banka.strip(), belge_no.strip(), tutar,
             tarih or bugun(), vade, notlar.strip(), simdi()),
        )
        audit(conn, "cek_ekle", "cekler", cur.lastrowid,
              {"tur": tur, "musteri_id": musteri_id, "tutar": tutar, "vade": vade})
        return cur.lastrowid


def cek_durum(cek_id: int, yeni: str) -> None:
    """Durum değişimi. 'tahsil' durumunda müşteriye otomatik tahsilat kaydı oluşur;
    tekrar geri alınırsa o tahsilat otomatik iptal edilir (veri kaybı yok)."""
    if yeni not in CEK_DURUMLERI:
        raise ValueError("Geçersiz durum.")
    with db() as conn:
        cek = conn.execute("SELECT * FROM cekler WHERE id=?", (cek_id,)).fetchone()
        if not cek:
            raise ValueError("Kayıt bulunamadı.")
        if cek["durum"] == yeni:
            return
        if yeni == "tahsil":
            if cek["odeme_id"]:
                # Daha önce oluşturulmuşsa tekrar oluşturma
                var = conn.execute("SELECT durum FROM odemeler WHERE id=?",
                                   (cek["odeme_id"],)).fetchone()
                if var and var["durum"] == "aktif":
                    raise ValueError("Bu çek için tahsilat zaten kaydedilmiş.")
                yeni_odeme_id = 0
            else:
                yeni_odeme_id = _cek_tahsilat_olustur(conn, dict(cek))
            conn.execute("UPDATE cekler SET durum='tahsil', odeme_id=?, guncelleme=? "
                         "WHERE id=?", (yeni_odeme_id, simdi(), cek_id))
            audit(conn, "cek_tahsil", "cekler", cek_id,
                  {"tur": cek["tur"], "tutar": cek["tutar"], "odeme_id": yeni_odeme_id})
        else:
            if cek["odeme_id"]:
                # Tahsilat otomatik iptal edilir
                conn.execute("UPDATE odemeler SET durum='iptal', "
                             "iptal_sebebi='Çek/senet durumu değişti — otomatik iptal', "
                             "guncelleme=? WHERE id=? AND durum='aktif'",
                             (simdi(), cek["odeme_id"]))
                audit(conn, "cek_tahsilat_iptal", "odemeler", cek["odeme_id"],
                      {"cek_id": cek_id, "tur": cek["tur"]})
            conn.execute("UPDATE cekler SET durum=?, odeme_id=CASE WHEN ?='portfoy' "
                         "THEN 0 ELSE odeme_id END, guncelleme=? WHERE id=?",
                         (yeni, yeni, simdi(), cek_id))
            audit(conn, "cek_durum", "cekler", cek_id,
                  {"onceki": cek["durum"], "yeni": yeni, "tur": cek["tur"]})


def _cek_tahsilat_olustur(conn, cek: dict) -> int:
    """Çek tahsil edildiğinde otomatik TL tahsilat satırı oluşturur."""
    sdet = conn.execute(
        "INSERT INTO odemeler(musteri_id, tarih, para_birimi, tutar, hedef, uygulanan, "
        "kur, yontem, aciklama, kayit_zamani) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (cek["musteri_id"], cek["vade"], "tl", cek["tutar"], "tl", cek["tutar"],
         0, "cek" if cek["tur"] == "cek" else "senet",
         ("%s %s tahsil edildi" % (("Çek" if cek["tur"] == "cek" else "Senet"),
                                   (cek["belge_no"] or ""))).strip(), simdi(),
    ))
    audit(conn, "odeme_ekle", "odemeler", sdet.lastrowid,
          {"kaynak": "cek", "musteri_id": cek["musteri_id"], "tutar": cek["tutar"]})
    return sdet.lastrowid


def cek_portfoy_ozeti() -> dict:
    with db() as conn:
        satirlar = conn.execute(
            "SELECT tur, COUNT(*) AS adet, COALESCE(SUM(tutar),0) AS toplam "
            "FROM cekler WHERE durum='portfoy' GROUP BY tur").fetchall()
        d = {r["tur"]: dict(r) for r in satirlar}
        return {
            "cek_adet": d.get("cek", {}).get("adet", 0),
            "cek_toplam": round(d.get("cek", {}).get("toplam", 0.0), 2),
            "senet_adet": d.get("senet", {}).get("adet", 0),
            "senet_toplam": round(d.get("senet", {}).get("toplam", 0.0), 2),
        }


# --------------------------------------------------------------------------- #
# Kasa defteri (otomatik: TL tahsilatlar, peşin satışlar + manuel gelir/gider)
# --------------------------------------------------------------------------- #
def kasa_rapor(bas: str, bit: str) -> dict:
    """Seçilen aralıkta kasa hareketleri: giren/çıkan + yürüyen bakiye.

    Kaynaklar: manuel kasa kayıtları, TL tahsilatlar (otomatik), peşin TL satışlar
    (otomatik). Altın tahsilatlar birim tutarlılığı için kasaya eklenmez.
    """
    with db() as conn:
        satirlar: list[dict] = []

        for o in conn.execute(
            "SELECT o.*, m.ad AS musteri_ad FROM odemeler o JOIN musteriler m "
            "ON m.id=o.musteri_id WHERE o.durum='aktif' AND o.para_birimi='tl' "
            "AND o.tarih>=? AND o.tarih<=?", (bas, bit)):
            satirlar.append({
                "kaynak": "tahsilat", "id": o["id"], "tarih": o["tarih"],
                "tur": "gelir", "kategori": "Tahsilat",
                "aciklama": "%s — %s" % (o["musteri_ad"],
                                         (o["aciklama"] or "veresiye tahsilatı")),
                "tutar": float(o["tutar"]), "zaman": o["kayit_zamani"],
            })

        for s in conn.execute(
            "SELECT s.*, m.ad AS musteri_ad, u.ad AS urun_ad FROM satislar s "
            "JOIN musteriler m ON m.id=s.musteri_id LEFT JOIN urunler u ON u.id=s.urun_id "
            "WHERE s.durum='aktif' AND s.sekl='pesin' AND s.para_birimi='tl' "
            "AND s.tarih>=? AND s.tarih<=?", (bas, bit)):
            aciklama = (s["urun_ad"] and "%s — %s" % (s["musteri_ad"], s["urun_ad"])
                        or "%s — %s" % (s["musteri_ad"],
                                        (s["aciklama"] or "peşin satış")))
            satirlar.append({
                "kaynak": "pesin", "id": s["id"], "tarih": s["tarih"],
                "tur": "gelir", "kategori": "Peşin Satış",
                "aciklama": aciklama, "tutar": float(s["tutar"]),
                "zaman": s["kayit_zamani"],
            })

        for k in conn.execute(
            "SELECT * FROM kasa WHERE durum='aktif' AND tarih>=? AND tarih<=?",
            (bas, bit)):
            satirlar.append({
                "kaynak": "manuel", "id": k["id"], "tarih": k["tarih"],
                "tur": k["tur"], "kategori": k["kategori"],
                "aciklama": k["aciklama"], "tutar": float(k["tutar"]),
                "zaman": k["kayit_zamani"],
            })

        manuel_iptaller = [dict(r) for r in conn.execute(
            "SELECT * FROM kasa WHERE durum='iptal' ORDER BY tarih DESC LIMIT 20")]

        satirlar.sort(key=lambda r: (r["tarih"], r["zaman"], r["kaynak"], r["id"]))

        bakiye = float(conn.execute(
            "SELECT COALESCE((SELECT COALESCE(SUM(tutar),0) FROM odemeler "
            "WHERE durum='aktif' AND para_birimi='tl' AND tarih<?),0) "
            "+ COALESCE((SELECT COALESCE(SUM(tutar),0) FROM satislar "
            "WHERE durum='aktif' AND sekl='pesin' AND para_birimi='tl' AND tarih<?),0) "
            "+ COALESCE((SELECT COALESCE(SUM(CASE WHEN tur='gelir' THEN tutar "
            "ELSE -tutar END),0) FROM kasa WHERE durum='aktif' AND tarih<?),0)",
            (bas, bas, bas)).fetchone()[0])

        for r in satirlar:
            bakiye += r["tutar"] if r["tur"] == "gelir" else -r["tutar"]
            r["bakiye"] = round(bakiye, 2)

        giren = sum(r["tutar"] for r in satirlar if r["tur"] == "gelir")
        cikan = sum(r["tutar"] for r in satirlar if r["tur"] == "gider")
        return {
            "satirlar": satirlar,
            "giren": round(giren, 2),
            "cikan": round(cikan, 2),
            "net": round(giren - cikan, 2),
            "bakiye": round(bakiye, 2),
            "iptaller": manuel_iptaller,
        }


def kasa_ozet_tarih(bas: str, bit: str) -> float:
    """Sadece aralığın net TL tutarı (panel için hızlı)."""
    return kasa_rapor(bas, bit)["net"]


def kasa_ekle(tarih: str, tur: str, tutar: float, kategori: str = "",
              aciklama: str = "") -> int:
    if tur not in ("gelir", "gider"):
        raise ValueError("Tür gelir veya gider olmalı.")
    tutar = float(tutar)
    if tutar <= 0:
        raise ValueError("Tutar sıfırdan büyük olmalı.")
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO kasa(tarih, tur, kategori, tutar, aciklama, kayit_zamani) "
            "VALUES (?,?,?,?,?,?)",
            (tarih, tur, kategori.strip(), tutar, (aciklama or "").strip(), simdi()),
        )
        audit(conn, "kasa_ekle", "kasa", cur.lastrowid,
              {"tarih": tarih, "tur": tur, "tutar": tutar})
        return cur.lastrowid


def kasa_iptal(kasa_id: int, sebep: str) -> None:
    if not (sebep or "").strip():
        raise ValueError("İptal için sebep girmelisiniz.")
    with db() as conn:
        eski = conn.execute("SELECT * FROM kasa WHERE id=?", (kasa_id,)).fetchone()
        if not eski:
            raise ValueError("Kasa kaydı bulunamadı.")
        if eski["durum"] != "aktif":
            raise ValueError("Bu kayıt zaten iptal edilmiş.")
        conn.execute("UPDATE kasa SET durum='iptal', iptal_sebebi=?, guncelleme=? "
                     "WHERE id=?", (sebep.strip(), simdi(), kasa_id))
        audit(conn, "kasa_iptal", "kasa", kasa_id,
              {"oncesi": dict(eski), "sebep": sebep.strip()})
