"""Flask rotaları: panel, müşteriler, veresiye, tahsilat, rapor, yedek, ayarlar."""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import secrets
import time
from datetime import date, datetime, timedelta

from flask import (Blueprint, abort, current_app, flash, redirect, render_template,
                   request, send_file, session, url_for)

from . import backup as backup_mod
from . import db as dbmod
from . import services as sv

bp = Blueprint("views", __name__)


# --------------------------------------------------------------------------- #
# Yordamlar
# --------------------------------------------------------------------------- #
def _yedek_yoneticisi() -> backup_mod.YedekYoneticisi:
    return current_app.extensions["yedek"]


def _lan_ip() -> str:
    s = __import__("socket").socket(__import__("socket").AF_INET,
                                     __import__("socket").SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def sayi_cevir(metin) -> float:
    """'1.234,56' / '1234.56' / '2,5' biçimlerini sayıya çevirir."""
    m = (str(metin or "")).strip().replace(" ", "").replace("₺", "")
    m = m.replace("gr", "").replace("TL", "").replace("tl", "")
    if not m:
        raise ValueError("Tutar alanı boş olamaz.")
    if "," in m and "." in m:
        if m.rfind(",") > m.rfind("."):
            m = m.replace(".", "").replace(",", ".")
        else:
            m = m.replace(",", "")
    elif "," in m:
        m = m.replace(",", ".")
    try:
        return float(m)
    except ValueError:
        raise ValueError(f"'{metin}' geçerli bir sayı değil.")


def tl_kisa(v: float) -> str:
    """Kısa Türkçe TL biçimi: 4250 → 4.250,00 ₺"""
    s = f"{abs(float(v)):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} ₺"


def _guvenli_yol(hedef: str) -> bool:
    """Yalnızca uygulama içi göreli yollara (açık yönlendirmeye karşı) izin verir."""
    return hedef.startswith("/") and not hedef.startswith(("//", "/\\"))


def _geri_nereye() -> str:
    """Formdaki `geri` alanına güvenli şekilde dön."""
    hedef = request.form.get("geri", "")
    if _guvenli_yol(hedef):
        return hedef
    return request.referrer or url_for("views.panel")


# --------------------------------------------------------------------------- #
# Şablon yordamları / filtreler
# --------------------------------------------------------------------------- #
@bp.app_template_filter("tl")
def filtre_tl(deger) -> str:
    try:
        v = float(deger or 0)
    except (TypeError, ValueError):
        v = 0.0
    on = "-" if v < -0.004 else ""
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{on}{s} ₺"


@bp.app_template_filter("gr")
def filtre_gr(deger) -> str:
    try:
        v = float(deger or 0)
    except (TypeError, ValueError):
        v = 0.0
    on = "-" if v < -0.0005 else ""
    s = f"{abs(v):,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{on}{s} gr"


@bp.app_template_filter("tarih")
def filtre_tarih(deger: str) -> str:
    if not deger:
        return "—"
    try:
        return datetime.fromisoformat(str(deger)[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return str(deger)


@bp.app_template_filter("saat")
def filtre_saat(deger: str) -> str:
    if not deger:
        return "—"
    try:
        d = datetime.fromisoformat(str(deger))
        return d.strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return str(deger)


@bp.app_template_filter("boyut")
def filtre_boyut(bayt) -> str:
    try:
        b = float(bayt or 0)
    except (TypeError, ValueError):
        b = 0.0
    if b >= 1024 * 1024:
        return f"{b / (1024 * 1024):.1f} MB"
    if b >= 1024:
        return f"{b / 1024:.1f} KB"
    return f"{int(b)} B"


@bp.app_context_processor
def _baglam():
    yy = _yedek_yoneticisi()
    durum = {}
    try:
        durum = yy.son_durum()
    except Exception:
        pass
    return {
        "lan_ip": _lan_ip(),
        "port": current_app.config.get("PORT", 8765),
        "yedek_durum": durum,
        "yedek_uyari": _yedek_uyari(),
        "dukkan": _ayar("dukkan_adi", "Hacılar Kuyumculuk"),
        "gram_simdi": sv.fiyat_getir(),
        "bugun_tarih": date.today().isoformat(),
        "pin_var": bool(_ayar("pin_hash", "")),
    }


def _yedek_uyari() -> str:
    mesajlar = []
    saglik = current_app.extensions.get("db_sagligi", "ok")
    if saglik != "ok":
        mesajlar.append(f"Veritabanı bütünlük kontrolü başarısız ({saglik}). "
                        "Lütfen bir yedeği geri yükleyin veya destek alın.")
    try:
        u = _yedek_yoneticisi().uyari()
    except Exception as e:
        u = f"Yedek durumu okunamadı: {e}"
    if u:
        mesajlar.append(u)
    return " · ".join(mesajlar)


def _ayar(anahtar: str, varsayilan: str = "") -> str:
    conn = dbmod.baglanti()
    try:
        return sv.ayar_oku(conn, anahtar, varsayilan)
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Güvenlik (PIN kilidi — isteğe bağlı)
# --------------------------------------------------------------------------- #
def _pin_kontrol(pin: str) -> bool:
    tuz = _ayar("pin_tuz", "")
    k = _ayar("pin_hash", "")
    if not k:
        return True
    if not tuz:
        return False
    return hmac.compare_digest(hashlib.sha256((tuz + pin).encode("utf-8")).hexdigest(), k)


_GIRIS_DENEMELERI: dict[str, list[float]] = {}
GIRIS_HAK = 5
GIRIS_KILIT_SANIYE = 300


def _giris_kilitli() -> bool:
    ip = request.remote_addr or ""
    simdi = time.time()
    denemeler = [t for t in _GIRIS_DENEMELERI.get(ip, []) if simdi - t < GIRIS_KILIT_SANIYE]
    _GIRIS_DENEMELERI[ip] = denemeler
    return len(denemeler) >= GIRIS_HAK


@bp.before_request
def _koruma():
    if request.endpoint in ("static",):
        return None
    if request.endpoint in ("views.giris",):
        return None
    if session.get("giris"):
        return None
    # PIN hiç ayarlanmadıysa giriş serbest
    if not _ayar("pin_hash", ""):
        session["giris"] = True
        return None
    return redirect(url_for("views.giris", lutfen=request.path))


@bp.route("/giris", methods=["GET", "POST"])
def giris():
    if request.method == "POST":
        if _giris_kilitli():
            flash(f"Çok fazla hatalı deneme. {GIRIS_KILIT_SANIYE // 60} dakika sonra tekrar deneyin.",
                  "hata")
            return render_template("giris.html", default_pin=True), 429
        pin = request.form.get("pin", "")
        if _pin_kontrol(pin):
            _GIRIS_DENEMELERI.pop(request.remote_addr or "", None)
            session.permanent = bool(request.form.get("hatirla"))
            session["giris"] = True
            hedef = request.args.get("lutfen") or url_for("views.panel")
            if not _guvenli_yol(hedef):
                hedef = url_for("views.panel")
            flash("Hoş geldiniz.", "basari")
            return redirect(hedef)
        _GIRIS_DENEMELERI.setdefault(request.remote_addr or "", []).append(time.time())
        flash("PIN hatalı. Tekrar deneyin.", "hata")
    if session.get("giris") or not _ayar("pin_hash", ""):
        return redirect(url_for("views.panel"))
    return render_template("giris.html", default_pin=True)


@bp.route("/cikis", methods=["POST"])
def cikis():
    session.clear()
    flash("Oturum kapatıldı.", "bilgi")
    return redirect(url_for("views.giris"))


# --------------------------------------------------------------------------- #
# Panel
# --------------------------------------------------------------------------- #
@bp.route("/")
def panel():
    veri = sv.panel()
    return render_template("panel.html", v=veri, sayfa="panel")


# --------------------------------------------------------------------------- #
# Müşteriler
# --------------------------------------------------------------------------- #
@bp.route("/musteriler")
def musteriler_sayfasi():
    q = request.args.get("q", "").strip()
    borclu = request.args.get("borclu") == "1"
    durum = request.args.get("durum", "aktif")
    if durum not in ("aktif", "arsiv"):
        durum = "aktif"
    liste = sv.musteriler(q=q, durum=durum, sadece_borclu=borclu)
    return render_template("musteriler.html", musteriler=liste, q=q,
                           borclu=borclu, durum=durum, sayfa="musteriler")


@bp.route("/musteriler/ekle", methods=["POST"])
def musteri_ekle():
    try:
        ad = request.form.get("ad", "")
        telefon = request.form.get("telefon", "")
        adres = request.form.get("adres", "")
        notlar = request.form.get("notlar", "")
        limit = sayi_cevir(request.form.get("limit", "0") or 0)
        kategori = request.form.get("kategori", "")
        yeni = sv.musteri_ekle(ad, telefon, adres, notlar, limit, kategori)
        flash(f"'{ad}' kaydedildi.", "basari")
        if request.form.get("detay") == "1":
            return redirect(url_for("views.musteri_detay", mid=yeni))
    except ValueError as e:
        flash(str(e), "hata")
    return redirect(_geri_nereye())


@bp.route("/musteriler/<int:mid>")
def musteri_detay(mid):
    try:
        veri = sv.ekstre(mid)
    except ValueError as e:
        flash(str(e), "hata")
        return redirect(url_for("views.musteriler_sayfasi"))
    m = sv.musteri_getir(mid)
    if not m:
        flash("Müşteri bulunamadı.", "hata")
        return redirect(url_for("views.musteriler_sayfasi"))
    return render_template("musteri_detay.html", m=m, e=veri, sayfa="musteriler")


@bp.route("/musteriler/<int:mid>/duzenle", methods=["POST"])
def musteri_duzenle(mid):
    try:
        sv.musteri_guncelle(
            mid,
            request.form.get("ad", ""),
            request.form.get("telefon", ""),
            request.form.get("adres", ""),
            request.form.get("notlar", ""),
            sayi_cevir(request.form.get("limit", "0") or 0),
            request.form.get("kategori", ""),
            request.form.get("sozu_tarih", ""),
            request.form.get("sozu_not", ""),
        )
        flash("Müşteri bilgileri güncellendi.", "basari")
    except ValueError as e:
        flash(str(e), "hata")
    return redirect(_geri_nereye())


@bp.route("/musteriler/<int:mid>/durum", methods=["POST"])
def musteri_durum(mid):
    yeni = request.form.get("durum", "arsiv")
    try:
        sv.musteri_durum(mid, yeni)
        flash("Müşteri arşivlendi. Kayıt silinmedi, geçmişte duruyor." if yeni == "arsiv"
              else "Müşteri listeye geri alındı.", "basari")
    except ValueError as e:
        flash(str(e), "hata")
    return redirect(_geri_nereye())


# --------------------------------------------------------------------------- #
# Veresiye satışları
# --------------------------------------------------------------------------- #
@bp.route("/satislar")
def satislar_sayfasi():
    musteriler = sv.musteriler(durum="aktif")
    return render_template(
        "satislar.html",
        satislar=sv.satislar(
            baslangic=request.args.get("baslangic", ""),
            bitis=request.args.get("bitis", ""),
            para_birimi=request.args.get("pb", ""),
            durum=request.args.get("durum", "aktif"),
            sekl=request.args.get("sekl", ""),
        ),
        urunler=sv.urunler(),
        musteriler=musteriler,
        filtreler={
            "baslangic": request.args.get("baslangic", ""),
            "bitis": request.args.get("bitis", ""),
            "pb": request.args.get("pb", ""),
            "durum": request.args.get("durum", "aktif"),
            "sekl": request.args.get("sekl", ""),
        },
        sayfa="satislar",
    )


@bp.route("/satislar/ekle", methods=["POST"])
def satis_ekle():
    try:
        mid = int(request.form.get("musteri_id", 0) or 0)
        tutar = sayi_cevir(request.form.get("tutar", ""))
        sv.satis_ekle(
            musteri_id=mid,
            tarih=request.form.get("tarih") or date.today().isoformat(),
            para_birimi=request.form.get("pb", "tl"),
            tutar=tutar,
            vade=request.form.get("vade", ""),
            aciklama=request.form.get("aciklama", ""),
            sekl=request.form.get("sekl", "veresiye"),
            urun_id=int(request.form.get("urun_id", 0) or 0),
        )
        m = sv.musteri_getir(mid)
        if request.form.get("sekl", "veresiye") == "pesin":
            flash("Peşin satış kaydedildi (kasa defterine otomatik eklendi).", "basari")
        elif m and m["limit_tl"] > 0 and m["tl_borc"] > m["limit_tl"]:
            flash(f"Kaydedildi — DİKKAT: TL bakiyesi ({m['limit_tl']:.0f} ₺) "
                  f"limitin üzerinde: {m['tl_borc']:.2f} ₺", "uyari")
        else:
            flash("Veresiye satışı kaydedildi.", "basari")
    except (ValueError, KeyError) as e:
        flash(str(e), "hata")
    return redirect(_geri_nereye())


@bp.route("/satislar/<int:sid>/iptal", methods=["POST"])
def satis_iptal(sid):
    try:
        sv.satis_iptal(sid, request.form.get("sebep", ""))
        flash("Satış iptal edildi. Kayıt silinmedi, işlem geçmişinde duruyor.", "basari")
    except ValueError as e:
        flash(str(e), "hata")
    return redirect(_geri_nereye())


# --------------------------------------------------------------------------- #
# Tahsilatlar
# --------------------------------------------------------------------------- #
@bp.route("/tahsilatlar")
def tahsilatlar_sayfasi():
    musteriler = sv.musteriler(durum="aktif")
    return render_template(
        "tahsilatlar.html",
        odemeler=sv.odemeler(
            baslangic=request.args.get("baslangic", ""),
            bitis=request.args.get("bitis", ""),
            durum=request.args.get("durum", "aktif"),
        ),
        musteriler=musteriler,
        filtreler={
            "baslangic": request.args.get("baslangic", ""),
            "bitis": request.args.get("bitis", ""),
            "durum": request.args.get("durum", "aktif"),
        },
        sayfa="tahsilatlar",
    )


@bp.route("/tahsilatlar/ekle", methods=["POST"])
def odeme_ekle():
    try:
        mid = int(request.form.get("musteri_id", 0) or 0)
        tutar = sayi_cevir(request.form.get("tutar", ""))
        pb = request.form.get("pb", "tl")
        hedef = request.form.get("hedef", pb)
        kur = request.form.get("kur", "")
        sv.odeme_ekle(
            musteri_id=mid,
            tarih=request.form.get("tarih") or date.today().isoformat(),
            para_birimi=pb,
            tutar=tutar,
            hedef=hedef,
            yontem=request.form.get("yontem", "nakit"),
            aciklama=request.form.get("aciklama", ""),
            kur=sayi_cevir(kur) if kur.strip() else None,
        )
        m = sv.musteri_getir(mid)
        if m and not m["borclu"]:
            flash("Tahsilat kaydedildi — müşterinin borcu kapandı. ✓", "basari")
        elif m and (m["tl_borc"] < -0.004 or m["altin_borc"] < -0.0005):
            flash("Tahsilat kaydedildi — DİKKAT: müşteride AVANS (fazla ödeme) var.", "uyari")
        else:
            flash("Tahsilat kaydedildi.", "basari")
    except (ValueError, KeyError) as e:
        flash(str(e), "hata")
    return redirect(_geri_nereye())


@bp.route("/tahsilatlar/<int:oid>/iptal", methods=["POST"])
def odeme_iptal(oid):
    try:
        sv.odeme_iptal(oid, request.form.get("sebep", ""))
        flash("Tahsilat iptal edildi. Kayıt silinmedi, işlem geçmişinde duruyor.", "basari")
    except ValueError as e:
        flash(str(e), "hata")
    return redirect(_geri_nereye())


# --------------------------------------------------------------------------- #
# Ekstre (yazdırma)
# --------------------------------------------------------------------------- #
@bp.route("/ekstre/<int:mid>")
def ekstre(mid):
    try:
        veri = sv.ekstre(mid)
    except ValueError as e:
        flash(str(e), "hata")
        return redirect(url_for("views.musteriler_sayfasi"))
    return render_template("ekstre.html", e=veri, sayfa="musteriler")


# --------------------------------------------------------------------------- #
# Raporlar
# --------------------------------------------------------------------------- #
@bp.route("/raporlar")
def raporlar():
    return render_template(
        "raporlar.html",
        aylar=sv.rapor_aylik(6),
        borclular=sv.en_borclular(15),
        gram=sv.fiyat_getir(),
        sayfa="raporlar",
    )


@bp.route("/raporlar/csv")
def rapor_csv():
    hangi = request.args.get("hangi", "musteriler")
    bas = request.args.get("baslangic", "")
    bit = request.args.get("bitis", "")
    if hangi == "satislar":
        icerik, ad = sv.csv_satislar(bas, bit), f"veresiye-satislar_{bugun_iso()}.csv"
    elif hangi == "tahsilatlar":
        icerik, ad = sv.csv_odemeler(bas, bit), f"veresiye-tahsilatlar_{bugun_iso()}.csv"
    else:
        icerik, ad = sv.csv_musteriler(), f"veresiye-musteriler_{bugun_iso()}.csv"
    return send_file(io.BytesIO(icerik.encode("utf-8")),
                     mimetype="text/csv; charset=utf-8",
                     as_attachment=True, download_name=ad)


def bugun_iso() -> str:
    return date.today().strftime("%Y%m%d")


# --------------------------------------------------------------------------- #
# Yedek & güvenlik
# --------------------------------------------------------------------------- #
@bp.route("/yedek")
def yedek_sayfasi():
    yy = _yedek_yoneticisi()
    return render_template(
        "yedek.html",
        dosyalar=yy.liste()[:80],
        son=yy.son_durum(),
        sayfa="yedek",
    )


@bp.route("/yedek/manuel", methods=["POST"])
def yedek_manuel():
    try:
        sonuc = _yedek_yoneticisi().yedekle("manuel")
        flash(f"Yedek alındı: {os.path.basename(sonuc['dosya'])} "
              f"({sonuc['boyut'] // 1024} KB)", "basari")
    except Exception as e:
        flash(f"Yedekleme hatası: {e}", "hata")
    return redirect(url_for("views.yedek_sayfasi"))


def _yedek_dosyasi_bul() -> str | None:
    """`tur` + `ad` parametrelerinden yedek dosya yolunu bulur (klasör dışına çıkış engelli)."""
    tur = request.args.get("tur") or request.form.get("tur", "")
    ad = request.args.get("ad") or request.form.get("ad", "")
    if not tur or not ad or "/" in ad or "\\" in ad or ".." in ad:
        return None
    kok = os.path.realpath(_yedek_yoneticisi().yedek_koku)
    yol = os.path.realpath(os.path.join(kok, tur, ad))
    if not yol.startswith(kok + os.sep) or not os.path.isfile(yol):
        return None
    return yol


@bp.route("/yedek/indir")
def yedek_indir():
    yol = _yedek_dosyasi_bul()
    if not yol:
        abort(404)
    return send_file(yol, as_attachment=True, download_name=os.path.basename(yol))


@bp.route("/yedek/geri-yukle", methods=["POST"])
def yedek_geri_yukle():
    yol = _yedek_dosyasi_bul()
    if not yol:
        flash("Geçersiz yedek dosyası.", "hata")
        return redirect(url_for("views.yedek_sayfasi"))
    yy = _yedek_yoneticisi()
    try:
        yy.geri_yukle(yol)
        flash("Geri yükleme tamamlandı. Mevcut veriler önce 'on-yukleme' "
              "yedeğine kopyalandığı için hiçbir şey kaybolmadı.", "basari")
    except Exception as e:
        flash(f"Geri yükleme hatası: {e}", "hata")
    return redirect(url_for("views.yedek_sayfasi"))


@bp.route("/yedek/json")
def yedek_json():
    veri = sv.tam_disa_aktarim()
    icerik = json.dumps(veri, ensure_ascii=False, indent=1)
    return send_file(io.BytesIO(icerik.encode("utf-8")),
                     mimetype="application/json; charset=utf-8",
                     as_attachment=True,
                     download_name=f"veresiye-tam-yedek_{bugun_iso()}.json")


# --------------------------------------------------------------------------- #
# Ayarlar
# --------------------------------------------------------------------------- #
@bp.route("/ayarlar", methods=["GET"])
def ayarlar():
    return render_template("ayarlar.html", sayfa="ayarlar",
                           fiyatlar=sv.fiyat_gecmisi(30),
                           ikinci_yedek=_ayar("ikinci_yedek_klasor", ""))


@bp.route("/ayarlar", methods=["POST"])
def ayarlar_kaydet():
    mesaj_var = False
    try:
        with sv.db() as conn:
            dukkan = request.form.get("dukkan_adi", "").strip()
            if dukkan:
                sv.ayar_yaz(conn, "dukkan_adi", dukkan)
            vade = request.form.get("vade_gun", "").strip()
            if vade:
                sv.ayar_yaz(conn, "vade_gun", str(max(0, int(vade))))

            ikinci = request.form.get("ikinci_yedek_klasor")
            if ikinci is not None:
                ikinci = ikinci.strip()
                if ikinci:
                    ikinci = os.path.abspath(ikinci)
                    try:
                        os.makedirs(ikinci, exist_ok=True)
                    except OSError as e:
                        raise ValueError(f"İkinci yedek klasörü oluşturulamadı: {e}")
                sv.ayar_yaz(conn, "ikinci_yedek_klasor", ikinci)
                flash("İkinci yedek klasörü kaydedildi." if ikinci else
                      "İkinci yedek klasörü kaldırıldı.", "basari")
                mesaj_var = True

            # PIN
            yeni_pin = request.form.get("yeni_pin", "").strip()
            kaldir = request.form.get("pin_kaldir")
            mevcut_pin = request.form.get("mevcut_pin", "")
            if kaldir:
                if not _pin_kontrol(mevcut_pin):
                    raise ValueError("PIN kaldırmak için mevcut PIN'i girin.")
                sv.ayar_yaz(conn, "pin_hash", "")
                sv.ayar_yaz(conn, "pin_tuz", "")
                flash("PIN kilidi kaldırıldı.", "basari")
                mesaj_var = True
            elif yeni_pin:
                if len(yeni_pin) < 4:
                    raise ValueError("PIN en az 4 haneli olmalı.")
                eski_hash = sv.ayar_oku(conn, "pin_hash", "")
                if eski_hash and not _pin_kontrol(mevcut_pin):
                    raise ValueError("Mevcut PIN hatalı.")
                tuz = secrets.token_hex(16)
                sv.ayar_yaz(conn, "pin_tuz", tuz)
                sv.ayar_yaz(conn, "pin_hash",
                            hashlib.sha256((tuz + yeni_pin).encode("utf-8")).hexdigest())
                flash("PIN güncellendi. Tablet girişinde bu PIN'i kullanın.", "basari")
                mesaj_var = True

        # Gram fiyatı
        fiyat = request.form.get("gram_fiyat", "").strip()
        if fiyat:
            v = sayi_cevir(fiyat)
            if v <= 0:
                raise ValueError("Gram fiyat sıfırdan büyük olmalı.")
            sv.fiyat_kaydet(date.today().isoformat(), v)
            flash(f"Bugünkü gram fiyat: {tl_kisa(v)}/gr", "basari")
            mesaj_var = True
        if not mesaj_var:
            flash("Ayarlar kaydedildi.", "basari")
    except ValueError as e:
        flash(str(e), "hata")
    except Exception as e:
        flash(f"Hata: {e}", "hata")
    return redirect(url_for("views.ayarlar"))


@bp.route("/fiyat", methods=["POST"])
def fiyat_hizli():
    try:
        v = sayi_cevir(request.form.get("gram_fiyat", ""))
        if v <= 0:
            raise ValueError("Geçersiz fiyat.")
        sv.fiyat_kaydet(request.form.get("tarih") or date.today().isoformat(), v)
        flash(f"Gram fiyat güncellendi: {v:,.2f} ₺", "basari")
    except ValueError as e:
        flash(str(e), "hata")
    return redirect(_geri_nereye())


# --------------------------------------------------------------------------- #
# İşlem geçmişi
# --------------------------------------------------------------------------- #
@bp.route("/islem-gecmisi")
def islem_gecmisi():
    return render_template("islem_gecmisi.html", hareketler=sv.hareket_gecmisi(300),
                           sayfa="gecmis")


# --------------------------------------------------------------------------- #
# Ürünler (katalog + birim fiyat)
# --------------------------------------------------------------------------- #
@bp.route("/urunler")
def urunler_sayfasi():
    return render_template("urunler.html", sayfa="urunler",
                           urunler=sv.urunler(),
                           arsiv=sv.urunler(durum="arsiv"))


@bp.route("/urunler/ekle", methods=["POST"])
def urun_ekle():
    try:
        sv.urun_ekle(
            request.form.get("ad", ""),
            request.form.get("birim", "adet") or "adet",
            sayi_cevir(request.form.get("tl_fiyat", "0") or 0),
            sayi_cevir(request.form.get("gr_miktar", "0") or 0),
            request.form.get("notlar", ""),
        )
        flash("Ürün kataloglara eklendi.", "basari")
    except ValueError as e:
        flash(str(e), "hata")
    return redirect(url_for("views.urunler_sayfasi"))


@bp.route("/urunler/<int:uid>/duzenle", methods=["POST"])
def urun_duzenle(uid):
    try:
        sv.urun_guncelle(
            uid,
            request.form.get("ad", ""),
            request.form.get("birim", "adet") or "adet",
            sayi_cevir(request.form.get("tl_fiyat", "0") or 0),
            sayi_cevir(request.form.get("gr_miktar", "0") or 0),
            request.form.get("notlar", ""),
        )
        flash("Ürün/fiyat güncellendi.", "basari")
    except ValueError as e:
        flash(str(e), "hata")
    return redirect(_geri_nereye())


@bp.route("/urunler/<int:uid>/durum", methods=["POST"])
def urun_durum(uid):
    try:
        yeni = request.form.get("durum", "arsiv")
        sv.urun_durum(uid, yeni)
        flash("Ürün arşivlendi (silinmedi)." if yeni == "arsiv"
              else "Ürün listeye geri alındı.", "basari")
    except ValueError as e:
        flash(str(e), "hata")
    return redirect(_geri_nereye())


# --------------------------------------------------------------------------- #
# Tedarikçiler
# --------------------------------------------------------------------------- #
@bp.route("/tedarikciler")
def tedarikciler_sayfasi():
    return render_template("tedarikciler.html", sayfa="tedarikciler",
                           tedarikciler=sv.tedarikciler(),
                           arsiv=sv.tedarikciler(durum="arsiv"))


@bp.route("/tedarikciler/ekle", methods=["POST"])
def tedarikci_ekle():
    try:
        sv.tedarikci_ekle(request.form.get("ad", ""),
                          request.form.get("telefon", ""),
                          request.form.get("notlar", ""))
        flash("Tedarikçi kaydedildi.", "basari")
    except ValueError as e:
        flash(str(e), "hata")
    return redirect(_geri_nereye())


@bp.route("/tedarikciler/<int:tid>")
def tedarikci_detay(tid):
    try:
        e = sv.tedarik_ekstre(tid)
    except ValueError as err:
        flash(str(err), "hata")
        return redirect(url_for("views.tedarikciler_sayfasi"))
    t = sv.tedarikci_getir(tid)
    if not t:
        flash("Tedarikçi bulunamadı.", "hata")
        return redirect(url_for("views.tedarikciler_sayfasi"))
    return render_template("tedarik_detay.html", m=t, e=e, sayfa="tedarikciler")


@bp.route("/tedarikciler/<int:tid>/duzenle", methods=["POST"])
def tedarikci_duzenle(tid):
    try:
        sv.tedarikci_duzenle(tid, request.form.get("ad", ""),
                             request.form.get("telefon", ""),
                             request.form.get("notlar", ""))
        flash("Tedarikçi güncellendi.", "basari")
    except ValueError as e:
        flash(str(e), "hata")
    return redirect(_geri_nereye())


@bp.route("/tedarikciler/<int:tid>/durum", methods=["POST"])
def tedarikci_durum(tid):
    try:
        yeni = request.form.get("durum", "arsiv")
        sv.tedarikci_durum(tid, yeni)
        flash("Tedarikçi arşivlendi (silinmedi)." if yeni == "arsiv"
              else "Tedarikçi listeye geri alındı.", "basari")
    except ValueError as e:
        flash(str(e), "hata")
    return redirect(_geri_nereye())


@bp.route("/tedarikciler/<int:tid>/alis/ekle", methods=["POST"])
def alis_ekle(tid):
    try:
        sv.alis_ekle(
            tid,
            request.form.get("tarih") or date.today().isoformat(),
            sayi_cevir(request.form.get("tutar", "")),
            request.form.get("aciklama", ""),
        )
        flash("Alış (bizim borcumuz) kaydedildi.", "basari")
    except (ValueError, KeyError) as e:
        flash(str(e), "hata")
    return redirect(_geri_nereye())


@bp.route("/alis/<int:aid>/iptal", methods=["POST"])
def alis_iptal(aid):
    try:
        sv.alis_iptal(aid, request.form.get("sebep", ""))
        flash("Alış iptal edildi (kayıt duruyor).", "basari")
    except ValueError as e:
        flash(str(e), "hata")
    return redirect(_geri_nereye())


@bp.route("/tedarikciler/<int:tid>/odeme/ekle", methods=["POST"])
def tedarik_odeme_ekle(tid):
    try:
        sv.tedarik_odeme_ekle(
            tid,
            request.form.get("tarih") or date.today().isoformat(),
            sayi_cevir(request.form.get("tutar", "")),
            request.form.get("yontem", "nakit"),
            request.form.get("aciklama", ""),
        )
        flash("Tedarikçi ödemesi kaydedildi.", "basari")
    except (ValueError, KeyError) as e:
        flash(str(e), "hata")
    return redirect(_geri_nereye())


@bp.route("/tedarik-odeme/<int:oid>/iptal", methods=["POST"])
def tedarik_odeme_iptal(oid):
    try:
        sv.tedarik_odeme_iptal(oid, request.form.get("sebep", ""))
        flash("Ödeme iptal edildi (kayıt duruyor).", "basari")
    except ValueError as e:
        flash(str(e), "hata")
    return redirect(_geri_nereye())


# --------------------------------------------------------------------------- #
# Çek & Senet defteri
# --------------------------------------------------------------------------- #
@bp.route("/cekler")
def cekler_sayfasi():
    musteriler = sv.musteriler(durum="aktif")
    tur = request.args.get("tur", "")
    durum = request.args.get("durum", "portfoy")
    return render_template(
        "cekler.html",
        kayitlar=sv.cekler(tur=tur, durum=durum),
        musteriler=musteriler,
        ozet=sv.cek_portfoy_ozeti(),
        filtreler={"tur": tur, "durum": durum},
        durumlar=sv.CEK_DURUMLERI,
        sayfa="cekler",
    )


@bp.route("/cekler/ekle", methods=["POST"])
def cek_ekle():
    try:
        mid = int(request.form.get("musteri_id", 0) or 0)
        sv.cek_ekle(
            request.form.get("tur", "cek"),
            mid,
            request.form.get("banka", ""),
            request.form.get("belge_no", ""),
            sayi_cevir(request.form.get("tutar", "")),
            request.form.get("tarih") or date.today().isoformat(),
            request.form.get("vade", ""),
            request.form.get("notlar", ""),
        )
        flash("Çek/senet portföye eklendi.", "basari")
    except (ValueError, KeyError) as e:
        flash(str(e), "hata")
    return redirect(_geri_nereye())


@bp.route("/cekler/<int:cid>/durum", methods=["POST"])
def cek_durum(cid):
    try:
        sv.cek_durum(cid, request.form.get("yeni", ""))
        flash("Çek/senet durumu güncellendi.", "basari")
    except ValueError as e:
        flash(str(e), "hata")
    return redirect(_geri_nereye())


# --------------------------------------------------------------------------- #
# Kasa defteri
# --------------------------------------------------------------------------- #
@bp.route("/kasa")
def kasa_sayfasi():
    bas = request.args.get("baslangic") or (date.today().replace(day=1).isoformat())
    bit = request.args.get("bitis") or date.today().isoformat()
    rapor = sv.kasa_rapor(bas, bit)
    return render_template("kasa.html", r=rapor,
                           filtreler={"baslangic": bas, "bitis": bit},
                           sayfa="kasa")


@bp.route("/kasa/ekle", methods=["POST"])
def kasa_ekle():
    try:
        sv.kasa_ekle(
            request.form.get("tarih") or date.today().isoformat(),
            request.form.get("tur", "gelir"),
            sayi_cevir(request.form.get("tutar", "")),
            request.form.get("kategori", ""),
            request.form.get("aciklama", ""),
        )
        flash("Kasa kaydı eklendi.", "basari")
    except (ValueError, KeyError) as e:
        flash(str(e), "hata")
    return redirect(_geri_nereye())


@bp.route("/kasa/<int:kid>/iptal", methods=["POST"])
def kasa_iptal(kid):
    try:
        sv.kasa_iptal(kid, request.form.get("sebep", ""))
        flash("Kasa kaydı iptal edildi (kayıt duruyor).", "basari")
    except ValueError as e:
        flash(str(e), "hata")
    return redirect(_geri_nereye())
