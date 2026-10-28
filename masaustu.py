"""Kuyumcu Veresiye Premium — Masaüstü (tkinter) arayüz.

Web sürümüyle **aynı veritabanını** (veresiye.db) paylaşır: web'den girilen
kaydı masaüstünde (ve tersi) aynı anda görürsünüz. Aynı güvenlik kuralları:
hiçbir kayıt silinmez; iptal/arşiv olur; tüm işlemler denetim günlüğüne yazılır.

Çalıştırma:  python masaustu.py   (veya masaustu.bat çift tık)
EXE üretimi: pyinstaller kuyumcu_masaustu.spec
"""
from __future__ import annotations

import json
import os
import sys
import tkinter as tk
from datetime import date, datetime
from tkinter import filedialog, messagebox, simpledialog, ttk

# veresiye paketini bul (script proje kökünde ise doğrudan bulur)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from veresiye import backup as vbackup  # noqa: E402
from veresiye import db as vdb          # noqa: E402
from veresiye import services as sv     # noqa: E402

# --------------------------------------------------------------------------- #
# Tema: premium koyu (antrasit) + altın vurgular
# --------------------------------------------------------------------------- #
ARKA = "#14161a"        # pencere zemini
PANEL = "#1c1f24"       # kart zemini
PANEL2 = "#23262d"      # alan zemini
CIZGI = "#2d3138"
ALTIN = "#d4af37"
ALTIN_ACIK = "#f0d77b"
METIN = "#e8e6df"
SOLUK = "#8a8f98"
YESIL = "#34c37a"
KIRMIZI = "#e0566a"
UYARI = "#e0a94a"


def tl(v) -> str:
    return (f"{float(v):,.2f}".replace(",", "X")
            .replace(".", ",").replace("X", ".") + " ₺")


def gr(v) -> str:
    return (f"{float(v):,.4f}".replace(",", "X")
            .replace(".", ",").replace("X", ".") + " gr")


def sayi(s: str) -> float:
    """Türkçe girdi kabulü: '5.000', '5.000,50', '3,25', '8250'."""
    s = (s or "").strip().replace(" ", "").replace("\xa0", "")
    if not s:
        return 0.0
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    return float(s)


