"""HACILAR KUYUMCULUK â€” uzaktan gÃ¼ncelleme modÃ¼lÃ¼.

MantÄ±k:
- SÃ¼rÃ¼mler ayrÄ±, Ã–ZEL bir depoda (RetroNyym/hacilar-guncelleme) GitHub
  Release olarak yayÄ±nlanÄ±r. Ana kod deposu da Ã¶zeldir.
- Ã–zel depodan okuma iÃ§in salt-okunur fine-grained token gerekir: token,
  guncelleme_anahtari.txt iÃ§inde gelir ve derlerken exe'ye gÃ¶mÃ¼lÃ¼r. Token
  YALNIZCA bu depoyu okuyabilir; kod deponuza dokunamaz.
- Program her aÃ§Ä±lÄ±ÅŸta en son sÃ¼rÃ¼mÃ¼ kontrol eder (internet yoksa veya
  kontrol baÅŸarÄ±sÄ±zsa program normal aÃ§Ä±lÄ±r â€” hiÃ§bir zaman takÄ±lmaz).
- YayÄ±nda daha yeni bir sÃ¼rÃ¼m varsa gÃ¼ncelleme MECBURÄ°DÄ°R: kullanÄ±cÄ± ya
  gÃ¼nceller ya da programÄ± kapatÄ±r.

Bayi akÄ±ÅŸÄ± (sahip):
  GuncellemeYayinla.exe  â†’  sÃ¼rÃ¼m no + notlarÄ± gir, exe'yi seÃ§; hepsi bu.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request

SURUM = "1.3.0"                       # bu programÄ±n sÃ¼rÃ¼mÃ¼
DEPO = "RetroNyym/hacilar-guncelleme"  # Ã–ZEL gÃ¼ncelleme deposu
EXE_ADI = "HacilarKuyumculuk.exe"
ZAMAN_ASIMI = 8                        # saniye
ANAHTAR_DOSYASI = "guncelleme_anahtari.txt"   # okuma yetkili token (depoya girilmez)


def _token() -> str:
    """Ã–zel depodan indirme iÃ§in salt-okunur eriÅŸim anahtarÄ±.

    Anahtar, proje kÃ¶kÃ¼ndeki guncelleme_anahtari.txt iÃ§indedir ve derlerken
    exe'nin iÃ§ine gÃ¶mÃ¼lÃ¼r (depoya commit EDÄ°LMEZ). Sadece bu depoyu okuma
    yetkili fine-grained token kullanÄ±n.
    """
    kokler = [getattr(sys, "_MEIPASS", ""),
              os.path.dirname(os.path.abspath(__file__))]
    for kok in kokler:
        if not kok:
            continue
        yol = os.path.join(kok, ANAHTAR_DOSYASI)
        if os.path.exists(yol):
            try:
                with open(yol, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except OSError:
                return ""
    return ""


def _reg():
    try:
        import winreg
        return winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                r"Software\HacilarKuyumculuk")
    except Exception:
        return None


def kurulum_yaz(surum: str) -> None:
    """Ä°ndirilen sÃ¼rÃ¼mÃ¼n yÃ¼klendiÄŸini iÅŸaretler (gÃ¼ncelleme dÃ¶ngÃ¼sÃ¼nÃ¼ kÄ±rar)."""
    k = _reg()
    if k is not None:
        try:
            import winreg
            winreg.SetValueEx(k, "KuruluSurum", 0, winreg.REG_SZ, surum)
        except OSError:
            pass


def kurulum_oku() -> str:
    k = _reg()
    if k is None:
        return ""
    try:
        import winreg
        return str(winreg.QueryValueEx(k, "KuruluSurum")[0] or "")
    except OSError:
        return ""


# --------------------------------------------------------------------------- #
# SÃ¼rÃ¼m karÅŸÄ±laÅŸtÄ±rma (1.2.10 > 1.2.9 gibi)
# --------------------------------------------------------------------------- #
def _parcala(surum: str) -> tuple[int, ...]:
    sayilar = re.findall(r"\d+", surum or "")
    return tuple(int(x) for x in sayilar) or (0,)


def surum_yeni_mi(aday: str, mevcut: str) -> bool:
    return _parcala(aday) > _parcala(mevcut)


# --------------------------------------------------------------------------- #
# Son sÃ¼rÃ¼mÃ¼ sorgula
# --------------------------------------------------------------------------- #
def _basliklar() -> dict:
    b = {
        "User-Agent": "HacilarKuyumculuk",
        "Accept": "application/vnd.github+json",
    }
    t = _token()
    if t:
        b["Authorization"] = f"Bearer {t}"
    return b


def en_yeni_surum() -> dict | None:
    """GitHub API'den son release'i okur.

    DÃ¶nen: {'surum': '1.1.0', 'exe_url': ..., 'boyut': int, 'notlar': str}
    Bilgi alÄ±namazsa (internet yok, anahtar yok, depo boÅŸ, API hatasÄ±) -> None.
    """
    url = f"https://api.github.com/repos/{DEPO}/releases/latest"
    try:
        istek = urllib.request.Request(url, headers=_basliklar())
        with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as cevap:
            veri = json.loads(cevap.read().decode("utf-8"))
    except Exception:
        return None

    tag = str(veri.get("tag_name") or "").strip().lstrip("vV")
    if not tag:
        return None
    exe_url = ""
    boyut = 0
    for varlik in veri.get("assets", []):
        if str(varlik.get("name", "")).lower() == EXE_ADI.lower():
            exe_url = varlik.get("url", "") or varlik.get("browser_download_url", "")
            boyut = int(varlik.get("size") or 0)
            break
    if not exe_url:
        return None
    return {
        "surum": tag,
        "exe_url": exe_url,
        "boyut": boyut,
        "notlar": str(veri.get("body") or "").strip(),
        "yayin_tarihi": str(veri.get("published_at") or ""),
    }


def kontrol() -> dict | None:
    """Yeni sÃ¼rÃ¼m varsa bilgini dÃ¶ndÃ¼rÃ¼r; yoksa/hata ise None."""
    bilgi = en_yeni_surum()
    if not bilgi:
        return None
    if bilgi["surum"] == kurulum_oku():
        return None   # bu yayÄ±n zaten bu makineye kurulmuÅŸ
    if surum_yeni_mi(bilgi["surum"], SURUM):
        return bilgi
    return None


# --------------------------------------------------------------------------- #
# Ä°ndirme + kendini deÄŸiÅŸtirme
# --------------------------------------------------------------------------- #
class _YetkisizYonlendirme(urllib.request.HTTPRedirectHandler):
    """GitHub, Ã¶zel depo varlÄ±ÄŸÄ±nÄ± imzalÄ± bir depolama adresine yÃ¶nlendirir.
    Yetki baÅŸlÄ±ÄŸÄ± bu Ã¼Ã§Ã¼ncÃ¼ taraf sunucuya gÃ¶nderilmez."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        yeni = super().redirect_request(req, fp, code, msg, headers, newurl)
        if yeni is not None:
            yeni.headers.pop("Authorization", None)
            yeni.unredirected_hdrs.pop("Authorization", None)
        return yeni


