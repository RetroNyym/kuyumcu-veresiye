"""HACILAR KUYUMCULUK — Veresiye Takibi (tkinter masaüstü arayüzü).

Tek amaç: veresiye borçları ve takibi.
- Borçlar sayfası: isim yaz → borcu gör; tüm borçlular tek listede, en altta toplam.
- İşlemler: borç ekle, tahsilat al, ekstre (TXT/Excel), WhatsApp hatırlatma.
- Yedek sekmesi: saatlik/günlük/aylık otomatik yedek + tam JSON yedeği.
- PIN kilidi ve 1 günlük demo + lisans anahtarı korunur.

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

SAHIBI = "Mehmet Avkıran"          # program sahibi — alt bar ve selamlamada görünür


def selamlama(saat: int | None = None) -> tuple[str, str]:
    """PC saatine göre selam: her vakit için uygun karşılama."""
    saat = datetime.now().hour if saat is None else saat
    if 5 <= saat < 12:
        return "☀️", "Günaydın"
    if 12 <= saat < 17:
        return "🌤️", "Tünaydın"
    if 17 <= saat < 22:
        return "🌆", "İyi akşamlar"
    return "🌙", "İyi geceler"


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
        # program sahibi alt bilgi çubuğu (pencerenin en altında)
        alt = ttk.Frame(self.kok, style="Panel.TFrame", padding=(18, 6))
        alt.pack(side="bottom", fill="x")
        ttk.Label(alt, text=f"© {datetime.now().year} {SAHIBI} · HACILAR KUYUMCULUK",
                  style="Soluk.TLabel", background=PANEL).pack(side="left")
        ttk.Label(alt, text="Veresiye Takibi", style="Soluk.TLabel",
                  background=PANEL).pack(side="right")
        self._sekmeler()
        self.panel_yenile()
        self._selam_dongu()
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
        selam_satiri = ttk.Frame(sol, style="Panel.TFrame")
        selam_satiri.pack(anchor="w", pady=(3, 0))
        self.selam_soz_etiketi = tk.Label(selam_satiri, text="", bg=ALTIN,
                                          fg="#14161a", font=("Segoe UI", 10, "bold"),
                                          padx=10, pady=3)
        self.selam_soz_etiketi.pack(side="left")
        self.selam_ad_etiketi = tk.Label(selam_satiri, text="", bg=PANEL, fg=ALTIN,
                                         font=("Segoe UI", 13, "bold"))
        self.selam_ad_etiketi.pack(side="left", padx=(9, 0))
        self._selam_yaz()
        self.fiyat_etiketi = ttk.Label(sol, text="", style="Soluk.TLabel", background=PANEL)
        self.fiyat_etiketi.pack(anchor="w", pady=(3, 0))

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

    # --------------------------------------------- selamlama + alt bilgi bar #
    def _selam_yaz(self):
        ikon, soz = selamlama()
        self.selam_soz_etiketi.configure(text=f"{ikon} {soz}")
        self.selam_ad_etiketi.configure(text=SAHIBI)

    def _selam_dongu(self):
        """PC saati değiştikçe selamı tazeler (her vakit için doğru karşılama)."""
        self._selam_yaz()
        self.kok.after(60_000, self._selam_dongu)

    # ------------------------------------------------------------ sekmeler #
    def _sekmeler(self):
        self.notlar_ck = ttk.Notebook(self.kok)
        self.notlar_ck.pack(fill="both", expand=True, padx=8, pady=(4, 10))

        self.tab_panel = ttk.Frame(self.notlar_ck, padding=10)
        self.tab_yedek = ttk.Frame(self.notlar_ck, padding=10)

        self.notlar_ck.add(self.tab_panel, text="  🏠 Borçlar  ")
        self.notlar_ck.add(self.tab_yedek, text="  💾 Yedek  ")

        self.notlar_ck.bind("<<NotebookTabChanged>>", self._sekme_degisti)
        self._panel_kur()
        self._yedek_kur()

    def _sekme_degisti(self, _e=None):
        secili = self.notlar_ck.select()
        if secili == str(self.tab_panel):
            self.panel_yenile()
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
        agac.tag_configure("borc", foreground=KIRMIZI)
        agac.tag_configure("pesin", foreground=UYARI)
        agac.tag_configure("ok", foreground=YESIL)
        agac.tag_configure("soluk", foreground=SOLUK)
        agac.tag_configure("cift", background="#191c21")
        kay = ttk.Scrollbar(sarici, orient="vertical", command=agac.yview)
        agac.configure(yscrollcommand=kay.set)
        agac.pack(side="left", fill="both", expand=True)
        kay.pack(side="right", fill="y")
        return agac

    # ================================================================ BORCLAR
    def _panel_kur(self):
        # --- buyuk arama alani: isim yaz -> borcu gor --------------------- #
        ara = ttk.Frame(self.tab_panel)
        ara.pack(fill="x")
        ttk.Label(ara, text="🔎", font=("Segoe UI", 15)).pack(side="left")
        self.m_ara = tk.StringVar()
        girdi = ttk.Entry(ara, textvariable=self.m_ara, font=("Segoe UI", 13), width=32)
        girdi.pack(side="left", padx=8, ipady=6)
        girdi.bind("<KeyRelease>", lambda _e: self.panel_yenile())
        ipucu(girdi, "Müşteri adı veya telefon yazın —\nborcu anında görürsünüz.")
        self.m_borclu = tk.BooleanVar(value=True)
        cb = ttk.Checkbutton(ara, text="Sadece borçlular", variable=self.m_borclu,
                             command=self.panel_yenile)
        cb.pack(side="left", padx=12)
        ipucu(cb, "İşareti kaldırırsanız borcu olmayanlar\ndahil tüm müşteriler listelenir.")

        # --- islem dugmeleri ---------------------------------------------- #
        dugme = ttk.Frame(self.tab_panel)
        dugme.pack(fill="x", pady=8)
        for yazi, komut, stil, aciklama in (
            ("+ Yeni Müşteri", self.musteri_dlg_yeni, "Altin.TButton",
             "Yeni müşteri kartı açar: ad, telefon,\nkredi limiti, ödeme sözü, not."),
            ("💰 Borç Ekle", lambda: self._m_semma(self.satis_dlg), None,
             "Seçili müşteriye veresiye borç işler\n(tarih, tutar, vade)."),
            ("✅ Tahsilat Al", lambda: self._m_semma(self.tahsilat_dlg), "Yesil.TButton",
             "Seçili müşteriden ödeme alır;\nborç en eski satıştan başlayarak kapanır."),
            ("✎ Düzenle", lambda: self._m_semma(self.musteri_dlg_duzenle), None,
             "Seçili müşterinin bilgilerini günceller."),
            ("📄 Ekstre", lambda: self._m_semma(self.ekstre_penceresi), None,
             "Seçili müşterinin hesap dökümünü açar\n(TXT veya Excel olarak kaydedilir)."),
            ("📱 WhatsApp", lambda: self._m_semma(self.whatsapp_dlg), None,
             "Borç hatırlatma mesajı üretir;\nWhatsApp\'ta açar veya panoya kopyalar."),
            ("📊 Excel\'e Aktar", self.musterileri_excel_aktar, None,
             "Borçlu listesini toplamlarıyla birlikte\nExcel (.xlsx) olarak kaydeder."),
            ("Arşivle / Geri Al", self.musteri_durum_degistir, None,
             "Seçili müşteriyi arşive kaldırır (silinmez)\nveya listeye geri alır."),
        ):
            btn = ttk.Button(dugme, text=yazi, style=stil or "TButton", command=komut)
            btn.pack(side="left", padx=(0, 7))
            ipucu(btn, aciklama)

        # --- en altta toplam cubugu (her zaman gorunur) -------------------- #
        self.toplam_cubugu = ttk.Frame(self.tab_panel, style="Panel.TFrame",
                                       padding=(16, 12))
        self.toplam_cubugu.pack(side="bottom", fill="x", pady=(8, 0))
        self.toplam_etiket = ttk.Label(self.toplam_cubugu, text="—",
                                       style="KpiDeger.TLabel")
        self.toplam_etiket.pack(side="left")
        ipucu(self.toplam_etiket, "Listedeki borçların toplamı:\nTL borç + altın borcun "
                                  "güncel gram\nfiyatındaki değeri.")
        self.sayi_etiket = ttk.Label(self.toplam_cubugu, text="", style="Soluk.TLabel",
                                     background=PANEL)
        self.sayi_etiket.pack(side="right")

        # --- borc listesi --------------------------------------------------- #
        self.borc_agac = self._agac(self.tab_panel,
                                    ["Müşteri", "Telefon", "TL Borç", "Altın Borç",
                                     "Toplam (TL değeri)", "En Eski Vade", "Aşım (gün)"],
                                    genislikler=(215, 120, 110, 110, 140, 115, 95),
                                    sagalar=(2, 3, 4, 6), yuk=16)
        self.borc_agac.bind("<<TreeviewSelect>>", self._m_sec_degisti)
        self.borc_agac.bind("<Double-1>",
                            lambda _e: self._m_semma(self.ekstre_penceresi))
        self.panel_yenile()

    def musteriler_yenile(self):
        """Eski isim uyumlulugu: listeyi yeniden doldurur."""
        self.panel_yenile()

    def panel_yenile(self):
        q = self.m_ara.get()
        self.borc_agac.delete(*self.borc_agac.get_children())
        aktif = sv.musteriler(q=q)
        arsiv = sv.musteriler(q=q, durum="arsiv")
        if self.m_borclu.get():
            aktif = [m for m in aktif if m["borclu"]]
        kur = sv.fiyat_getir()
        toplam_tl = toplam_gr = toplam_deger = 0.0
        borclu_sayi = 0
        for i, m in enumerate(aktif):
            deger = float(m["tl_borc"]) + float(m["altin_borc"]) * kur
            toplam_tl += float(m["tl_borc"])
            toplam_gr += float(m["altin_borc"])
            toplam_deger += deger
            gun = int(m.get("gecikme_gun") or 0)
            if m["borclu"]:
                borclu_sayi += 1
            et = (("gecikmis",) if gun > 0 else ("borc",) if m["borclu"] else ("ok",))
            if i % 2:
                et = et + ("cift",)
            vade = (tarih_yaz(m.get("en_eski_vade", ""))
                    if m.get("en_eski_vade") else "—")
            self.borc_agac.insert("", "end", iid=str(m["id"]), tags=et, values=(
                m["ad"], m["telefon"], tl(m["tl_borc"]), gr(m["altin_borc"]),
                tl(deger), vade, gun if gun > 0 else ""))
        for i, m in enumerate(arsiv):
            et = ("soluk",) + (("cift",) if i % 2 else ())
            self.borc_agac.insert("", "end", iid=str(m["id"]), tags=et, values=(
                m["ad"] + "  (arşiv)", m["telefon"], tl(m["tl_borc"]),
                gr(m["altin_borc"]), tl(float(m["tl_borc"])
                                        + float(m["altin_borc"]) * kur),
                "—", ""))
        self.fiyat_etiketi.configure(text=f"Güncel gram fiyatı: {tl(kur)}")
        self.toplam_etiket.configure(
            text=f"TOPLAM ALACAK:    {tl(toplam_tl)}  +  {gr(toplam_gr)}"
                 f"    =    {tl(toplam_deger)}")
        self.sayi_etiket.configure(
            text=f"{borclu_sayi} borçlu / {len(aktif)} müşteri listeleniyor")

    def _m_sec_degisti(self, _e=None):
        sec = self.borc_agac.selection()
        if sec:
            iid = sec[0]
            if iid.isdigit():
                self.secili_musteri = int(iid)
            else:
                self.secili_musteri = None

    def _m_semma(self, fonks):
        if self.secili_musteri is None:
            messagebox.showinfo("Seçim yok", "Önce listeden bir müşteri seçin.")
            return
        fonks(self.secili_musteri)

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
        basliklar = ["Müşteri", "Telefon", "TL Borç", "Altın Borç", "Toplam (TL değeri)",
                     "En Eski Vade", "Vade Aşımı (gün)", "Kredi Limiti", "Durum"]
        kur = sv.fiyat_getir()
        satirlar = []
        toplam_tl = toplam_gr = toplam_deger = 0.0
        for m in (sv.musteriler(durum="aktif") + sv.musteriler(durum="arsiv")):
            deger = float(m["tl_borc"]) + float(m["altin_borc"]) * kur
            toplam_tl += float(m["tl_borc"])
            toplam_gr += float(m["altin_borc"])
            toplam_deger += deger
            satirlar.append([m["ad"], m["telefon"], m["tl_borc"], m["altin_borc"],
                             round(deger, 2), m.get("en_eski_vade", ""),
                             int(m.get("gecikme_gun") or 0), m["limit_tl"],
                             m["durum"]])
        satirlar.append(["", "", "", "", "", "", "", "", ""])
        satirlar.append(["TOPLAM", "", toplam_tl, toplam_gr, round(toplam_deger, 2),
                         "", "", "", ""])
        excel_kaydet(self.kok, basliklar, satirlar,
                     f"borclar_{date.today().isoformat()}.xlsx")

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
