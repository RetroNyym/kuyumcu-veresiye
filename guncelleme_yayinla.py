r"""HACILAR KUYUMCULUK — BAYİ GÜNCELLEME YAYINLAMA (SADECE SAHİP KULLANIR).

Yeni sürümü müşterilere dağıtır:
    GuncellemeYayinla.exe                       (sorularla)
    GuncellemeYayinla.exe --surum 1.1.0 --dosya dist\HacilarKuyumculuk.exe --not "..."
Tüm müşterilerin programı açılışta MECBURİ olarak güncellenir.

Bu program müşteriye verilmez; yalnızca program sahibine aittir.
GitHub CLI (gh) kurulu ve hesaplı olmalıdır:  gh auth status
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

DEPO = "RetroNyym/hacilar-guncelleme"
EXE_ADI = "HacilarKuyumculuk.exe"


def arg(al: str, sor: str, varsayilan: str = "") -> str:
    if al in sys.argv:
        return sys.argv[sys.argv.index(al) + 1]
    if not sys.stdin or not sys.stdin.isatty():
        return varsayilan
    deger = input(sor).strip()
    return deger or varsayilan


def main() -> None:
    print()
    print("=" * 62)
    print("   HACILAR KUYUMCULUK — GÜNCELLEME YAYINLAMA (bayi)")
    print("=" * 62)

    surum = arg("--surum", "Yeni sürüm numarası (ör. 1.1.0): ")
    if not surum:
        print("HATA: sürüm numarası gerekli."); dur = input(); sys.exit(1)
    dosya = arg("--dosya", f"Yüklenecek exe yolu [{os.path.join('dist', EXE_ADI)}]: ",
                os.path.join("dist", EXE_ADI))
    notlar = arg("--not", "Sürüm notları (müşteriye görünür): ",
                 "İyileştirmeler ve düzeltmeler.")

    dosya = os.path.abspath(dosya)
    if not os.path.isfile(dosya):
        print(f"HATA: dosya yok: {dosya}"); input(); sys.exit(1)
    boyut = os.path.getsize(dosya) / (1024 * 1024)

    print()
    print(f"   Sürüm : v{surum}")
    print(f"   Dosya : {dosya}  ({boyut:.1f} MB)")
    print(f"   Notlar: {notlar}")
    print()
    onay = arg("--evet", "Yayınlansın mı? (E/H): ").lower()
    if onay not in ("e", "evet", "y"):
        print("İptal edildi."); input(); sys.exit(0)

    etiket = f"v{surum}"
    cmd = ["gh", "release", "create", etiket, dosya,
           "--repo", DEPO, "--title", f"HACILAR KUYUMCULUK v{surum}",
           "--notes", notlar]
    print("GitHub'a yükleniyor...")
    sonuc = subprocess.run(cmd, capture_output=True, text=True)
    if sonuc.returncode != 0:
        print()
        print("HATA: yayınlanamadı.")
        print(sonuc.stderr.strip() or sonuc.stdout.strip())
        print("Aynı sürüm tekrar yayınlanamayabilir; sürüm no artırın veya:")
        print(f"  gh release delete {etiket} --repo {DEPO} --yes")
        input(); sys.exit(1)

    print()
    print("=" * 62)
    print(f"   TAMAM — v{surum} yayında: {sonuc.stdout.strip()}")
    print("   Müşterilerin programı açılışta MECBURİ güncellenecek.")
    print("=" * 62)
    try:
        input("   Kapatmak için Enter...")
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main()