def tarih_yaz(iso) -> str:
    """Gün-ay-yıl gösterimi; saatli değerler de desteklenir."""
    izo = str(iso or "")
    try:
        return datetime.strptime(izo[:19], "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M")
    except ValueError:
        pass
    try:
        return datetime.strptime(izo[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return izo


CIZI = "-" * 94


# --------------------------------------------------------------------------- #
# Uygulama
# --------------------------------------------------------------------------- #
class Uygulama:
    def __init__(self, kok: tk.Tk):
        self.kok = kok
        self.yedekci = vbackup.YedekYoneticisi()
        self.secili_musteri: int | None = None
        self._tema_kur()
        self._ust_serit()
        self._sekmeler()
        self.panel_yenile()
        self.yedekci.baslat()
        kok.protocol("WM_DELETE_WINDOW", self.kapat)

    # ---------------------------------------------------------------- tema #
    def _tema_kur(self):
        self.kok.title("Kuyumcu Veresiye Premium — Masaüstü")
        self.kok.geometry("1180x730")
        self.kok.minsize(1000, 640)
        self.kok.configure(bg=ARKA)

        st = ttk.Style(self.kok)
        st.theme_use("clam")
        st.configure(".", background=ARKA, foreground=METIN,
                     fieldbackground=PANEL2, bordercolor=CIZGI,
                     lightcolor=PANEL, darkcolor=PANEL, troughcolor=PANEL2,
                     font=("Segoe UI", 10))
        st.configure("TFrame", background=ARKA)
        st.configure("Panel.TFrame", background=PANEL)
        st.configure("TNotebook", background=ARKA, borderwidth=0, tabmargins=[10, 8, 10, 0])
        st.configure("TNotebook.Tab", background=PANEL, foreground=SOLUK,
                     padding=[18, 9], borderwidth=0)
        st.map("TNotebook.Tab", background=[("selected", PANEL2)],
               foreground=[("selected", ALTIN)])
        st.configure("TLabel", background=ARKA, foreground=METIN)
        st.configure("Panel.TLabel", background=PANEL, foreground=METIN)
        st.configure("Soluk.TLabel", background=ARKA, foreground=SOLUK)
        st.configure("Altin.TLabel", background=ARKA, foreground=ALTIN,
                     font=("Segoe UI", 11, "bold"))
        st.configure("Baslik.TLabel", background=PANEL, foreground=ALTIN_ACIK,
                     font=("Segoe UI Semibold", 15))
        st.configure("KpiDeger.TLabel", background=PANEL, foreground=METIN,
                     font=("Segoe UI", 16, "bold"))
        st.configure("KpiEtiket.TLabel", background=PANEL, foreground=SOLUK,
                     font=("Segoe UI", 9))
        st.configure("TEntry", insertcolor=METIN, fieldbackground=PANEL2)
        st.configure("TSpinbox", fieldbackground=PANEL2, arrowcolor=ALTIN)
        st.configure("TCombobox", fieldbackground=PANEL2, arrowcolor=ALTIN)
        st.configure("TButton", background=PANEL2, foreground=METIN, padding=[14, 7],
                     borderwidth=1, focusthickness=0)
        st.map("TButton", background=[("active", "#2b2f36")],
               foreground=[("disabled", SOLUK)])
        st.configure("Altin.TButton", background="#3a3325", foreground=ALTIN_ACIK,
                     borderwidth=1, padding=[18, 8])
        st.map("Altin.TButton", background=[("active", "#46402b")])
        st.configure("Yesil.TButton", background="#1e352a", foreground=YESIL, padding=[18, 8])
        st.map("Yesil.TButton", background=[("active", "#264434")])
        st.configure("TCheckbutton", background=ARKA, foreground=METIN, focuscolor=ARKA)
        st.map("TCheckbutton", background=[("active", ARKA)])
        st.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                     foreground=METIN, rowheight=27, borderwidth=0)
        st.configure("Treeview.Heading", background=PANEL2, foreground=SOLUK,
                     font=("Segoe UI", 9, "bold"), borderwidth=0, padding=[8, 6])
        st.map("Treeview.Heading", background=[("active", "#2c3038")])
        st.configure("Vertical.TScrollbar", background=PANEL2, troughcolor=ARKA,
                     borderwidth=0, arrowsize=12)

        self.kok.option_add("*Treeview*selectForeground", ALTIN_ACIK)
        self.kok.option_add("*Treeview*selectBackground", "#3a3325")

    # ------------------------------------------------------------ üst şerit #
    def _ust_serit(self):
        ust = ttk.Frame(self.kok, style="Panel.TFrame", padding=(18, 10, 18, 10))
        ust.pack(fill="x")

        sol = ttk.Frame(ust, style="Panel.TFrame")
        sol.pack(side="left")
        ttk.Label(sol, text="◆ Kuyumcu Veresiye Premium", style="Baslik.TLabel").pack(anchor="w")
        self.fiyat_etiketi = ttk.Label(sol, text="", style="Soluk.TLabel", background=PANEL)
        self.fiyat_etiketi.pack(anchor="w")

        sag = ttk.Frame(ust, style="Panel.TFrame")
        sag.pack(side="right")
        ttk.Button(sag, text="Gram Fiyatı Güncelle", style="Altin.TButton",
                   command=self.fiyat_penceresi).pack(side="right", padx=6)

    # ------------------------------------------------------------ sekmeler #
    def _sekmeler(self):
        self.notlar_ck = ttk.Notebook(self.kok)
        self.notlar_ck.pack(fill="both", expand=True, padx=8, pady=(4, 10))

        self.tab_panel = ttk.Frame(self.notlar_ck, padding=10)
        self.tab_musteriler = ttk.Frame(self.notlar_ck, padding=10)
        self.tab_urunler = ttk.Frame(self.notlar_ck, padding=10)
        self.tab_gecmis = ttk.Frame(self.notlar_ck, padding=10)
        self.tab_yedek = ttk.Frame(self.notlar_ck, padding=10)

        self.notlar_ck.add(self.tab_panel, text="  Panel  ")
        self.notlar_ck.add(self.tab_musteriler, text="  Müşteriler  ")
        self.notlar_ck.add(self.tab_urunler, text="  Ürünler & Fiyat  ")
        self.notlar_ck.add(self.tab_gecmis, text="  İşlem Geçmişi  ")
        self.notlar_ck.add(self.tab_yedek, text="  Yedek  ")

        self.notlar_ck.bind("<<NotebookTabChanged>>", self._sekme_degisti)
        self._panel_kur()
        self._musteriler_kur()
        self._urunler_kur()
        self._gecmis_kur()
        self._yedek_kur()

    def _sekme_degisti(self, _e=None):
        secili = self.notlar_ck.select()
        if secili == str(self.tab_panel):
            self.panel_yenile()
        elif secili == str(self.tab_musteriler):
            self.musteriler_yenile()
        elif secili == str(self.tab_urunler):
            self.urunler_yenile()
        elif secili == str(self.tab_gecmis):
            self.gecmis_yenile()
        elif secili == str(self.tab_yedek):
            self.yedek_yenile()

    # -------------------------------------------------------- ağaç yapıcı #
    def _agac(self, ebeveyn, basliklar, genislikler=None, sagalar=None, yuk=8):
        sarici = ttk.Frame(ebeveyn)
        sarici.pack(fill="both", expand=True, pady=(4, 0))
        g = genislikler or tuple(max(90, 1040 // len(basliklar)) for _ in basliklar)
        hizalar = ["w" for _ in basliklar]
        if sagalar:
            for i in sagalar:
                hizalar[i] = "e"
        agac = ttk.Treeview(sarici, columns=basliklar, show="headings", height=yuk)
        for b, w, h in zip(basliklar, g, hizalar):
            agac.heading(b, text=b)
            agac.column(b, width=w, anchor=h)
        agac.tag_configure("gecikmis", foreground=KIRMIZI)
        agac.tag_configure("pesin", foreground=UYARI)
        agac.tag_configure("ok", foreground=YESIL)
        agac.tag_configure("soluk", foreground=SOLUK)
        kay = ttk.Scrollbar(sarici, orient="vertical", command=agac.yview)
        agac.configure(yscrollcommand=kay.set)
        agac.pack(side="left", fill="both", expand=True)
        kay.pack(side="right", fill="y")
        return agac

    # ================================================================ PANEL
    def _panel_kur(self):
        kpi = ttk.Frame(self.tab_panel)
        kpi.pack(fill="x")
        self.kpi: dict[str, ttk.Label] = {}
        kartlar = [
            ("tl", "Toplam TL Alacak"),
            ("altin", "Toplam Altın Borç"),
            ("tl_deger", "Altının TL Değeri"),
            ("genel", "Genel Toplam"),
            ("tahsil_bugun", "Bugün Tahsilat (TL)"),
            ("satis_ay", "Bu Ay Veresiye (TL)"),
        ]
        for anahtar, etiket in kartlar:
            kart = ttk.Frame(kpi, style="Panel.TFrame", padding=(14, 12))
            kart.pack(side="left", fill="x", expand=True, padx=(0 if anahtar == "tl" else 8, 0))
            ttk.Label(kart, text=etiket, style="KpiEtiket.TLabel").pack(anchor="w")
            self.kpi[anahtar] = ttk.Label(kart, text="—", style="KpiDeger.TLabel")
            self.kpi[anahtar].pack(anchor="w")

        alt = ttk.Frame(self.tab_panel)
        alt.pack(fill="both", expand=True, pady=(12, 0))
        solv = ttk.Frame(alt)
        solv.pack(side="left", fill="both", expand=True)
        sags = ttk.Frame(alt)
        sags.pack(side="left", fill="both", expand=True, padx=(10, 0))

        ttk.Label(solv, text="Vadesi Geçenler", style="Altin.TLabel").pack(anchor="w")
        self.gecikmis_agac = self._agac(
            solv, ["Müşteri", "Vade", "TL Borç", "Altın", "Telefon"],
            genislikler=(170, 100, 110, 100, 120), sagalar=(2, 3))

        ttk.Label(sags, text="Ödeme Sözü Veren Borçlular", style="Altin.TLabel").pack(anchor="w")
        self.soz_agac = self._agac(
            sags, ["Müşteri", "Söz Tarihi", "Not", "TL Borç", "Altın"],
            genislikler=(140, 110, 170, 110, 100), sagalar=(3, 4))

        ttk.Label(self.tab_panel, text="Son İşlemler (son 15)", style="Altin.TLabel").pack(
            anchor="w", pady=(10, 0))
        self.son_agac = self._agac(
            self.tab_panel, ["Zaman", "İşlem", "Açıklama", "Tutar"], sagalar=(3,))

    def panel_yenile(self):
        v = sv.panel()
        self.fiyat_etiketi.configure(
            text=f"Güncel gram fiyatı: {tl(v['gram_fiyat'])}   ·   "
                 f"{v['musteri_sayisi']} aktif müşteri, {v['borclu_sayisi']} borçlu   ·   "
                 f"web sürümüyle aynı veri")
        self.kpi["tl"].configure(text=tl(v["tl_toplam"]))
        self.kpi["altin"].configure(text=gr(v["gr_toplam"]))
        self.kpi["tl_deger"].configure(text=tl(v["gr_deger"]))
        self.kpi["genel"].configure(text=tl(v["genel_deger"]))
        self.kpi["tahsil_bugun"].configure(text=tl(v["bugun_tl"]))
        self.kpi["satis_ay"].configure(text=tl(v["ay_satis_tl"]))

        for a in (self.gecikmis_agac, self.soz_agac, self.son_agac):
            a.delete(*a.get_children())

        for m in v.get("gecikmis", []):
            self.gecikmis_agac.insert("", "end", tags=("gecikmis",), values=(
                m["ad"], tarih_yaz(m.get("vade", "")), tl(m["tl_borc"]),
                gr(m["altin_borc"]), m.get("telefon", "")))

        for m in v.get("odeme_sozleri", []):
            self.soz_agac.insert("", "end", tags=("pesin",), values=(
                m["ad"], tarih_yaz(m["sozu_tarih"]), m.get("sozu_not", ""),
                tl(m["tl_borc"]), gr(m["altin_borc"])))

        for h in v.get("son_hareketler", []):
            tutar = gr(h.get("tutar", 0)) if h.get("pb") == "altin" else tl(h.get("tutar", 0))
            islem = str(h.get("aciklama") or h.get("tur", ""))
            self.son_agac.insert("", "end", tags=("ok",) if h.get("tur", "") != "Satış" else (),
                                 values=(tarih_yaz(h.get("zaman", "")), h.get("tur", ""),
                                         islem[:60], tutar))

    # ========================================================= MÜŞTERİLER
    def _musteriler_kur(self):
        ust = ttk.Frame(self.tab_musteriler)
        ust.pack(fill="x")
        ttk.Label(ust, text="Ara:").pack(side="left")
        self.m_ara = tk.StringVar()
        girdi = ttk.Entry(ust, textvariable=self.m_ara, width=30)
        girdi.pack(side="left", padx=8)
        girdi.bind("<KeyRelease>", lambda _e: self.musteriler_yenile())
        self.m_borclu = tk.BooleanVar(value=False)
        ttk.Checkbutton(ust, text="Sadece borçlular", variable=self.m_borclu,
                        command=self.musteriler_yenile).pack(side="left", padx=8)

        dugme = ttk.Frame(self.tab_musteriler)
        dugme.pack(fill="x", pady=8)
        for yazi, komut, stil in (
            ("+ Yeni Müşteri", self.musteri_dlg_yeni, "Altin.TButton"),
            ("✎ Düzenle", lambda: self._m_semma(self.musteri_dlg_duzenle), None),
            ("Satış Ekle", lambda: self._m_semma(self.satis_dlg), None),
            ("Tahsilat Al", lambda: self._m_semma(self.tahsilat_dlg), "Yesil.TButton"),
            ("Ekstre", lambda: self._m_semma(self.ekstre_penceresi), None),
            ("Arşivle / Geri Al", self.musteri_durum_degistir, None),
        ):
            ttk.Button(dugme, text=yazi,
                       style=stil or "TButton", command=komut).pack(side="left", padx=(0, 7))

        kolonlar = ["ad", "telefon", "kategori", "sozu", "tl_borc", "altin_borc", "limit"]
        basliklar = {"ad": "Müşteri", "telefon": "Telefon", "kategori": "Kategori",
                     "sozu": "Ödeme Sözü", "tl_borc": "TL Borç",
                     "altin_borc": "Altın Borç", "limit": "Limit"}
        genislikler = {"ad": 190, "telefon": 115, "kategori": 85, "sozu": 150,
                       "tl_borc": 95, "altin_borc": 95, "limit": 90}
        self.m_agac = ttk.Treeview(self.tab_musteriler, columns=kolonlar, show="headings")
        for k in kolonlar:
            self.m_agac.heading(k, text=basliklar[k])
            self.m_agac.column(k, width=genislikler[k],
                               anchor="e" if k in ("tl_borc", "altin_borc", "limit") else "w")
        kay = ttk.Scrollbar(self.tab_musteriler, orient="vertical",
                            command=self.m_agac.yview)
        self.m_agac.configure(yscrollcommand=kay.set)
        sarici = ttk.Frame(self.tab_musteriler)
        sarici.pack(fill="both", expand=True, pady=(0, 8))
        self.m_agac.pack(in_=sarici, side="left", fill="both", expand=True)
        kay.pack(in_=sarici, side="right", fill="y")
        self.m_agac.tag_configure("borc", foreground=KIRMIZI)
        self.m_agac.tag_configure("arsiv", foreground=SOLUK)
        self.m_agac.bind("<<TreeviewSelect>>", self._m_sec_degisti)
        self.m_agac.bind("<Double-1>", lambda _e: self._m_semma(self.ekstre_penceresi))
        self.musteriler_yenile()

    def _m_sec_degisti(self, _e=None):
        sec = self.m_agac.selection()
        if sec:
            iid = sec[0]
            if iid in ("arsiv_basi",) or not iid.isdigit():
                self.secili_musteri = None
            else:
                self.secili_musteri = int(iid)

    def _m_semma(self, fonks):
        if self.secili_musteri is None:
            messagebox.showinfo("Seçim yok", "Önce listeden bir müşteri seçin.")
            return
        fonks(self.secili_musteri)

    def musteriler_yenile(self):
        q = self.m_ara.get()
        self.m_agac.delete(*self.m_agac.get_children())
        arsiv = sv.musteriler(q=q, durum="arsiv")
        for m in sv.musteriler(q=q, sadece_borclu=self.m_borclu.get()):
            et = ("borc",) if m["borclu"] else ()
            soz = (tarih_yaz(m["sozu_tarih"]) + " " + (m.get("sozu_not") or "")[:18]).strip()
            self.m_agac.insert("", "end", iid=str(m["id"]), tags=et, values=(
                m["ad"], m["telefon"], m.get("kategori", ""), soz,
                tl(m["tl_borc"]), gr(m["altin_borc"]), tl(m["limit_tl"])))
        for m in arsiv:
            soz = (tarih_yaz(m["sozu_tarih"]) + " " + (m.get("sozu_not") or "")[:18]).strip()
            self.m_agac.insert("", "end", iid=str(m["id"]), tags=("arsiv",), values=(
                m["ad"] + "  (arşiv)", m["telefon"], m.get("kategori", ""), soz,
                tl(m["tl_borc"]), gr(m["altin_borc"]), tl(m["limit_tl"])))

    def musteri_dlg_yeni(self):
        self._musteri_dlg(None)

    def musteri_dlg_duzenle(self, mid):
        self._musteri_dlg(mid)

    def _musteri_dlg(self, mid):
        penc = tk.Toplevel(self.kok)
        penc.title("Müşteri Düzenle" if mid else "Yeni Müşteri")
        penc.configure(bg=PANEL, padx=18, pady=14)
        penc.transient(self.kok)
        penc.grab_set()
        penc.resizable(False, False)

        m = sv.musteri_getir(mid) if mid else None
        al: dict[str, tk.StringVar] = {}
        satirlar = [
            ("ad", "Ad *", (m["ad"] if m else "")),
            ("telefon", "Telefon", (m["telefon"] if m else "")),
            ("kategori", "Kategori", (m["kategori"] if m else "")),
            ("limit", "Kredi Limiti (₺, 0 = limitsiz)", (("%g" % m["limit_tl"]) if m else "0")),
            ("sozu_tarih", "Ödeme Sözü Tarihi (AAAA-AA-GG)", (m["sozu_tarih"] if m else "")),
            ("sozu_not", "Söz Notu", (m["sozu_not"] if m else "")),
            ("adres", "Adres", (m["adres"] if m else "")),
            ("notlar", "Not", (m["notlar"] if m else "")),
        ]
        for i, (k, etiket, varsayilan) in enumerate(satirlar):
            ttk.Label(penc, text=etiket, style="Panel.TLabel").grid(
                row=i, column=0, sticky="w", pady=4)
            al[k] = tk.StringVar(value=str(varsayilan))
            ttk.Entry(penc, textvariable=al[k], width=42).grid(
                row=i, column=1, sticky="we", pady=4)

        def kaydet():
            try:
                limit = sayi(al["limit"].get())
                if mid:
                    sv.musteri_guncelle(mid, al["ad"].get(), al["telefon"].get(),
                                        al["adres"].get(), al["notlar"].get(), limit,
                                        al["kategori"].get(), al["sozu_tarih"].get(),
                                        al["sozu_not"].get())
                    mesaj = "Müşteri güncellendi."
                else:
                    sv.musteri_ekle(al["ad"].get(), al["telefon"].get(), al["adres"].get(),
                                    al["notlar"].get(), limit, al["kategori"].get())
                    mesaj = "Müşteri kaydedildi."
            except ValueError as hata:
                messagebox.showwarning("Hata", str(hata), parent=penc)
                return
            self.musteriler_yenile()
            self.panel_yenile()
            penc.destroy()

        ttk.Button(penc, text="Kaydet", style="Altin.TButton", command=kaydet).grid(
            row=len(satirlar), column=0, columnspan=2, sticky="we", pady=(10, 0))
        penc.columnconfigure(1, weight=1)

    def musteri_durum_degistir(self, mid):
        m = sv.musteri_getir(mid)
        if not m:
            return
        try:
            if m["durum"] == "aktif":
                if not messagebox.askyesno(
                        "Arşivle", f"'{m['ad']}' arşivlensin mi?\n(SİLİNMEZ, "
                        "ekstresi ve işlem geçmişi aynen durur.)"):
                    return
                sv.musteri_durum(mid, "arsiv")
                mesaj = "Arşivlendi."
            else:
                sv.musteri_durum(mid, "aktif")
                mesaj = "Listeye geri alındı."
        except ValueError as hata:
            messagebox.showwarning("Hata", str(hata))
            return
        self.musteriler_yenile()
        self.panel_yenile()
        messagebox.showinfo("Tamam", mesaj)

    # ============================================================== satış #
    def satis_dlg(self, mid):
        penc = tk.Toplevel(self.kok)
        penc.title("Satış Ekle")
        penc.configure(bg=PANEL, padx=18, pady=14)
        penc.transient(self.kok)
        penc.grab_set()
        penc.resizable(False, False)
        m = sv.musteri_getir(mid)

        ttk.Label(penc, text=f"Müşteri: {m['ad']}", style="Altin.TLabel").pack(anchor="w")

        sekl = tk.StringVar(value="veresiye")
        pb = tk.StringVar(value="tl")
        grid = ttk.Frame(penc)
        grid.pack(fill="x", pady=6)

        def satir_i(no, etiket):
            ttk.Label(grid, text=etiket, style="Panel.TLabel").grid(
                row=no, column=0, sticky="w", pady=3)

        satir_i(0, "Satış Şekli")
        ttk.Combobox(grid, state="readonly", width=28,
                     values=["veresiye (borç)", "pesin (peşin)"],
                     textvariable=sekl).grid(row=0, column=1, sticky="w", padx=6, pady=3)
        satir_i(1, "Para Birimi")
        cb_pb = ttk.Combobox(grid, state="readonly", width=28,
                             values=["tl", "altin"], textvariable=pb)
        cb_pb.grid(row=1, column=1, sticky="w", padx=6, pady=3)

        satir_i(2, "Ürün (isteğe bağlı)")
        urun_okuma = tk.StringVar(value="— doğrudan gir —")
        cb_urun = ttk.Combobox(grid, state="readonly", width=28, textvariable=urun_okuma)
        secenekler = ["— doğrudan gir —"]
        urun_veri = {secenekler[0]: (0, 0.0, 0.0)}
        for u in sv.urunler():
            etiket = f"{u['ad']} ({u['birim']})  {tl(u['tl_fiyat'])} / {gr(u['gr_miktar'])}"
            secenekler.append(etiket)
            urun_veri[etiket] = (u["id"], u["tl_fiyat"], u["gr_miktar"])
        cb_urun["values"] = secenekler
        cb_urun.current(0)
        cb_urun.grid(row=2, column=1, sticky="w", padx=6, pady=3)

        ek: dict[str, tk.StringVar] = {}
        satirlar = [
            ("tarih", "Satış Tarihi (AAAA-AA-GG)", date.today().isoformat()),
            ("tutar", "Tutar *", ""),
            ("vade", "Vade (AAAA-AA-GG; peşinde boş)", ""),
            ("aciklama", "Açıklama", ""),
        ]
        for i, (k, etiket, varsayilan) in enumerate(satirlar, start=3):
            satir_i(i, etiket)
            ek[k] = tk.StringVar(value=varsayilan)
            ttk.Entry(grid, textvariable=ek[k], width=30).grid(
                row=i, column=1, sticky="w", padx=6, pady=3)

        def urun_secildiginde(_e=None):
            secim = urun_veri.get(urun_okuma.get())
            if not secim or not secim[0]:
                return
            miktar = secim[2] if pb.get() == "altin" else secim[1]
            if miktar:
                ek["tutar"].set(("%g" % miktar).replace(".", ","))
                ek["aciklama"].set(ek["aciklama"].get() or urun_okuma.get().split(" (")[0])

        cb_urun.bind("<<ComboboxSelected>>", urun_secildiginde)
        cb_pb.bind("<<ComboboxSelected>>", urun_secildiginde)

        def kaydet():
            sek = "pesin" if "pesin" in sekl.get() else "veresiye"
            try:
                sv.satis_ekle(musteri_id=mid, tarih=ek["tarih"].get() or date.today().isoformat(),
                              para_birimi=pb.get(), tutar=sayi(ek["tutar"].get()),
                              vade=ek["vade"].get(), aciklama=ek["aciklama"].get(),
                              sekl=sek, urun_id=(urun_veri.get(urun_okuma.get()) or (0,))[0])
            except ValueError as hata:
                messagebox.showwarning("Hata", str(hata), parent=penc)
                return
            penc.destroy()
            self.panel_yenile()
            self.musteriler_yenile()
            messagebox.showinfo(
                "Tamam", "Satış kaydedildi."
                if sek == "veresiye"
                else "Peşin satış kaydedildi (kasa defterine otomatik girdi).")

        ttk.Button(penc, text="Satışı Kaydet", style="Altin.TButton", command=kaydet).pack(
            fill="x", pady=(10, 0))

    # ========================================================= tahsilat #
    def tahsilat_dlg(self, mid):
        penc = tk.Toplevel(self.kok)
        penc.title("Tahsilat Al")
        penc.configure(bg=PANEL, padx=18, pady=14)
        penc.transient(self.kok)
        penc.grab_set()
        penc.resizable(False, False)
        m = sv.musteri_getir(mid)
        ttk.Label(penc, text=f"Müşteri: {m['ad']}   ·   Borç: {tl(m['tl_borc'])} + "
                             f"{gr(m['altin_borc'])}", style="Altin.TLabel").pack(anchor="w")

        pb = tk.StringVar(value="tl")
        hedef = tk.StringVar(value="tl")
        yontem = tk.StringVar(value="nakit")
        tarih = tk.StringVar(value=date.today().isoformat())
        tutar = tk.StringVar(value="")
        aciklama = tk.StringVar(value="")
        kur = tk.StringVar(value="%g" % sv.fiyat_getir())

        grid = ttk.Frame(penc)
        grid.pack(fill="x", pady=6)
        secenler = [
            ("tarih", "Tarih (AAAA-AA-GG)", tarih),
            ("tutar", "Tahsil Tutarı *", tutar),
            ("pb", "Nakit Türü (alınan)", pb, ["tl", "altin"]),
            ("hedef", "Hedef Borç (hangisi kapansın)", hedef, ["tl", "altin"]),
            ("yontem", "Yöntem", yontem,
             ["nakit", "kart", "havale", "cek", "senet"]),
            ("aciklama", "Açıklama", aciklama),
        ]
        for i, satir in enumerate(secenler):
            ttk.Label(grid, text=satir[1], style="Panel.TLabel").grid(
                row=i, column=0, sticky="w", pady=3)
            if len(satir) == 5:
                ttk.Combobox(grid, state="readonly", width=28, values=satir[4],
                             textvariable=satir[2]).grid(row=i, column=1, sticky="w",
                                                         padx=6, pady=3)
            else:
                ttk.Entry(grid, textvariable=satir[2], width=30).grid(
                    row=i, column=1, sticky="w", padx=6, pady=3)

        ttk.Label(penc, text="Nakit türü ile hedef borç farklıysa çevrim güncel gram "
                             "fiyatıyla yapılır; isterseniz kuru elle girin.",
                  style="Soluk.TLabel", background=PANEL).pack(anchor="w")
        kur_alan = ttk.Entry(penc, textvariable=kur, width=16)
        kur_alan.pack(anchor="w", pady=4)
        ozet_etiketi = tk.Label(penc, text="", bg=PANEL, fg=UYARI, justify="left")

        def ozet(_e=None):
            p, h = pb.get(), hedef.get()
            k = sayi(kur.get()) or sv.fiyat_getir()
            t = sayi(tutar.get())
            if p == h:
                ozet_etiketi.configure(text="Aynı birim — düz tahsilat.", fg=METIN)
            elif p == "tl":
                ozet_etiketi.configure(text=f"{tl(t)} ≈ {gr(t / k if k else 0)} altın "
                                            f"borcu kapatır (kur {tl(k)} / gr)", fg=UYARI)
            else:
                ozet_etiketi.configure(text=f"{gr(t)} ≈ {tl(t * k)} TL borcu kapatır "
                                            f"(kur {tl(k)} / gr)", fg=UYARI)

        pb.trace_add("write", ozet)
        hedef.trace_add("write", ozet)
        tutar.trace_add("write", ozet)
        kur.trace_add("write", ozet)
        ozet_etiketi.pack(anchor="w", pady=(2, 0))

        def kaydet():
            try:
                sv.odeme_ekle(mid,
                              tarih.get() or date.today().isoformat(), pb.get(),
                              sayi(tutar.get()), hedef.get(), yontem.get(),
                              aciklama.get(),
                              kur=(sayi(kur.get()) if sayi(kur.get()) > 0 else None))
            except ValueError as hata:
                messagebox.showwarning("Hata", str(hata), parent=penc)
                return
            penc.destroy()
            self.panel_yenile()
            self.musteriler_yenile()
            messagebox.showinfo("Tamam", "Tahsilat kaydedildi.")

        ttk.Button(penc, text="Tahsilatı Kaydet", style="Yesil.TButton",
                   command=kaydet).pack(fill="x", pady=(10, 0))

    # ============================================================ ekstre #
    def ekstre_penceresi(self, mid):
        e = sv.ekstre(mid)
        m = e["musteri"]
        penc = tk.Toplevel(self.kok)
        penc.title(f"Ekstre — {m['ad']}")
        penc.configure(bg=PANEL, padx=16, pady=12)
        penc.geometry("960x600")
        penc.transient(self.kok)

        metin = tk.Text(penc, bg=PANEL, fg=METIN, insertbackground=METIN,
                        font=("Consolas", 10), borderwidth=0, wrap="none",
                        selectbackground="#32363d")
        metin.pack(side="top", fill="both", expand=True)

        baslik = f"HESAP EKSTRESİ — {m['ad']}"
        if m["telefon"]:
            baslik += f"  ({m['telefon']})"
        metin.insert("end", baslik + "\n" + CIZI + "\n")
        metin.insert("end",
                     f"{'Tarih':<11}{'Açıklama':<28}{'Borç':>15}{'Tahsilat':>15}"
                     f"{'TL Bakiye':>13}{'Altın Bakiye':>12}\n")
        metin.insert("end", CIZI + "\n")
        for r in e["satirlar"]:
            borc = ""
            tahs = ""
            if r["borc"]:
                borc = gr(r["borc"]) if r["para_birimi"] == "altin" else tl(r["borc"])
            if r["tahsilat"]:
                tahs = gr(r["tahsilat"]) if r["para_birimi"] == "altin" else tl(r["tahsilat"])
            aciklama = (r["aciklama"] or "veresiye tahsilatı")[:27]
            metin.insert("end",
                         f"{tarih_yaz(r['tarih']):<11}{aciklama:<28}{borc:>15}{tahs:>15}"
                         f"{tl(r['tl_bakiye']):>13}{gr(r['altin_bakiye']):>12}\n")
        metin.insert("end", CIZI + "\n")
        b = e["bakiye"]
        if b["borclu"]:
            durum = "BORÇLU"
        elif b.get("avans"):
            durum = "avans var"
        else:
            durum = "kapandı"
        metin.insert("end", f"GÜNCEL BAKİYE ({durum}): {tl(b['tl_borc'])} + {gr(b['altin_borc'])}\n")
        if e["iptaller"]:
            metin.insert("end", f"İptal kayıt sayısı: {len(e['iptaller'])} (silinmedi)\n")

        def iptal_et():
            try:
                satir_no = int(metin.index("sel.first").split(".")[0])
            except tk.TclError:
                messagebox.showinfo("Seçim yok", "Önce ekstredeki bir işlem satırı seçin.",
                                    parent=penc)
                return
            secili = metin.get(f"{satir_no}.0", f"{satir_no}.end")
            eslesen = [r for r in e["satirlar"] if tarih_yaz(r["tarih"]) in secili]
            if not eslesen:
                messagebox.showinfo("Bulunamadı",
                                    "Seçili satır bir işlem satırı olmalı "
                                    "(başlık veya bakiye satırı değil).", parent=penc)
                return
            r = eslesen[-1]
            tur = "Satış" if r["tur"] == "satis" else "Tahsilat"
            sebep = simpledialog.askstring("İptal Sebebi", f"{tur} iptal sebebi:", parent=penc)
            if not (sebep or "").strip():
                return
            try:
                if r["tur"] == "satis":
                    sv.satis_iptal(r["id"], sebep)
                else:
                    sv.odeme_iptal(r["id"], sebep)
            except ValueError as hata:
                messagebox.showwarning("Hata", str(hata), parent=penc)
                return
            penc.destroy()
            self.panel_yenile()
            self.musteriler_yenile()
            messagebox.showinfo("Tamam", f"{tur} iptal edildi (kayıt duruyor).")

        bark = ttk.Frame(penc)
        bark.pack(side="top", fill="x", pady=(8, 0))
        ttk.Button(bark, text="İptal Et (seçili satır)", command=iptal_et).pack(side="left")
        ttk.Button(bark, text="Satış Ekle", style="Altin.TButton",
                   command=lambda: self.satis_dlg(mid)).pack(side="left", padx=6)
        ttk.Button(bark, text="Tahsilat Al", style="Yesil.TButton",
                   command=lambda: self.tahsilat_dlg(mid)).pack(side="left")
        ttk.Button(bark, text="TXT olarak Kaydet",
                   command=lambda: self._ekstre_kaydet(m, metin)).pack(side="right")

    def _ekstre_kaydet(self, m, metin: tk.Text):
        dosya = filedialog.asksaveasfilename(
            defaultextension=".txt", parent=self.kok,
            initialfile=f"ekstre_{m['ad'].replace(' ', '_')}_{date.today().isoformat()}.txt",
            filetypes=[("Metin dosyası", "*.txt")])
        if dosya:
            with open(dosya, "w", encoding="utf-8") as f:
                f.write(metin.get("1.0", "end"))
            messagebox.showinfo("Kaydedildi", dosya, parent=self.kok)

    # ======================================================= ÜRÜN / FİYAT
    def _urunler_kur(self):
        pan = ttk.Frame(self.tab_urunler)
        pan.pack(fill="both", expand=True)
        sol = ttk.Frame(pan)
        sol.pack(side="left", fill="both", expand=True, padx=(0, 12))
        sag = ttk.Frame(pan)
        sag.pack(side="left", fill="both", expand=True)

        kart = ttk.Frame(sol, style="Panel.TFrame", padding=14)
        kart.pack(fill="x")
        ttk.Label(kart, text="Yeni Ürün", style="Altin.TLabel").pack(anchor="w")
        uu: dict[str, tk.StringVar] = {}
        for k, etiket in [("ad", "Ürün Adı *"), ("birim", "Birim (adet/gr/cm/paket)"),
                          ("tl_fiyat", "TL Fiyatı"), ("gr_miktar", "Gram Miktarı"),
                          ("notlar", "Not")]:
            satir = ttk.Frame(kart)
            satir.pack(fill="x", pady=3)
            ttk.Label(satir, text=etiket, style="Panel.TLabel", width=24).pack(side="left")
            uu[k] = tk.StringVar()
            ttk.Entry(satir, textvariable=uu[k]).pack(side="left", fill="x", expand=True)

        def ekle():
            try:
                sv.urun_ekle(uu["ad"].get(), uu["birim"].get() or "adet",
                             sayi(uu["tl_fiyat"].get()), sayi(uu["gr_miktar"].get()),
                             uu["notlar"].get())
            except ValueError as hata:
                messagebox.showwarning("Hata", str(hata))
                return
            for v in uu.values():
                v.set("")
            self.urunler_yenile()

        ttk.Button(kart, text="Ürünü Ekle", style="Altin.TButton", command=ekle).pack(
            anchor="w", pady=(8, 0))

        ttk.Label(sol, text="Ürünler", style="Altin.TLabel").pack(anchor="w", pady=(10, 0))
        self.u_agac = self._agac(sol, ["Ürün", "Birim", "TL Fiyatı", "Gram"],
                                 genislikler=(200, 70, 110, 100), sagalar=(2, 3))

        self.u_secilen: int | None = None
        self.u_agac.bind("<<TreeviewSelect>>", self._u_sec_degisti)

        def durum_degistir():
            if self.u_secilen is None:
                messagebox.showinfo("Seçim yok", "Listeden bir ürün seçin.")
                return
            u = sv.urun_getir(self.u_secilen)
            if not u:
                return
            if u["durum"] == "aktif":
                soru = f"'{u['ad']}' arşivlensin mi? (silinmez)"
                yeni = "arsiv"
            else:
                soru = f"'{u['ad']}' listeye geri alınsın mı?"
                yeni = "aktif"
            if messagebox.askyesno("Ürün durumu", soru):
                sv.urun_durum(u["id"], yeni)
                self.urunler_yenile()

        ttk.Button(sol, text="Arşivle / Geri Al", command=durum_degistir).pack(
            anchor="w", pady=6)

        fkart = ttk.Frame(sag, style="Panel.TFrame", padding=14)
        fkart.pack(fill="x")
        ttk.Label(fkart, text="Gram Fiyatı Kaydet", style="Altin.TLabel").pack(anchor="w")
        self.f_tarih = tk.StringVar(value=date.today().isoformat())
        self.f_fiyat = tk.StringVar(value="%g" % sv.fiyat_getir())
        for etiket, var in [("Tarih (AAAA-AA-GG)", self.f_tarih), ("Fiyat (₺/gr)", self.f_fiyat)]:
            satir = ttk.Frame(fkart)
            satir.pack(fill="x", pady=3)
            ttk.Label(satir, text=etiket, style="Panel.TLabel", width=20).pack(side="left")
            ttk.Entry(satir, textvariable=var, width=16).pack(side="left")

        def fkaydet():
            try:
                sv.fiyat_kaydet(self.f_tarih.get() or date.today().isoformat(),
                                sayi(self.f_fiyat.get()))
            except ValueError as hata:
                messagebox.showwarning("Hata", str(hata))
                return
            self.panel_yenile()
            messagebox.showinfo("Tamam", "Fiyat kaydedildi.")

        ttk.Button(fkart, text="Fiyatı Kaydet", style="Altin.TButton", command=fkaydet).pack(
            anchor="w", pady=(8, 0))

        ttk.Label(sag, text="Fiyat Geçmişi (son 15)", style="Altin.TLabel").pack(
            anchor="w", pady=(10, 0))
        self.f_agac = self._agac(sag, ["Tarih", "Fiyat"], genislikler=(130, 130), sagalar=(1,))

    def _u_sec_degisti(self, _e=None):
        sec = self.u_agac.selection()
        if sec:
            self.u_secilen = int(self.u_agac.item(sec[0])["values"][0])

    def urunler_yenile(self):
        self.u_agac.delete(*self.u_agac.get_children())
        for u in sv.urunler():
            self.u_agac.insert("", "end", values=(u["ad"], u["birim"],
                                                  tl(u["tl_fiyat"]), gr(u["gr_miktar"])))
        self.f_agac.delete(*self.f_agac.get_children())
        for f in sv.fiyat_gecmisi(15):
            self.f_agac.insert("", "end", values=(tarih_yaz(f["tarih"]), tl(f["gram_fiyat"])))

    # ============================================================ GEÇMİŞ
    def _gecmis_kur(self):
        ttk.Label(self.tab_gecmis,
                  text="İşlem Geçmişi — salt-ekleme denetim kaydı (son 300)",
                  style="Altin.TLabel").pack(anchor="w")
        self.g_agac = self._agac(self.tab_gecmis,
                                 ["Zaman", "İşlem", "Tablo", "Kayıt"],
                                 genislikler=(150, 160, 130, 80))
        ttk.Label(self.tab_gecmis, text="Detay: satıra çift tıklayın.",
                  style="Soluk.TLabel").pack(anchor="w")
        self.g_detay_kutusu = tk.Text(self.tab_gecmis, height=9, bg=PANEL, fg=METIN,
                                      font=("Consolas", 9), borderwidth=0, wrap="word")
        self.g_detay_kutusu.pack(fill="x", pady=(6, 0))
        self.g_veri: dict[str, dict] = {}   # iid -> hareket detayı
        self.g_agac.bind("<Double-1>", self._gecmis_sec)

    def _gecmis_sec(self, _e=None):
        sec = self.g_agac.selection()
        kutu = self.g_detay_kutusu
        kutu.delete("1.0", "end")
        if not sec:
            return
        iid = sec[0]
        h = self.g_veri.get(iid)
        if h:
            kutu.insert("1.0", f"{h['zaman']} · {h['islem']} "
                         f"({h['tablo']} #{h['kayit_id']})\n\n"
                         + json.dumps(h["detay_nesne"], ensure_ascii=False, indent=2))
        else:
            kutu.insert("1.0", "Detay yok.")

    def gecmis_yenile(self):
        self.g_agac.delete(*self.g_agac.get_children())
        self.g_veri.clear()
        for h in sv.hareket_gecmisi(300):
            iid = self.g_agac.insert("", "end", values=(
                h["zaman"], h["islem"], h["tablo"], h["kayit_id"]))
            self.g_veri[iid] = h

    # ============================================================ YEDEK
    def _yedek_kur(self):
        kart = ttk.Frame(self.tab_yedek, style="Panel.TFrame", padding=14)
        kart.pack(fill="x")
        ttk.Label(kart, text="Otomatik Yedekler", style="Altin.TLabel").pack(anchor="w")
        ttk.Label(kart, text="Saatlik (son 72) + günlük (son 120) + aylık (son 24) yedekler, "
                             "program açıkken otomatik alınır.\nKaçırılan yedek bir sonraki "
                             "açılışta telafi edilir. Web sürümü açıkken de aynı mantık "
                             "aynen çalışır.",
                  style="Panel.TLabel", background=PANEL).pack(anchor="w")

        def manuel():
            try:
                dosya = self.yedekci.yedekle("manuel")
            except (RuntimeError, OSError) as hata:
                messagebox.showwarning("Hata", str(hata))
                return
            self.yedek_yenile()
            messagebox.showinfo("Tamam", f"Manuel yedek alındı:\n{dosya['dosya']}")

        ttk.Button(kart, text="Şimdi Yedekle", style="Altin.TButton", command=manuel).pack(
            anchor="w", pady=(8, 0))

        def json_aktar():
            dosya = filedialog.asksaveasfilename(
                defaultextension=".json", parent=self.kok,
                initialfile=f"tam_yedek_{date.today().isoformat()}.json")
            if dosya:
                with open(dosya, "w", encoding="utf-8") as f:
                    json.dump(sv.tam_disa_aktarim(), f, ensure_ascii=False, indent=2)
                messagebox.showinfo("Tamam", "Tam JSON yedeği kaydedildi:\n" + dosya)

        ttk.Button(kart, text="Tam JSON Yedeği İndir", style="Yesil.TButton",
                   command=json_aktar).pack(anchor="w", pady=(0, 0))

        ttk.Label(self.tab_yedek, text="Yedek Dosyaları (yeniler önce)",
                  style="Altin.TLabel").pack(anchor="w", pady=(12, 0))
        self.y_agac = self._agac(self.tab_yedek,
                                 ["Tür", "Dosya", "Zaman", "Boyut"],
                                 genislikler=(100, 420, 170, 110))
        self.yedek_yenile()

    def yedek_yenile(self):
        self.y_agac.delete(*self.y_agac.get_children())
        for y in self.yedekci.liste()[:80]:
            boyut = y["boyut"]
            okuma = (f"{boyut / 1024:.0f} KB" if boyut < 1024 * 1024
                     else f"{boyut / 1024 / 1024:.1f} MB")
            self.y_agac.insert("", "end", values=(
                y["tur"], os.path.basename(y["ad"]), tarih_yaz(y["zaman"]), okuma))

    # ===================================================== fiyat penceresi
    def fiyat_penceresi(self):
        penc = tk.Toplevel(self.kok)
        penc.title("Gram Fiyatı Güncelle")
        penc.configure(bg=PANEL, padx=18, pady=14)
        penc.transient(self.kok)
        penc.grab_set()
        penc.resizable(False, False)
        tarih = tk.StringVar(value=date.today().isoformat())
        fiyat = tk.StringVar(value="%g" % sv.fiyat_getir())
        b = ttk.Frame(penc)
        b.pack(fill="x")
        ttk.Label(b, text="Tarih:", style="Panel.TLabel").pack(side="left")
        ttk.Entry(b, textvariable=tarih, width=14).pack(side="left", padx=6)
        ttk.Label(b, text="Fiyat (₺/gr):", style="Panel.TLabel").pack(side="left", padx=(10, 0))
        ttk.Entry(b, textvariable=fiyat, width=14).pack(side="left", padx=6)

        def kaydet():
            try:
                sv.fiyat_kaydet(tarih.get() or date.today().isoformat(), sayi(fiyat.get()))
            except ValueError as hata:
                messagebox.showwarning("Hata", str(hata), parent=penc)
                return
            self.panel_yenile()
            self.urunler_yenile()
            penc.destroy()

        ttk.Button(penc, text="Kaydet", style="Altin.TButton", command=kaydet).pack(
            fill="x", pady=(10, 0))

    # ================================================================ kapat
    def kapat(self):
        self.yedekci.durdur()
        self.kok.destroy()


def main():
    vdb.init_db()   # veritabanı yoksa oluştur (web sürümü olmadan da çalışsın)
    kok = tk.Tk()
    Uygulama(kok)
    kok.mainloop()


if __name__ == "__main__":
    main()
