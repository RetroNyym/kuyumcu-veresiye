"""Kuyumcu Veresiye Premium — Masaüstü (tkinter) arayüz.

Web sürümüyle **aynı veritabanını** (veresiye.db) paylaşır: web'den girilen
kaydı masaüstünde (ve tersi) aynı anda görürsünüz. Aynı güvenlik kuralları:
hiçbir kayıt silinmez; iptal/arşiv olur; tüm işlemler denetim günlüğüne yazılır.

Çalıştırma:  python masaustu.py   (veya masaustu.bat çift tık)
EXE üretimi: pyinstaller kuyumcu_masaustu.spec
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
import tkinter as tk
import webbrowser
from datetime import date, datetime
from tkinter import filedialog, messagebox, simpledialog, ttk

# veresiye paketini bul (script proje kökünde ise doğrudan bulur)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lisans as ls     # noqa: E402
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
# İpucu (tooltip): düğme/alan üstünde küçük açıklama penceresi
# --------------------------------------------------------------------------- #
class Ipucu:
    def __init__(self, widget, yazi: str):
        self.widget = widget
        self.yazi = (yazi or "").strip()
        self.penc: tk.Toplevel | None = None
        widget.bind("<Enter>", self.goster, add="+")
        widget.bind("<Leave>", self.gizle, add="+")
        widget.bind("<ButtonPress>", self.gizle, add="+")

    def goster(self, _e=None):
        if self.penc or not self.yazi:
            return
        x = self.widget.winfo_rootx() + 14
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self.penc = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)
        cerceve = tk.Frame(tw, bg=ALTIN, padx=1, pady=1)   # ince altın çerçeve
        ic = tk.Label(cerceve, text=self.yazi, bg="#15181d", fg=METIN,
                      font=("Segoe UI", 9), justify="left", padx=12, pady=7,
                      wraplength=340)
        ic.pack()
        cerceve.pack()
        tw.wm_geometry(f"+{x}+{y}")

    def gizle(self, _e=None):
        if self.penc is not None:
            try:
                self.penc.destroy()
            except tk.TclError:
                pass
            self.penc = None


def ipucu(widget, yazi: str):
    """Widget'a kısa açıklama iliştirir (fare üstüne gelince görünür)."""
    Ipucu(widget, yazi)


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
    def _baslik(self) -> str:
        d = ls.durum()
        if d["lisansli"]:
            return "HACILAR KUYUMCULUK  ·  Lisanslı"
        return f"HACILAR KUYUMCULUK  ·  {d['kalan_yazi']}"

    def _tema_kur(self):
        self.kok.title(self._baslik())
        self.kok.geometry("1180x730")
        self.kok.minsize(1000, 640)
        self.kok.configure(bg=ARKA)

        # pencere simgesi (exe içine gömülü logo)
        simge = os.path.join(getattr(sys, "_MEIPASS",
                                      os.path.dirname(os.path.abspath(__file__))),
                             "hacilar.ico")
        if os.path.exists(simge):
            try:
                self.kok.iconbitmap(simge)
            except Exception:
                pass

        st = ttk.Style(self.kok)
        st.theme_use("clam")
        st.configure(".", background=ARKA, foreground=METIN,
                     fieldbackground=PANEL2, bordercolor=CIZGI,
                     lightcolor=PANEL, darkcolor=PANEL, troughcolor=PANEL2,
                     font=("Segoe UI", 10))
        st.configure("TFrame", background=ARKA)
        st.configure("Panel.TFrame", background=PANEL)
        st.configure("TNotebook", background=ARKA, borderwidth=0,
                     tabmargins=[10, 8, 10, 0])
        st.configure("TNotebook.Tab", background=PANEL, foreground=SOLUK,
                     padding=[18, 10], borderwidth=0, font=("Segoe UI", 10))
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
        st.configure("KpiUyari.TLabel", background=PANEL, foreground=KIRMIZI,
                     font=("Segoe UI", 16, "bold"))
        st.configure("TEntry", insertcolor=METIN, fieldbackground=PANEL2)
        st.configure("TSpinbox", fieldbackground=PANEL2, arrowcolor=ALTIN)
        st.configure("TCombobox", fieldbackground=PANEL2, arrowcolor=ALTIN)
        st.configure("TButton", background=PANEL2, foreground=METIN, padding=[14, 7],
                     borderwidth=1, focusthickness=0)
        st.map("TButton", background=[("active", "#2b2f36"), ("pressed", "#333945")],
               foreground=[("disabled", SOLUK)])
        st.configure("Altin.TButton", background="#3a3325", foreground=ALTIN_ACIK,
                     borderwidth=1, padding=[18, 8], font=("Segoe UI", 9, "bold"))
        st.map("Altin.TButton", background=[("active", "#4a4230"), ("pressed", "#2e2917")])
        st.configure("Yesil.TButton", background="#1e352a", foreground=YESIL,
                     padding=[18, 8], font=("Segoe UI", 9, "bold"))
        st.map("Yesil.TButton", background=[("active", "#274b39"), ("pressed", "#163024")])
        st.configure("TCheckbutton", background=ARKA, foreground=METIN, focuscolor=ARKA)
        st.map("TCheckbutton", background=[("active", ARKA)])
        st.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                     foreground=METIN, rowheight=30, borderwidth=0)
        st.configure("Treeview.Heading", background=PANEL2, foreground=SOLUK,
                     font=("Segoe UI", 9, "bold"), borderwidth=0, padding=[10, 7])
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
        ttk.Label(sol, text="◆ HACILAR KUYUMCULUK", style="Baslik.TLabel").pack(anchor="w")
        self.fiyat_etiketi = ttk.Label(sol, text="", style="Soluk.TLabel", background=PANEL)
        self.fiyat_etiketi.pack(anchor="w")

        sag = ttk.Frame(ust, style="Panel.TFrame")
        sag.pack(side="right")
        btn_fiyat = ttk.Button(sag, text="Gram Fiyatı Güncelle", style="Altin.TButton",
                               command=self.fiyat_penceresi)
        btn_fiyat.pack(side="right", padx=6)
        ipucu(btn_fiyat, "Güncel altın gram fiyatını kaydeder.\n"
                         "Altın borçların TL değeri bu fiyattan hesaplanır.")
        btn_pin = ttk.Button(sag, text="🔒 PIN Kilidi", command=self.pin_penceresi)
        btn_pin.pack(side="right", padx=6)
        ipucu(btn_pin, "Program açılışına PIN koyar.\n"
                       "Dükkan bilgisayarında başkaları hesabı göremez.")
        btn_lisans = ttk.Button(sag, text="🔑 Lisans", command=self.lisans_butonu)
        btn_lisans.pack(side="right", padx=6)
        ipucu(btn_lisans, "Demo durumunu gösterir.\n"
                          "Lisans anahtarınız varsa buradan girersiniz.")

    # ------------------------------------------------------------ sekmeler #
    def _sekmeler(self):
        self.notlar_ck = ttk.Notebook(self.kok)
        self.notlar_ck.pack(fill="both", expand=True, padx=8, pady=(4, 10))

        self.tab_panel = ttk.Frame(self.notlar_ck, padding=10)
        self.tab_musteriler = ttk.Frame(self.notlar_ck, padding=10)
        self.tab_urunler = ttk.Frame(self.notlar_ck, padding=10)
        self.tab_tedarik = ttk.Frame(self.notlar_ck, padding=10)
        self.tab_cek = ttk.Frame(self.notlar_ck, padding=10)
        self.tab_kasa = ttk.Frame(self.notlar_ck, padding=10)
        self.tab_rapor = ttk.Frame(self.notlar_ck, padding=10)
        self.tab_gecmis = ttk.Frame(self.notlar_ck, padding=10)
        self.tab_yedek = ttk.Frame(self.notlar_ck, padding=10)

        self.notlar_ck.add(self.tab_panel, text="  🏠 Panel  ")
        self.notlar_ck.add(self.tab_musteriler, text="  👥 Müşteriler  ")
        self.notlar_ck.add(self.tab_urunler, text="  🏷 Ürünler & Fiyat  ")
        self.notlar_ck.add(self.tab_tedarik, text="  🚚 Tedarikçiler  ")
        self.notlar_ck.add(self.tab_cek, text="  🧾 Çek & Senet  ")
        self.notlar_ck.add(self.tab_kasa, text="  💰 Kasa  ")
        self.notlar_ck.add(self.tab_rapor, text="  📈 Raporlar  ")
        self.notlar_ck.add(self.tab_gecmis, text="  🕘 İşlem Geçmişi  ")
        self.notlar_ck.add(self.tab_yedek, text="  💾 Yedek  ")

        self.notlar_ck.bind("<<NotebookTabChanged>>", self._sekme_degisti)
        self._panel_kur()
        self._musteriler_kur()
        self._urunler_kur()
        self._tedarik_kur()
        self._cek_kur()
        self._kasa_kur()
        self._rapor_kur()
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
        elif secili == str(self.tab_tedarik):
            self.tedarik_yenile()
        elif secili == str(self.tab_cek):
            self.cek_yenile()
        elif secili == str(self.tab_kasa):
            self.kasa_yenile()
        elif secili == str(self.tab_rapor):
            self.rapor_yenile()
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
        agac = ttk.Treeview(sarici, columns=basliklar, show="headings", height=yuk,
                            cursor="hand2")
        for b, w, h in zip(basliklar, g, hizalar):
            agac.heading(b, text=b)
            agac.column(b, width=w, anchor=h)
        agac.tag_configure("gecikmis", foreground=KIRMIZI)
        agac.tag_configure("pesin", foreground=UYARI)
        agac.tag_configure("ok", foreground=YESIL)
        agac.tag_configure("soluk", foreground=SOLUK)
        agac.tag_configure("cift", background="#191c21")
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
        kart_aciklamalari = {
            "tl": "Müşterilerin kapatilmemis toplam TL borcu.",
            "altin": "Müşterilerin toplam altin (gram) borcu.",
            "tl_deger": "Altin borclarin guncel gram fiyatindaki TL karsiligi.",
            "genel": "TL alacak + altin degeri toplami (genel durum).",
            "tahsil_bugun": "Bugun yapilan toplam tahsilat (TL).",
            "satis_ay": "Bu ay yapilan veresiye satislari (TL).",
            "gecikme": "Vadesi gecen alacaklarin toplami (TL degeri).",
            "orani": "Son 3 ayda veresiye satislarina gore tahsilat yuzdesi.",
            "risk": "Vadesi 90 gunden fazla gecmis alacaklar — once bunlari takip edin.",
        }
        for anahtar, etiket in kartlar:
            kart = ttk.Frame(kpi, style="Panel.TFrame", padding=(14, 12))
            kart.pack(side="left", fill="x", expand=True, padx=(0 if anahtar == "tl" else 8, 0))
            etik = ttk.Label(kart, text=etiket, style="KpiEtiket.TLabel")
            etik.pack(anchor="w")
            ipucu(etik, kart_aciklamalari[anahtar])
            self.kpi[anahtar] = ttk.Label(kart, text="—", style="KpiDeger.TLabel")
            self.kpi[anahtar].pack(anchor="w")

        # --- premium: yaşlandırma / tahsilat oranı / risk kartları ----------
        kpi2 = ttk.Frame(self.tab_panel)
        kpi2.pack(fill="x", pady=(8, 0))
        kartlar2 = [
            ("gecikme", "Vadesi Geçen Toplam (TL değeri)"),
            ("orani", "Tahsilat Oranı (son 3 ay)"),
            ("risk", "Yüksek Risk — 90+ Gün (TL değeri)"),
        ]
        for anahtar, etiket in kartlar2:
            kart = ttk.Frame(kpi2, style="Panel.TFrame", padding=(14, 12))
            kart.pack(side="left", fill="x", expand=True, padx=(0 if anahtar == "gecikme" else 8, 0))
            ttk.Label(kart, text=etiket, style="KpiEtiket.TLabel").pack(anchor="w")
            self.kpi[anahtar] = ttk.Label(kart, text="—", style="KpiDeger.TLabel")
            self.kpi[anahtar].pack(anchor="w")

        # --- premium: 6 aylık veresiye ↔ tahsilat trendi --------------------
        grafik_kart = ttk.Frame(self.tab_panel, style="Panel.TFrame", padding=(12, 8))
        grafik_kart.pack(fill="x", pady=(10, 0))
        ttk.Label(grafik_kart, text="6 Aylık Veresiye ↔ Tahsilat Trendi",
                  style="Altin.TLabel").pack(anchor="w")
        self.grafik = tk.Canvas(grafik_kart, bg=PANEL, highlightthickness=0,
                                height=150, borderwidth=0)
        self.grafik.pack(fill="x", pady=(4, 0))
        self.grafik.bind("<Configure>", lambda _e: self._grafik_guncelle())

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

        ya = sv.yaslandirma()
        self.kpi["gecikme"].configure(text=tl(sum(ya["kova"].values())))
        self.kpi["risk"].configure(text=tl(ya["kova"]["90+"]))
        self.kpi["orani"].configure(text=f"% {sv.tahsilat_orani(3):.1f}".replace(".", ","))
        self._grafik_guncelle()

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

    def _grafik_guncelle(self):
        tuval = getattr(self, "grafik", None)
        if tuval is None:
            return
        tuval.delete("all")
        try:
            veri = list(reversed(sv.rapor_aylik(6)))
        except Exception:
            return
        gen = tuval.winfo_width()
        if gen < 200:
            gen = 900
        yuk = 150
        sol, sag, ust, alt = 52, 12, 16, 26
        maks = max([r["satis_tl"] for r in veri] + [r["tahsilat_tl"] for r in veri] + [1.0])
        tuval.create_line(sol, yuk - alt, gen - sag, yuk - alt, fill=CIZGI, width=1)

        def xy(i, deger):
            x = sol + i * (gen - sol - sag) / max(len(veri) - 1, 1)
            y = (yuk - alt) - (deger / maks) * (yuk - alt - ust)
            return x, y

        AY_ADI = ["", "Oca", "Şub", "Mar", "Nis", "May", "Haz",
                  "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
        for i, r in enumerate(veri):
            x = xy(i, 0)[0]
            tuval.create_text(x, yuk - alt + 11, text=AY_ADI[int(r["ay"][5:7])],
                              fill=SOLUK, font=("Segoe UI", 8))
        for dizi, renk in (([r["satis_tl"] for r in veri], ALTIN),
                           ([r["tahsilat_tl"] for r in veri], YESIL)):
            noktalar = []
            for i, deger in enumerate(dizi):
                noktalar += xy(i, deger)
            if len(noktalar) >= 4:
                tuval.create_line(*noktalar, fill=renk, width=2, smooth=True)
            for i, deger in enumerate(dizi):
                x, y = xy(i, deger)
                tuval.create_oval(x - 3, y - 3, x + 3, y + 3, fill=renk, outline="")
        # gölge çizelge
        tuval.create_rectangle(sol + 2, 4, sol + 12, 14, fill=ALTIN, outline="")
        tuval.create_text(sol + 17, 9, text="Veresiye satış", fill=METIN,
                          font=("Segoe UI", 8), anchor="w")
        tuval.create_rectangle(sol + 110, 4, sol + 120, 14, fill=YESIL, outline="")
        tuval.create_text(sol + 125, 9, text="Tahsilat", fill=METIN,
                          font=("Segoe UI", 8), anchor="w")

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
        musteri_dugmeleri = (
            ("+ Yeni Müşteri", self.musteri_dlg_yeni, "Altin.TButton",
             "Yeni müşteri kartı açar: ad, telefon,\nkredi limiti, ödeme sözü, not."),
            ("✎ Düzenle", lambda: self._m_semma(self.musteri_dlg_duzenle), None,
             "Seçili müşterinin bilgilerini günceller."),
            ("Satış Ekle", lambda: self._m_semma(self.satis_dlg), None,
             "Seçili müşteriye veresiye veya peşin\nsatış işler."),
            ("Tahsilat Al", lambda: self._m_semma(self.tahsilat_dlg), "Yesil.TButton",
             "Seçili müşteriden ödeme alır.\nBorç eski satıştan başlayarak kapanır."),
            ("Ekstre", lambda: self._m_semma(self.ekstre_penceresi), None,
             "Seçili müşterinin hesap dökümünü açar\n(TXT veya Excel olarak kaydedilir)."),
            ("📱 WhatsApp Hatırlatma", lambda: self._m_semma(self.whatsapp_dlg), None,
             "Borç hatırlatma mesajı üretir,\nWhatsApp'ta açar veya panoya kopyalar."),
            ("📊 Excel'e Aktar", self.musterileri_excel_aktar, None,
             "Tüm müşteri listesini borçlarıyla\nbirlikte Excel (.xlsx) olarak kaydeder."),
            ("Arşivle / Geri Al", self.musteri_durum_degistir, None,
             "Seçili müşteriyi arşive kaldırır (silinmez)\nveya listeye geri alır."),
        )
        for yazi, komut, stil, aciklama in musteri_dugmeleri:
            btn = ttk.Button(dugme, text=yazi,
                             style=stil or "TButton", command=komut)
            btn.pack(side="left", padx=(0, 7))
            ipucu(btn, aciklama)

        kolonlar = ["ad", "telefon", "kategori", "sozu", "tl_borc", "altin_borc",
                    "gecikme", "limit"]
        basliklar = {"ad": "Müşteri", "telefon": "Telefon", "kategori": "Kategori",
                     "sozu": "Ödeme Sözü", "tl_borc": "TL Borç",
                     "altin_borc": "Altın Borç", "gecikme": "Vade Aşımı (gün)",
                     "limit": "Limit"}
        genislikler = {"ad": 180, "telefon": 110, "kategori": 80, "sozu": 140,
                       "tl_borc": 90, "altin_borc": 90, "gecikme": 105, "limit": 85}
        self.m_agac = ttk.Treeview(self.tab_musteriler, columns=kolonlar, show="headings")
        for k in kolonlar:
            self.m_agac.heading(k, text=basliklar[k])
            self.m_agac.column(k, width=genislikler[k],
                               anchor="e" if k in ("tl_borc", "altin_borc",
                                                   "gecikme", "limit") else "w")
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
            gun = int(m.get("gecikme_gun") or 0)
            et = ("borc",) if m["borclu"] else ()
            if gun > 0:
                et = et + ("gecikmis",)
            soz = (tarih_yaz(m["sozu_tarih"]) + " " + (m.get("sozu_not") or "")[:18]).strip()
            self.m_agac.insert("", "end", iid=str(m["id"]), tags=et, values=(
                m["ad"], m["telefon"], m.get("kategori", ""), soz,
                tl(m["tl_borc"]), gr(m["altin_borc"]), gun, tl(m["limit_tl"])))
        for m in arsiv:
            soz = (tarih_yaz(m["sozu_tarih"]) + " " + (m.get("sozu_not") or "")[:18]).strip()
            self.m_agac.insert("", "end", iid=str(m["id"]), tags=("arsiv",), values=(
                m["ad"] + "  (arşiv)", m["telefon"], m.get("kategori", ""), soz,
                tl(m["tl_borc"]), gr(m["altin_borc"]), 0, tl(m["limit_tl"])))

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
        ttk.Button(bark, text="Excel olarak Kaydet",
                   command=lambda: self._ekstre_excel(m, e)).pack(side="right", padx=(0, 6))

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

    # ======================================================= TEDARİKÇİLER
    def _tedarik_kur(self):
        ust = ttk.Frame(self.tab_tedarik)
        ust.pack(fill="x")
        ttk.Label(ust, text="Ara:").pack(side="left")
        self.t_ara = tk.StringVar()
        girdi = ttk.Entry(ust, textvariable=self.t_ara, width=26)
        girdi.pack(side="left", padx=8)
        girdi.bind("<KeyRelease>", lambda _e: self.tedarik_yenile())

        dugme = ttk.Frame(self.tab_tedarik)
        dugme.pack(fill="x", pady=8)
        for yazi, komut, stil, aciklama in (
            ("+ Yeni Tedarikçi", self.tedarikci_dlg_yeni, "Altin.TButton",
             "Mal aldığınız kişiyi/firmayı tanımlarsınız.\n(Bizim borcumuz — cari hesap)"),
            ("✎ Düzenle", lambda: self._t_semma(self.tedarikci_dlg), None,
             "Seçili tedarikçinin bilgilerini günceller."),
            ("Mal Alışı", lambda: self._t_semma(self.alis_dlg), None,
             "Seçili tedarikçiden yapılan alışı\nborç olarak işler."),
            ("Ödeme Yap", lambda: self._t_semma(self.tedarik_odeme_dlg), "Yesil.TButton",
             "Tedarikçiye yaptığınız ödemeyi kaydeder;\nborcu azalır."),
            ("Ekstre", lambda: self._t_semma(self.tedarik_ekstre_penceresi), None,
             "Alış-ödeme dökümünü açar\n(Excel olarak kaydedilebilir)."),
            ("Arşivle / Geri Al", self.tedarik_durum_degistir, None,
             "Seçili tedarikçiyi arşivler (silinmez)\nveya listeye geri alır."),
        ):
            btn = ttk.Button(dugme, text=yazi, style=stil or "TButton", command=komut)
            btn.pack(side="left", padx=(0, 7))
            ipucu(btn, aciklama)

        self.t_agac = self._agac(self.tab_tedarik,
                                 ["Tedarikçi", "Telefon", "Alış Toplamı",
                                  "Ödeme Toplamı", "Kalan Borcumuz"],
                                 genislikler=(220, 130, 130, 130, 140),
                                 sagalar=(2, 3, 4), yuk=14)
        self.t_secilen: int | None = None
        self.t_agac.bind("<<TreeviewSelect>>", self._t_sec_degisti)

    def _t_sec_degisti(self, _e=None):
        sec = self.t_agac.selection()
        if sec and sec[0].isdigit():
            self.t_secilen = int(sec[0])
        else:
            self.t_secilen = None

    def _t_semma(self, fonks):
        if self.t_secilen is None:
            messagebox.showinfo("Seçim yok", "Önce listeden bir tedarikçi seçin.")
            return
        fonks(self.t_secilen)

    def tedarik_yenile(self):
        self.t_agac.delete(*self.t_agac.get_children())
        for t in sv.tedarikciler(q=self.t_ara.get(), durum="arsiv"):
            self.t_agac.insert("", "end", iid=str(t["id"]), tags=("soluk",), values=(
                t["ad"] + "  (arşiv)", t["telefon"], tl(t["alis_toplam"]),
                tl(t["odeme_toplam"]), tl(t["borc"])))
        for t in sv.tedarikciler(q=self.t_ara.get()):
            et = ("gecikmis",) if t["borclu"] else ("ok",)
            self.t_agac.insert("", "end", iid=str(t["id"]), tags=et, values=(
                t["ad"], t["telefon"], tl(t["alis_toplam"]),
                tl(t["odeme_toplam"]), tl(t["borc"])))

    def tedarikci_dlg_yeni(self):
        self.tedarikci_dlg(None)

    def tedarikci_dlg(self, tid):
        penc = tk.Toplevel(self.kok)
        penc.title("Tedarikçi Düzenle" if tid else "Yeni Tedarikçi")
        penc.configure(bg=PANEL, padx=18, pady=14)
        penc.transient(self.kok)
        penc.grab_set()
        penc.resizable(False, False)
        t = sv.tedarikci_getir(tid) if tid else None
        al: dict[str, tk.StringVar] = {}
        satirlar = [("ad", "Ad *", (t["ad"] if t else "")),
                    ("telefon", "Telefon", (t["telefon"] if t else "")),
                    ("notlar", "Not", (t["notlar"] if t else ""))]
        for i, (k, etiket, varsayilan) in enumerate(satirlar):
            ttk.Label(penc, text=etiket, style="Panel.TLabel").grid(
                row=i, column=0, sticky="w", pady=4)
            al[k] = tk.StringVar(value=str(varsayilan))
            ttk.Entry(penc, textvariable=al[k], width=38).grid(
                row=i, column=1, sticky="we", pady=4)

        def kaydet():
            try:
                if tid:
                    sv.tedarikci_duzenle(tid, al["ad"].get(), al["telefon"].get(),
                                         al["notlar"].get())
                else:
                    sv.tedarikci_ekle(al["ad"].get(), al["telefon"].get(),
                                      al["notlar"].get())
            except ValueError as hata:
                messagebox.showwarning("Hata", str(hata), parent=penc)
                return
            self.tedarik_yenile()
            penc.destroy()

        ttk.Button(penc, text="Kaydet", style="Altin.TButton",
                   command=kaydet).grid(row=len(satirlar), column=0,
                                        columnspan=2, sticky="we", pady=(10, 0))
        penc.columnconfigure(1, weight=1)

    def alis_dlg(self, tid):
        t = sv.tedarikci_getir(tid)
        penc = tk.Toplevel(self.kok)
        penc.title(f"Mal Alışı — {t['ad']}")
        penc.configure(bg=PANEL, padx=18, pady=14)
        penc.transient(self.kok)
        penc.grab_set()
        penc.resizable(False, False)
        ttk.Label(penc, text=f"Tedarikçi: {t['ad']}   ·   Mevcut borcumuz: "
                             f"{tl(t['borc'])}", style="Altin.TLabel").pack(anchor="w")
        al = {"tarih": tk.StringVar(value=date.today().isoformat()),
              "tutar": tk.StringVar(), "aciklama": tk.StringVar()}
        for k, etiket in (("tarih", "Tarih (AAAA-AA-GG)"), ("tutar", "Tutar *"),
                          ("aciklama", "Açıklama")):
            ttk.Label(penc, text=etiket, style="Panel.TLabel").pack(
                anchor="w", pady=(8, 0))
            ttk.Entry(penc, textvariable=al[k], width=30).pack(anchor="w")

        def kaydet():
            try:
                sv.alis_ekle(tid, al["tarih"].get() or date.today().isoformat(),
                             sayi(al["tutar"].get()), al["aciklama"].get())
            except ValueError as hata:
                messagebox.showwarning("Hata", str(hata), parent=penc)
                return
            penc.destroy()
            self.tedarik_yenile()
            messagebox.showinfo("Tamam", "Mal alışı kaydedildi.")

        ttk.Button(penc, text="Alışı Kaydet", style="Altin.TButton",
                   command=kaydet).pack(fill="x", pady=(12, 0))

    def tedarik_odeme_dlg(self, tid):
        t = sv.tedarikci_getir(tid)
        penc = tk.Toplevel(self.kok)
        penc.title(f"Tedarikçiye Ödeme — {t['ad']}")
        penc.configure(bg=PANEL, padx=18, pady=14)
        penc.transient(self.kok)
        penc.grab_set()
        penc.resizable(False, False)
        ttk.Label(penc, text=f"Tedarikçi: {t['ad']}   ·   Borcumuz: {tl(t['borc'])}",
                  style="Altin.TLabel").pack(anchor="w")
        al = {"tarih": tk.StringVar(value=date.today().isoformat()),
              "tutar": tk.StringVar(),
              "yontem": tk.StringVar(value="nakit"),
              "aciklama": tk.StringVar()}
        satirlar = [("tarih", "Tarih (AAAA-AA-GG)", None),
                    ("tutar", "Tutar *", None),
                    ("yontem", "Yöntem", ["nakit", "kart", "havale", "cek", "senet"]),
                    ("aciklama", "Açıklama", None)]
        for i, (k, etiket, secenekler) in enumerate(satirlar):
            ttk.Label(penc, text=etiket, style="Panel.TLabel").pack(
                anchor="w", pady=(8, 0))
            if secenekler:
                ttk.Combobox(penc, state="readonly", width=27,
                             values=secenekler, textvariable=al[k]).pack(anchor="w")
            else:
                ttk.Entry(penc, textvariable=al[k], width=30).pack(anchor="w")

        def kaydet():
            try:
                sv.tedarik_odeme_ekle(tid, al["tarih"].get() or date.today().isoformat(),
                                      sayi(al["tutar"].get()), al["yontem"].get(),
                                      al["aciklama"].get())
            except ValueError as hata:
                messagebox.showwarning("Hata", str(hata), parent=penc)
                return
            penc.destroy()
            self.tedarik_yenile()
            messagebox.showinfo("Tamam", "Ödeme kaydedildi.")

        ttk.Button(penc, text="Ödemeyi Kaydet", style="Yesil.TButton",
                   command=kaydet).pack(fill="x", pady=(12, 0))

    def tedarik_ekstre_penceresi(self, tid):
        e = sv.tedarik_ekstre(tid)
        t = e["tedarikci"]
        penc = tk.Toplevel(self.kok)
        penc.title(f"Tedarikçi Ekstresi — {t['ad']}")
        penc.configure(bg=PANEL, padx=16, pady=12)
        penc.geometry("820x560")
        penc.transient(self.kok)
        metin = tk.Text(penc, bg=PANEL, fg=METIN, insertbackground=METIN,
                        font=("Consolas", 10), borderwidth=0, wrap="none")
        metin.pack(side="top", fill="both", expand=True)
        metin.insert("end", f"TEDARİKÇİ HESAP DÖKÜMÜ — {t['ad']}\n" + CIZI + "\n")
        metin.insert("end", f"{'Tarih':<11}{'Açıklama':<34}{'Alış (Borç)':>15}"
                             f"{'Ödeme':>15}{'Bakiye':>14}\n")
        metin.insert("end", CIZI + "\n")
        harita: dict[int, dict] = {}
        for r in e["satirlar"]:
            no = int(metin.index("end").split(".")[0])
            harita[no] = r
            metin.insert("end", f"{tarih_yaz(r['tarih']):<11}"
                                 f"{(r['aciklama'] or 'mal alışı')[:33]:<34}"
                                 f"{tl(r['borc']) if r['borc'] else '':>15}"
                                 f"{tl(r['odeme']) if r['odeme'] else '':>15}"
                                 f"{tl(r['bakiye']):>14}\n")
        metin.insert("end", CIZI + "\n")
        metin.insert("end", f"GÜNCEL BORCUMUZ: {tl(e['bakiye'])}\n")

        def iptal_et():
            try:
                no = int(metin.index("sel.first").split(".")[0])
            except tk.TclError:
                messagebox.showinfo("Seçim yok", "Önce bir işlem satırı seçin.",
                                    parent=penc)
                return
            r = harita.get(no)
            if not r:
                messagebox.showinfo("Uygun değil", "Lütfen bir işlem satırı seçin.",
                                    parent=penc)
                return
            tur = "Mal alışı" if r["tur"] == "alis" else "Ödeme"
            sebep = simpledialog.askstring("İptal Sebebi", f"{tur} iptal sebebi:",
                                           parent=penc)
            if not (sebep or "").strip():
                return
            try:
                if r["tur"] == "alis":
                    sv.alis_iptal(r["id"], sebep)
                else:
                    sv.tedarik_odeme_iptal(r["id"], sebep)
            except ValueError as hata:
                messagebox.showwarning("Hata", str(hata), parent=penc)
                return
            penc.destroy()
            self.tedarik_yenile()
            messagebox.showinfo("Tamam", f"{tur} iptal edildi (kayıt durur).")

        bark = ttk.Frame(penc)
        bark.pack(side="top", fill="x", pady=(8, 0))
        ttk.Button(bark, text="İptal Et (seçili satır)", command=iptal_et).pack(side="left")
        ttk.Button(bark, text="Excel olarak Kaydet", command=lambda: excel_kaydet(
            self.kok, ["Tarih", "Açıklama", "Alış", "Ödeme", "Bakiye"],
            [[r["tarih"], r["aciklama"], r["borc"], r["odeme"], r["bakiye"]]
             for r in e["satirlar"]],
            f"tedarikci_{t['ad'].replace(' ', '_')}_{date.today().isoformat()}.xlsx"
        )).pack(side="right")

    def tedarik_durum_degistir(self, tid):
        t = sv.tedarikci_getir(tid)
        if not t:
            return
        if t["durum"] == "aktif":
            if messagebox.askyesno("Arşivle", f"'{t['ad']}' arşivlensin mi? (silinmez)"):
                sv.tedarikci_durum(tid, "arsiv")
        else:
            if messagebox.askyesno("Geri Al", f"'{t['ad']}' listeye geri alınsın mı?"):
                sv.tedarikci_durum(tid, "aktif")
        self.tedarik_yenile()

    # ======================================================= ÇEK & SENET
    def _cek_kur(self):
        ozet = ttk.Frame(self.tab_cek)
        ozet.pack(fill="x")
        self.cek_kpi: dict[str, ttk.Label] = {}
        for anahtar, etiket in (
            ("cek_adet", "Portföyde Çek (adet)"),
            ("cek_toplam", "Portföyde Çek (TL)"),
            ("senet_adet", "Portföyde Senet (adet)"),
            ("senet_toplam", "Portföyde Senet (TL)"),
        ):
            kart = ttk.Frame(ozet, style="Panel.TFrame", padding=(14, 12))
            kart.pack(side="left", fill="x", expand=True,
                      padx=(0 if anahtar == "cek_adet" else 8, 0))
            ttk.Label(kart, text=etiket, style="KpiEtiket.TLabel").pack(anchor="w")
            self.cek_kpi[anahtar] = ttk.Label(kart, text="—", style="KpiDeger.TLabel")
            self.cek_kpi[anahtar].pack(anchor="w")

        dugme = ttk.Frame(self.tab_cek)
        dugme.pack(fill="x", pady=8)
        btn_ekle = ttk.Button(dugme, text="+ Çek / Senet Ekle", style="Altin.TButton",
                              command=self.cek_ekle_dlg)
        btn_ekle.pack(side="left", padx=(0, 7))
        ipucu(btn_ekle, "Müşteriden alınan çeki/senedi portföye kaydeder.\n"
                        "Vade tarihi zorunludur.")
        btn_durum = ttk.Button(dugme, text="Durumu Değiştir", command=self.cek_durum_dlg)
        btn_durum.pack(side="left", padx=(0, 7))
        ipucu(btn_durum, "Tahsil edildi / karşı tarafa hamle / karşılıksız / portföye al.\n"
                         "'Tahsil edildi' seçilirse müşteriye otomatik tahsilat yazılır.")

        filtre = ttk.Frame(self.tab_cek)
        filtre.pack(fill="x", pady=(0, 4))
        ttk.Label(filtre, text="Tür:").pack(side="left")
        self.cek_tur = tk.StringVar(value="hepsi")
        ttk.Combobox(filtre, state="readonly", width=10, values=["hepsi", "cek", "senet"],
                     textvariable=self.cek_tur).pack(side="left", padx=(6, 14))
        ttk.Label(filtre, text="Durum:").pack(side="left")
        self.cek_durum = tk.StringVar(value="hepsi")
        ttk.Combobox(filtre, state="readonly", width=22,
                     values=["hepsi", "Portföyde", "Tahsil Edildi",
                             "Karşı Tarafa Hamle", "Karşılıksız"],
                     textvariable=self.cek_durum).pack(side="left", padx=6)

        self.cek_agac = self._agac(self.tab_cek,
                                   ["Tür", "Müşteri", "Banka", "Belge No", "Tutar",
                                    "Vade", "Kalan Gün", "Durum"],
                                   genislikler=(70, 180, 130, 110, 110, 100, 90, 150),
                                   sagalar=(4, 5), yuk=12)
        self.cek_agac.bind("<Double-1>", lambda _e: self.cek_durum_dlg())
        self.cek_yenile()

    def cek_yenile(self):
        o = sv.cek_portfoy_ozeti()
        self.cek_kpi["cek_adet"].configure(text=str(o["cek_adet"]))
        self.cek_kpi["cek_toplam"].configure(text=tl(o["cek_toplam"]))
        self.cek_kpi["senet_adet"].configure(text=str(o["senet_adet"]))
        self.cek_kpi["senet_toplam"].configure(text=tl(o["senet_toplam"]))

        self.cek_agac.delete(*self.cek_agac.get_children())
        tur = "" if self.cek_tur.get() == "hepsi" else self.cek_tur.get()
        durumlar = {"hepsi": "", "Portföyde": "portfoy", "Tahsil Edildi": "tahsil",
                    "Karşı Tarafa Hamle": "karsi_hamle", "Karşılıksız": "karsiliksiz"}
        durum = durumlar.get(self.cek_durum.get(), "")
        for c in sv.cekler(tur=tur, durum=durum):
            if c["durum"] == "portfoy" and c["gun_kaldi"] is not None:
                et = ("gecikmis",) if c["gun_kaldi"] < 0 else (
                    "pesin",) if c["gun_kaldi"] <= 7 else ()
            else:
                et = ("ok",) if c["durum"] == "tahsil" else ("soluk",)
            kalan = ("—" if c["gun_kaldi"] is None or c["durum"] != "portfoy"
                     else str(c["gun_kaldi"]))
            self.cek_agac.insert("", "end", iid=str(c["id"]), tags=et, values=(
                "Çek" if c["tur"] == "cek" else "Senet", c["musteri_ad"],
                c["banka"], c["belge_no"], tl(c["tutar"]), tarih_yaz(c["vade"]),
                kalan, sv.CEK_DURUMLERI[c["durum"]]))

    def cek_ekle_dlg(self):
        musteriler = sv.musteriler(durum="aktif")
        if not musteriler:
            messagebox.showinfo("Müşteri yok", "Önce müşteri tanımlayın.")
            return
        penc = tk.Toplevel(self.kok)
        penc.title("Çek / Senet Ekle")
        penc.configure(bg=PANEL, padx=18, pady=14)
        penc.transient(self.kok)
        penc.grab_set()
        penc.resizable(False, False)
        al = {"tur": tk.StringVar(value="cek"),
              "musteri": tk.StringVar(value=musteriler[0]["ad"]),
              "banka": tk.StringVar(), "belge_no": tk.StringVar(),
              "tutar": tk.StringVar(), "tarih": tk.StringVar(value=date.today().isoformat()),
              "vade": tk.StringVar(), "notlar": tk.StringVar()}
        harita = {m["ad"]: m["id"] for m in musteriler}
        satirlar = [("tur", "Tür", ["cek", "senet"]),
                    ("musteri", "Müşteri *", sorted(harita)),
                    ("banka", "Banka / Çeken"), ("belge_no", "Belge No"),
                    ("tutar", "Tutar *"), ("tarih", "Alış Tarihi (AAAA-AA-GG)"),
                    ("vade", "Vade (AAAA-AA-GG) *"), ("notlar", "Not")]
        for i, (k, etiket, secenekler) in enumerate(satirlar):
            ttk.Label(penc, text=etiket, style="Panel.TLabel").grid(
                row=i, column=0, sticky="w", pady=3)
            if secenekler:
                ttk.Combobox(penc, state="readonly", width=26, values=secenekler,
                             textvariable=al[k]).grid(row=i, column=1, padx=6, pady=3)
            else:
                ttk.Entry(penc, textvariable=al[k], width=28).grid(
                    row=i, column=1, padx=6, pady=3)

        def kaydet():
            try:
                sv.cek_ekle(al["tur"].get(), harita.get(al["musteri"].get(), 0),
                            al["banka"].get(), al["belge_no"].get(),
                            sayi(al["tutar"].get()), al["tarih"].get(),
                            al["vade"].get(), al["notlar"].get())
            except ValueError as hata:
                messagebox.showwarning("Hata", str(hata), parent=penc)
                return
            penc.destroy()
            self.cek_yenile()
            messagebox.showinfo("Tamam", "Çek/senet portföye kaydedildi.")

        ttk.Button(penc, text="Kaydet", style="Altin.TButton",
                   command=kaydet).grid(row=len(satirlar), column=0, columnspan=2,
                                        sticky="we", pady=(10, 0))
        penc.columnconfigure(1, weight=1)

    def cek_durum_dlg(self):
        sec = self.cek_agac.selection()
        if not sec or not sec[0].isdigit():
            messagebox.showinfo("Seçim yok", "Önce listeden bir çek/senet seçin.")
            return
        cid = int(sec[0])
        penc = tk.Toplevel(self.kok)
        penc.title("Durumu Değiştir")
        penc.configure(bg=PANEL, padx=18, pady=14)
        penc.transient(self.kok)
        penc.grab_set()
        penc.resizable(False, False)
        ttk.Label(penc, text="Yeni durum:", style="Panel.TLabel").pack(anchor="w")
        yeni = tk.StringVar(value="Tahsil Edildi")
        ttk.Combobox(penc, state="readonly", width=24,
                     values=list(sv.CEK_DURUMLERI.values()),
                     textvariable=yeni).pack(anchor="w", pady=6)
        ttk.Label(penc, text="'Tahsil Edildi' seçilirse müşteriye otomatik\n"
                             "tahsilat kaydı oluşur.", style="Soluk.TLabel",
                  background=PANEL).pack(anchor="w")

        ters = {v: k for k, v in sv.CEK_DURUMLERI.items()}

        def kaydet():
            try:
                sv.cek_durum(cid, ters[yeni.get()])
            except ValueError as hata:
                messagebox.showwarning("Hata", str(hata), parent=penc)
                return
            penc.destroy()
            self.cek_yenile()
            self.panel_yenile()
            messagebox.showinfo("Tamam", "Durum güncellendi.")

        ttk.Button(penc, text="Kaydet", style="Altin.TButton",
                   command=kaydet).pack(fill="x", pady=(10, 0))

    # ======================================================= KASA
    def _kasa_kur(self):
        filtre = ttk.Frame(self.tab_kasa)
        filtre.pack(fill="x")
        bugun_str = date.today().isoformat()
        ay_basi = bugun_str[:8] + "01"
        ttk.Label(filtre, text="Başlangıç:").pack(side="left")
        self.k_bas = tk.StringVar(value=ay_basi)
        ttk.Entry(filtre, textvariable=self.k_bas, width=12).pack(side="left", padx=6)
        ttk.Label(filtre, text="Bitiş:").pack(side="left")
        self.k_bit = tk.StringVar(value=bugun_str)
        ttk.Entry(filtre, textvariable=self.k_bit, width=12).pack(side="left", padx=6)
        btn = ttk.Button(filtre, text="Özeti Yenile", command=self.kasa_yenile)
        btn.pack(side="left", padx=10)
        ipucu(btn, "Seçilen tarih aralığındaki kasa hareketlerini listeler.")

        self.kasa_kpi: dict[str, ttk.Label] = {}
        kpi = ttk.Frame(self.tab_kasa)
        kpi.pack(fill="x", pady=(10, 0))
        for anahtar, etiket in (("giren", "Giren (TL)"), ("cikan", "Çıkan (TL)"),
                                ("net", "Net Aralık (TL)"), ("bakiye", "Kasa Bakiyesi")):
            kart = ttk.Frame(kpi, style="Panel.TFrame", padding=(14, 12))
            kart.pack(side="left", fill="x", expand=True,
                      padx=(0 if anahtar == "giren" else 8, 0))
            ttk.Label(kart, text=etiket, style="KpiEtiket.TLabel").pack(anchor="w")
            self.kasa_kpi[anahtar] = ttk.Label(kart, text="—", style="KpiDeger.TLabel")
            self.kasa_kpi[anahtar].pack(anchor="w")

        dugme = ttk.Frame(self.tab_kasa)
        dugme.pack(fill="x", pady=8)
        btn_gelir = ttk.Button(dugme, text="+ Gelir", style="Yesil.TButton",
                               command=lambda: self.kasa_hareket_dlg("gelir"))
        btn_gelir.pack(side="left", padx=(0, 7))
        ipucu(btn_gelir, "Kasaya manuel gelir girişi (kira, kasa fazla gibi).")
        btn_gider = ttk.Button(dugme, text="+ Gider", command=lambda: self.kasa_hareket_dlg("gider"))
        btn_gider.pack(side="left", padx=(0, 7))
        ipucu(btn_gider, "Kasadan manuel gider çıkışı (kira, elektrik, maaş gibi).")
        btn_iptal = ttk.Button(dugme, text="İptal Et (manuel kayıt)", command=self.kasa_iptal_et)
        btn_iptal.pack(side="left")
        ipucu(btn_iptal, "Seçili manuel gelir/gideri iptal eder (kayıt silinmez).\n"
                         "Otomatik tahsilat/peşin kayıtları ekstreden iptal edilir.")

        self.kasa_agac = self._agac(self.tab_kasa,
                                    ["Tarih", "Kaynak", "Tür", "Kategori",
                                     "Açıklama", "Tutar", "Bakiye"],
                                    genislikler=(95, 90, 70, 120, 330, 110, 120),
                                    sagalar=(5, 6), yuk=13)
        self.kasa_yenile()

    def kasa_yenile(self):
        try:
            v = sv.kasa_rapor(self.k_bas.get() or "2000-01-01",
                              self.k_bit.get() or "2999-12-31")
        except Exception:
            return
        self.kasa_kpi["giren"].configure(text=tl(v["giren"]))
        self.kasa_kpi["cikan"].configure(text=tl(v["cikan"]))
        self.kasa_kpi["net"].configure(text=tl(v["net"]))
        self.kasa_kpi["bakiye"].configure(text=tl(v["bakiye"]))
        self.kasa_agac.delete(*self.kasa_agac.get_children())
        self.kasa_harita: dict[str, dict] = {}
        for r in reversed(v["satirlar"]):
            et = ("ok",) if r["tur"] == "gelir" else ("gecikmis",)
            kaynak = {"tahsilat": "Tahsilat", "pesin": "Peşin Satış",
                      "manuel": "Manuel"}.get(r["kaynak"], r["kaynak"])
            iid = self.kasa_agac.insert("", "end", tags=et, values=(
                tarih_yaz(r["tarih"]), kaynak, "Gelir" if r["tur"] == "gelir" else "Gider",
                r["kategori"], r["aciklama"], tl(r["tutar"]), tl(r["bakiye"])))
            self.kasa_harita[iid] = r

    def kasa_hareket_dlg(self, tur: str):
        penc = tk.Toplevel(self.kok)
        penc.title("Kasaya Gelir" if tur == "gelir" else "Kasadan Gider")
        penc.configure(bg=PANEL, padx=18, pady=14)
        penc.transient(self.kok)
        penc.grab_set()
        penc.resizable(False, False)
        al = {"tarih": tk.StringVar(value=date.today().isoformat()),
              "tutar": tk.StringVar(),
              "kategori": tk.StringVar(value="Kira" if tur == "gider" else ""),
              "aciklama": tk.StringVar()}
        for k, etiket in (("tarih", "Tarih (AAAA-AA-GG)"), ("tutar", "Tutar *"),
                          ("kategori", "Kategori (Kira, Elektrik...)"),
                          ("aciklama", "Açıklama")):
            ttk.Label(penc, text=etiket, style="Panel.TLabel").pack(
                anchor="w", pady=(8, 0))
            ttk.Entry(penc, textvariable=al[k], width=30).pack(anchor="w")

        def kaydet():
            try:
                sv.kasa_ekle(al["tarih"].get() or date.today().isoformat(), tur,
                             sayi(al["tutar"].get()), al["kategori"].get(),
                             al["aciklama"].get())
            except ValueError as hata:
                messagebox.showwarning("Hata", str(hata), parent=penc)
                return
            penc.destroy()
            self.kasa_yenile()
            self.panel_yenile()
            messagebox.showinfo("Tamam", "Kasa kaydı yapıldı.")

        ttk.Button(penc, text="Kaydet", style="Altin.TButton",
                   command=kaydet).pack(fill="x", pady=(12, 0))

    def kasa_iptal_et(self):
        sec = self.kasa_agac.selection()
        if not sec:
            messagebox.showinfo("Seçim yok", "Önce listeden bir kayıt seçin.")
            return
        r = self.kasa_harita.get(sec[0])
        if not r or r["kaynak"] != "manuel":
            messagebox.showinfo("Otomatik kayıt",
                                "Tahsilat/peşin satış kayıtları buradan iptal edilmez;\n"
                                "ilgili müşteri ekstresinden iptal edin.")
            return
        sebep = simpledialog.askstring("İptal Sebebi", "İptal sebebi:")
        if not (sebep or "").strip():
            return
        try:
            sv.kasa_iptal(r["id"], sebep)
        except ValueError as hata:
            messagebox.showwarning("Hata", str(hata))
            return
        self.kasa_yenile()
        self.panel_yenile()
        messagebox.showinfo("Tamam", "Kasa kaydı iptal edildi (kayıt durur).")

    # ======================================================= RAPORLAR
    def _rapor_kur(self):
        filtre = ttk.Frame(self.tab_rapor)
        filtre.pack(fill="x")
        bugun_str = date.today().isoformat()
        ay_basi = bugun_str[:8] + "01"
        ttk.Label(filtre, text="Başlangıç:").pack(side="left")
        self.r_bas = tk.StringVar(value=ay_basi)
        ttk.Entry(filtre, textvariable=self.r_bas, width=12).pack(side="left", padx=6)
        ttk.Label(filtre, text="Bitiş:").pack(side="left")
        self.r_bit = tk.StringVar(value=bugun_str)
        ttk.Entry(filtre, textvariable=self.r_bit, width=12).pack(side="left", padx=6)
        btn = ttk.Button(filtre, text="Özeti Yenile", command=self.rapor_yenile)
        btn.pack(side="left", padx=10)
        ipucu(btn, "Seçilen aralıktaki satış-tahsilat özetini hesaplar.")
        btn_x = ttk.Button(filtre, text="📊 Excel'e Aktar", command=self.rapor_excel_aktar)
        btn_x.pack(side="left")
        ipucu(btn_x, "Seçili aralığın özetini ve borçlu listesini Excel olarak kaydeder.")

        self.rapor_kpi: dict[str, ttk.Label] = {}
        kpi = ttk.Frame(self.tab_rapor)
        kpi.pack(fill="x", pady=(10, 0))
        for anahtar, etiket in (("veresiye", "Veresiye Satış (TL)"),
                                ("tahsilat", "Tahsilat (TL)"),
                                ("pesin", "Peşin Satış (TL)"),
                                ("net_kasa", "Kasa Net (TL)")):
            kart = ttk.Frame(kpi, style="Panel.TFrame", padding=(14, 12))
            kart.pack(side="left", fill="x", expand=True,
                      padx=(0 if anahtar == "veresiye" else 8, 0))
            ttk.Label(kart, text=etiket, style="KpiEtiket.TLabel").pack(anchor="w")
            self.rapor_kpi[anahtar] = ttk.Label(kart, text="—", style="KpiDeger.TLabel")
            self.rapor_kpi[anahtar].pack(anchor="w")

        ttk.Label(self.tab_rapor, text="En Borçlular (TL değeri, ilk 15)",
                  style="Altin.TLabel").pack(anchor="w", pady=(12, 0))
        self.borclu_agac = self._agac(self.tab_rapor,
                                      ["Müşteri", "Telefon", "TL Borç", "Altın Borç",
                                       "Toplam Değer", "Vade Aşımı (gün)", "Telefon"],
                                      genislikler=(200, 120, 110, 110, 130, 110, 110),
                                      sagalar=(2, 3, 4, 5), yuk=12)
        self.rapor_yenile()

    def rapor_yenile(self):
        bas = self.r_bas.get() or "2000-01-01"
        bit = self.r_bit.get() or "2999-12-31"
        satis = [s for s in sv.satislar(baslangic=bas, bitis=bit, sekl="veresiye")]
        veresiye = sum(float(s["tutar"]) for s in satis if s["para_birimi"] == "tl")
        tahsilat = 0.0
        pesin = 0.0
        try:
            kasa = sv.kasa_rapor(bas, bit)
            tahsilat = sum(float(r["tutar"]) for r in kasa["satirlar"]
                           if r["kaynak"] == "tahsilat")
            pesin = sum(float(r["tutar"]) for r in kasa["satirlar"]
                        if r["kaynak"] == "pesin")
            net = kasa["net"]
        except Exception:
            net = 0.0
        self.rapor_kpi["veresiye"].configure(text=tl(veresiye))
        self.rapor_kpi["tahsilat"].configure(text=tl(tahsilat))
        self.rapor_kpi["pesin"].configure(text=tl(pesin))
        self.rapor_kpi["net_kasa"].configure(text=tl(net))

        self.borclu_agac.delete(*self.borclu_agac.get_children())
        kur = sv.fiyat_getir()
        for m in sv.en_borclular(15):
            deger = float(m["tl_borc"]) + float(m["altin_borc"]) * kur
            self.borclu_agac.insert("", "end", tags=("gecikmis",) if m["gecikme_gun"] else (),
                                    values=(m["ad"], m["telefon"], tl(m["tl_borc"]),
                                            gr(m["altin_borc"]), tl(deger),
                                            int(m.get("gecikme_gun") or 0),
                                            m["telefon"]))

    def rapor_excel_aktar(self):
        bas = self.r_bas.get() or "2000-01-01"
        bit = self.r_bit.get() or "2999-12-31"
        kur = sv.fiyat_getir()
        basliklar = ["Müşteri", "Telefon", "TL Borç", "Altın Borç", "Toplam (TL değeri)",
                     "Vade Aşımı (gün)", "En Eski Vade"]
        satirlar = []
        toplam = 0.0
        for m in sv.musteriler(durum="aktif", sadece_borclu=True):
            deger = float(m["tl_borc"]) + float(m["altin_borc"]) * kur
            toplam += deger
            satirlar.append([m["ad"], m["telefon"], m["tl_borc"], m["altin_borc"],
                             round(deger, 2), int(m.get("gecikme_gun") or 0),
                             m.get("en_eski_vade", "")])
        satirlar.append(["", "", "", "TOPLAM", round(toplam, 2), "", ""])
        excel_kaydet(self.kok, basliklar, satirlar,
                     f"borclu_rapor_{bas}_{bit}.xlsx")

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

    # ============================================== premium: lisans & pin & WhatsApp
    def lisans_butonu(self):
        d = ls.durum()
        if d["lisansli"]:
            messagebox.showinfo("Lisans", "Program lisanslıdır. Teşekkürler!")
            return
        if lisans_penceresi(self.kok, zorunlu=False):
            self.kok.title(self._baslik())
            messagebox.showinfo("Lisans", "Etkinleştirme başarılı. Teşekkürler!")

    def pin_penceresi(self):
        tuz, mevcut_hash = pin_bilgisi()
        penc = tk.Toplevel(self.kok)
        penc.title("PIN Kilidi")
        penc.configure(bg=PANEL, padx=18, pady=14)
        penc.transient(self.kok)
        penc.grab_set()
        penc.resizable(False, False)
        suru = " (kilit şu an AÇIK)" if mevcut_hash else " (kilit şu an KAPALI)"
        ttk.Label(penc, text="PIN Kilidi" + suru, style="Altin.TLabel").pack(anchor="w")
        alan: dict[str, tk.StringVar] = {}
        satirlar = []
        if mevcut_hash:
            satirlar.append(("mevcut", "Mevcut PIN *"))
        satirlar += [("yeni", "Yeni PIN (4-8 haneli) *"),
                     ("tekrar", "Yeni PIN (tekrar) *")]
        for i, (k, etiket) in enumerate(satirlar):
            ttk.Label(penc, text=etiket, style="Panel.TLabel").pack(anchor="w", pady=(8, 0))
            alan[k] = tk.StringVar()
            ttk.Entry(penc, textvariable=alan[k], show="•", width=14).pack(anchor="w")

        def kaydet():
            if mevcut_hash:
                if hashlib.sha256(
                        (tuz + alan["mevcut"].get().strip()).encode("utf-8")
                ).hexdigest() != mevcut_hash:
                    messagebox.showwarning("Hata", "Mevcut PIN hatalı.", parent=penc)
                    return
            yeni = alan["yeni"].get().strip()
            if not (4 <= len(yeni) <= 8) or not yeni.isdigit():
                messagebox.showwarning("Hata", "Yeni PIN 4-8 haneli rakam olmalı.",
                                       parent=penc)
                return
            if yeni != alan["tekrar"].get().strip():
                messagebox.showwarning("Hata", "PIN'ler eşleşmiyor.", parent=penc)
                return
            pin_yaz(yeni)
            penc.destroy()
            messagebox.showinfo("Tamam", "PIN kilidi ayarlandı. Bir sonraki açılışta "
                                         "soranacak.")

        def kaldir():
            if not mevcut_hash:
                return
            if hashlib.sha256(
                    (tuz + alan["mevcut"].get().strip()).encode("utf-8")
            ).hexdigest() != mevcut_hash:
                messagebox.showwarning("Hata", "Mevcut PIN hatalı.", parent=penc)
                return
            with sv.db() as conn:
                sv.ayar_yaz(conn, "pin_tuz", "")
                sv.ayar_yaz(conn, "pin_hash", "")
            penc.destroy()
            messagebox.showinfo("Tamam", "PIN kilidi kaldırıldı.")

        dugme = ttk.Frame(penc)
        dugme.pack(fill="x", pady=(12, 0))
        ttk.Button(dugme, text="Kaydet", style="Altin.TButton", command=kaydet).pack(side="left")
        if mevcut_hash:
            ttk.Button(dugme, text="Kilidi Kaldır", command=kaldir).pack(side="left", padx=8)

    def whatsapp_dlg(self, mid):
        m = sv.musteri_getir(mid)
        tel = tel_99(m.get("telefon", ""))
        gun = int(m.get("gecikme_gun") or 0)
        parcalar = [f"Sayın {m['ad']},",
                    f"{dukkan_adi()} hesabınızda güncel borç:",
                    f"  {tl(m['tl_borc'])}  +  {gr(m['altin_borc'])}"]
        if m.get("en_eski_vade"):
            ek = f" ({gun} gün aşım)" if gun else ""
            parcalar.append(f"En eski işlem vadesi: {tarih_yaz(m['en_eski_vade'])}{ek}")
        parcalar.append("Ödemenizi yaptıysanız bu mesajı dikkate almayın. "
                        "Bilginize teşekkürler.")
        metin = "\n".join(parcalar)

        penc = tk.Toplevel(self.kok)
        penc.title(f"WhatsApp Hatırlatma — {m['ad']}")
        penc.configure(bg=PANEL, padx=16, pady=12)
        penc.transient(self.kok)
        penc.grab_set()
        kutu = tk.Text(penc, width=58, height=9, bg=PANEL2, fg=METIN, borderwidth=0,
                       font=("Segoe UI", 10), wrap="word")
        kutu.pack(fill="both", expand=True)
        kutu.insert("1.0", metin)
        durum = ttk.Label(penc, text=("Telefon: " + (m.get("telefon") or "— YOK —") +
                                      ("" if tel else "   (numara eksik, WhatsApp açılamaz)")),
                          style="Soluk.TLabel", background=PANEL)
        durum.pack(anchor="w", pady=(6, 0))

        dugme = ttk.Frame(penc)
        dugme.pack(fill="x", pady=(8, 0))

        def ac():
            from urllib.parse import quote
            webbrowser.open(f"https://wa.me/{tel}?text={quote(metin)}")

        ttk.Button(dugme, text="📱 WhatsApp'ta Aç", style="Yesil.TButton", command=ac,
                   state=("normal" if tel else "disabled")).pack(side="left")

        def kopyala():
            self.kok.clipboard_clear()
            self.kok.clipboard_append(metin)
            durum.configure(text="Mesaj panoya kopyalandı.")

        ttk.Button(dugme, text="Metni Kopyala", command=kopyala).pack(side="left", padx=8)

    def musterileri_excel_aktar(self):
        basliklar = ["Müşteri", "Telefon", "Kategori", "TL Borç", "Altın Borç",
                     "En Eski Vade", "Vade Aşımı (gün)", "Kredi Limiti",
                     "Ödeme Sözü", "Durum"]
        satirlar = []
        for m in (sv.musteriler(durum="aktif") + sv.musteriler(durum="arsiv")):
            satirlar.append([m["ad"], m["telefon"], m.get("kategori", ""),
                             m["tl_borc"], m["altin_borc"], m.get("en_eski_vade", ""),
                             int(m.get("gecikme_gun") or 0), m["limit_tl"],
                             m.get("sozu_tarih", ""), m["durum"]])
        excel_kaydet(self.kok, basliklar, satirlar,
                     f"musteriler_{date.today().isoformat()}.xlsx")

    def _ekstre_excel(self, m, e):
        basliklar = ["Tarih", "Açıklama", "Borç", "Tahsilat", "TL Bakiye",
                     "Altın Bakiye"]
        satirlar = [[r["tarih"], r["aciklama"], r["borc"], r["tahsilat"],
                     r["tl_bakiye"], r["altin_bakiye"]] for r in e["satirlar"]]
        b = e["bakiye"]
        satirlar.append(["", "GÜNCEL BAKİYE", "", "", b["tl_borc"], b["altin_borc"]])
        excel_kaydet(self.kok, basliklar, satirlar,
                     f"ekstre_{m['ad'].replace(' ', '_')}_{date.today().isoformat()}.xlsx")

    # ================================================================ kapat
    def kapat(self):
        self.yedekci.durdur()
        self.kok.destroy()


# --------------------------------------------------------------------------- #
# Yardımcılar: telefon / dükkan adı / PIN / Excel
# --------------------------------------------------------------------------- #
def tel_99(tel: str) -> str:
    """Telefonu WhatsApp (wa.me) biçimine çevirir: 0532... → 90532..."""
    d = "".join(ch for ch in (tel or "") if ch.isdigit())
    if d.startswith("0"):
        d = "90" + d[1:]
    elif len(d) == 10 and not d.startswith("90"):
        d = "90" + d
    return d if len(d) >= 10 else ""


def dukkan_adi() -> str:
    try:
        conn = vdb.baglanti()
        satir = conn.execute("SELECT deger FROM ayarlar WHERE anahtar='dukkan_adi'").fetchone()
        conn.close()
        if satir and str(satir[0]).strip():
            return str(satir[0])
    except Exception:
        pass
    return "HACILAR KUYUMCULUK"


def pin_bilgisi() -> tuple[str, str]:
    try:
        conn = vdb.baglanti()
        satirlar = conn.execute(
            "SELECT anahtar, deger FROM ayarlar WHERE anahtar IN ('pin_tuz','pin_hash')"
        ).fetchall()
        conn.close()
        d = {r[0]: str(r[1]) for r in satirlar}
        return d.get("pin_tuz", ""), d.get("pin_hash", "")
    except Exception:
        return "", ""


def pin_yaz(pin: str) -> None:
    tuz = secrets.token_hex(16)
    h = hashlib.sha256((tuz + pin).encode("utf-8")).hexdigest()
    try:
        conn = vdb.baglanti()
        for k, v in (("pin_tuz", tuz), ("pin_hash", h)):
            conn.execute("INSERT INTO ayarlar(anahtar, deger) VALUES (?, ?) "
                         "ON CONFLICT(anahtar) DO UPDATE SET deger=excluded.deger",
                         (k, v))
        conn.commit()
        conn.close()
    except Exception:
        pass


def pin_sor(kok: tk.Tk) -> bool:
    """PIN ayarlıysa açılışta sorar; 3 hakte kapanır. PIN yoksa doğrudan geçer."""
    tuz, h = pin_bilgisi()
    if not h:
        return True
    penc = tk.Toplevel(kok)
    penc.title("PIN Kilidi")
    penc.configure(bg=ARKA, padx=20, pady=16)
    penc.resizable(False, False)
    penc.grab_set()
    tk.Label(penc, text="🔒 HACILAR KUYUMCULUK", bg=ARKA, fg=ALTIN,
             font=("Segoe UI", 12, "bold")).pack(anchor="w")
    tk.Label(penc, text="Programı açmak için PIN girin.", bg=ARKA, fg=SOLUK).pack(
        anchor="w", pady=(2, 8))
    girdi = tk.StringVar()
    alan = tk.Entry(penc, textvariable=girdi, show="•", width=16,
                    bg=PANEL2, fg=METIN, insertbackground=METIN, borderwidth=0)
    alan.pack(anchor="w", ipady=4, padx=(0, 8))
    bilgi = tk.Label(penc, text="", bg=ARKA, fg=SOLUK)
    bilgi.pack(anchor="w", pady=(6, 0))
    sonuc = [False]
    hak = [3]

    def dene():
        pin = girdi.get().strip()
        if hashlib.sha256((tuz + pin).encode("utf-8")).hexdigest() == h:
            sonuc[0] = True
            penc.destroy()
            return
        hak[0] -= 1
        if hak[0] <= 0:
            penc.destroy()
            return
        bilgi.configure(text=f"PIN hatalı — {hak[0]} hakkınız kaldı.", fg=KIRMIZI)
        girdi.set("")
        alan.focus_set()

    tk.Button(penc, text="Aç", bg=ALTIN, fg="14161A", borderwidth=0,
              activebackground=ALTIN_ACIK, font=("Segoe UI", 9, "bold"),
              command=dene).pack(anchor="w", pady=(10, 0))
    alan.bind("<Return>", lambda _e: dene())
    alan.focus_set()
    penc.wait_window()
    return sonuc[0]


def excel_kaydet(kok, basliklar, satirlar, onerilen) -> None:
    """Listeyi .xlsx (openpyxl) ya da CSV olarak kaydeder."""
    dosya = filedialog.asksaveasfilename(
        defaultextension=".xlsx", parent=kok, initialfile=onerilen,
        filetypes=[("Excel çalışma kitabı", "*.xlsx"), ("CSV (Excel uyumlu)", "*.csv")])
    if not dosya:
        return
    try:
        if dosya.lower().endswith(".csv"):
            import csv
            with open(dosya, "w", encoding="utf-8-sig", newline="") as f:
                yaz = csv.writer(f)
                yaz.writerow(basliklar)
                yaz.writerows(satirlar)
        else:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill
            wb = Workbook()
            sayfa = wb.active
            sayfa.title = "Rapor"
            sayfa.append(list(basliklar))
            for s in satirlar:
                sayfa.append(list(s))
            for hucre in sayfa[1]:
                hucre.font = Font(bold=True, color="14161A")
                hucre.fill = PatternFill("solid", fgColor="D4AF37")
            for i in range(1, len(basliklar) + 1):
                hucreler = [len(str(basliklar[i - 1]))] + [
                    len(str(satir[i - 1])) for satir in satirlar[:60]]
                sayfa.column_dimensions[sayfa.cell(row=1, column=i).column_letter].width = \
                    min(max(hucreler) + 4, 44)
            sayfa.freeze_panes = "A2"
            wb.save(dosya)
        messagebox.showinfo("Kaydedildi", "Dosya kaydedildi:\n" + dosya, parent=kok)
    except Exception as hata:
        messagebox.showwarning("Hata", f"Dosya yazılamadı:\n{hata}", parent=kok)


def lisans_penceresi(kok: tk.Tk, zorunlu: bool) -> bool:
    """Anahtar etkinleştirme penceresi. Geçerli anahtar → True."""
    if zorunlu:
        kok.withdraw()
    penc = tk.Toplevel(kok)
    penc.title("Lisans Etkinleştirme — HACILAR KUYUMCULUK")
    penc.configure(bg=ARKA, padx=24, pady=18)
    penc.resizable(False, False)
    penc.grab_set()
    d = ls.durum()
    tk.Label(penc, text="◆ HACILAR KUYUMCULUK", bg=ARKA, fg=ALTIN,
             font=("Segoe UI", 13, "bold")).pack(anchor="w")
    if d["lisansli"]:
        durum_metni = "Program lisanslı. Teşekkürler!"
    elif d["demo_aktif"]:
        durum_metni = f"Demo sürüm: {d['kalan_yazi']}. İsterseniz şimdi anahtar girebilirsiniz."
    else:
        durum_metni = "Demo süresi doldu. Devam etmek için lisans anahtarı gerekli."
    tk.Label(penc, text=durum_metni, bg=ARKA, fg=METIN, justify="left").pack(
        anchor="w", pady=(4, 10))
    if d["not"]:
        tk.Label(penc, text=d["not"], bg=ARKA, fg=UYARI).pack(anchor="w")
    girdi = tk.StringVar()
    alan = tk.Entry(penc, textvariable=girdi, width=32, font=("Consolas", 11),
                    bg=PANEL2, fg=METIN, insertbackground=METIN, borderwidth=0)
    alan.pack(anchor="w", ipady=5, pady=(0, 4))
    tk.Label(penc, text="Örnek: HACILAR-ABCDE-FGHJK-LMNPR-STUVX", bg=ARKA,
             fg=SOLUK).pack(anchor="w")
    hata = tk.Label(penc, text="", bg=ARKA, fg=SOLUK)
    hata.pack(anchor="w", pady=(4, 0))
    sonuc = [False]

    def etkinlestir():
        if ls.etkinlestir(girdi.get()):
            sonuc[0] = True
            penc.destroy()
        else:
            hata.configure(text="Geçersiz anahtar. Kontrol edip tekrar deneyin.",
                           fg=KIRMIZI)

    dugme = ttk.Frame(penc)
    dugme.pack(fill="x", pady=(12, 0))
    ttk.Button(dugme, text="Etkinleştir", style="Altin.TButton",
               command=etkinlestir).pack(side="left")
    alan.bind("<Return>", lambda _e: etkinlestir())
    if not zorunlu:
        ttk.Button(dugme, text="Kapat", command=penc.destroy).pack(side="left", padx=8)
    tk.Label(penc, text=ls.BAYI_METNI, bg=ARKA, fg=SOLUK).pack(anchor="w", pady=(10, 0))
    alan.focus_set()
    penc.wait_window()
    return sonuc[0]


def main():
    vdb.init_db()   # veritabanı yoksa oluştur (web sürümü olmadan da çalışsın)
    try:            # eski varsayılan adı taşıyan DB'leri yeni markaya geçir
        conn = vdb.baglanti()
        satir = conn.execute(
            "SELECT deger FROM ayarlar WHERE anahtar='dukkan_adi'").fetchone()
        if satir and str(satir[0]).strip() in ("", "Kuyumcu"):
            conn.execute("UPDATE ayarlar SET deger='HACILAR KUYUMCULUK' "
                         "WHERE anahtar='dukkan_adi'")
            conn.commit()
        conn.close()
    except Exception:
        pass

    # --- demo / lisans kapısı ------------------------------------------- #
    ls.calistir()
    d = ls.durum()
    kok = tk.Tk()
    kok.withdraw()
    while not d["tam_erisim"]:
        basarili = lisans_penceresi(kok, zorunlu=True)
        d = ls.durum()
        if not basarili and not d["tam_erisim"]:
            kok.destroy()
            return
    # --- PIN kilidi ------------------------------------------------------ #
    if not pin_sor(kok):
        kok.destroy()
        return
    kok.deiconify()
    Uygulama(kok)
    kok.mainloop()


if __name__ == "__main__":
    main()