def indir(url: str, hedef: str, ilerleme=None) -> str:
    """Exe'yi indirir; boyut kontrolÃ¼ yapar; hedef yolunu dÃ¶ndÃ¼rÃ¼r."""
    os.makedirs(os.path.dirname(hedef), exist_ok=True)
    basliklar = _basliklar()
    if "api.github.com" in url:
        basliklar["Accept"] = "application/octet-stream"
    istek = urllib.request.Request(url, headers=basliklar)
    acici = urllib.request.build_opener(_YetkisizYonlendirme)
    with acici.open(istek, timeout=120) as cevap:
        toplam = int(cevap.headers.get("Content-Length") or 0) or 0
        alinan = 0
        blok = 64 * 1024
        with open(hedef, "wb") as f:
            while True:
                parca = cevap.read(blok)
                if not parca:
                    break
                f.write(parca)
                alinan += len(parca)
                if ilerleme and toplam:
                    ilerleme(alinan, toplam)
    if alinan < 1024 * 1024:   # 1 MB'den kÃ¼Ã§Ã¼k exe asla saÄŸlÄ±klÄ± olamaz
        raise RuntimeError("Ä°ndirilen dosya tamamlanamadÄ± (Ã§ok kÃ¼Ã§Ã¼k).")
    return hedef


def dogrula(dosya: str, beklenen_boyut: int = 0) -> bool:
    try:
        boyut = os.path.getsize(dosya)
    except OSError:
        return False
    if beklenen_boyut and boyut != beklenen_boyut:
        return False
    return boyut > 1024 * 1024


def uygula(yeni_dosya: str) -> None:
    """Ã‡alÄ±ÅŸan programÄ±n kapanmasÄ±ndan sonra yeni exe'yi yerine koyup aÃ§ar.

    Toplu iÅŸ (bat) dosyasÄ± ile: kapanmayÄ± bekler, eskiyi yedeÄŸe alÄ±r,
    yeniyi taÅŸÄ±r, programÄ± yeniden baÅŸlatÄ±r.
    """
    mevcut = os.path.abspath(sys.executable if getattr(sys, "frozen", False)
                             else __file__)
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Kaynak koddan Ã§alÄ±ÅŸÄ±rken gÃ¼ncelleme uygulanmaz.")
    if any(c in mevcut + yeni_dosya for c in '"%^&|<>!'):
        raise RuntimeError("Program yolunda gÃ¼ncellemeyi engelleyen karakter var.")
    bat_yolu = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")),
                            "hacilar_guncelle.bat")
    icerik = f"""@echo off
timeout /t 4 /nobreak >nul
if exist "{mevcut}.eski" del "{mevcut}.eski"
move /y "{mevcut}" "{mevcut}.eski"
move /y "{yeni_dosya}" "{mevcut}"
start "" "{mevcut}"
del "%~f0"
"""
    with open(bat_yolu, "w", encoding="utf-8") as f:
        f.write(icerik)
    subprocess.Popen(["cmd", "/c", bat_yolu], close_fds=True,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def sifirla():
    """(Bilgi) bayi aracÄ±: yayÄ±n yapÄ±lan depoda yeni release oluÅŸturur."""
    raise NotImplementedError("Bu iÅŸ GuncellemeYayinla.exe'ye aittir.")
