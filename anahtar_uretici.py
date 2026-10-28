"""HACILAR KUYUMCULUK — BAYİ ANAHTAR ÜRETİCİ (SADECE SAHİP KULLANIR).

Kullanım:
    anahtar_uretici.exe              → 1 anahtar üretir
    anahtar_uretici.exe --adet 10    → 10 anahtar üretir

Bu program müşteriye verilmez; yalnızca lisans satan kişiye aittir.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lisans  # noqa: E402

BASLIK = "=" * 56


def main() -> None:
    adet = 1
    if "--adet" in sys.argv:
        try:
            adet = max(1, int(sys.argv[sys.argv.index("--adet") + 1]))
        except (IndexError, ValueError):
            adet = 1

    print()
    print(BASLIK)
    print("   HACILAR KUYUMCULUK — LİSANS ANAHTARI ÜRETİCİ (bayi)")
    print(BASLIK)
    for _ in range(adet):
        print("   " + lisans.uret())
    print(BASLIK)
    print("   Anahtarları müşteriye özel kayıt altına alınız.")
    print("   Müşteri, anahtarı program açılışındaki ekrana girecek.")
    print(BASLIK)
    try:
        input("   Kapatmak için Enter'a basın...")
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main()
