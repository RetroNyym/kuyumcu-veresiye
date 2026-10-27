"""Kuyumcu Veresiye Premium — başlatıcı.

Çalıştır:  python baslat.py
- Paneli kendi tarayıcınızda açar.
- Aynı ağdaki tabletten erişmek için ekranda yazan adresi kullanın.
- Saatlik + günlük + aylık otomatik yedekleme arka planda başlar.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from veresiye import create_app          # noqa: E402
from veresiye import db as dbmod         # noqa: E402

BOS_PORT = 8765


def bos_port_bul(baslangic: int = BOS_PORT, adet: int = 30) -> int:
    for port in range(baslangic, baslangic + adet):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
            return port
        except OSError:
            continue
        finally:
            s.close()
    return baslangic


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main() -> None:
    port = bos_port_bul()
    app = create_app(port=port)

    # Otomatik yedekleme döngüsü
    yy = app.extensions["yedek"]
    yy.baslat()

    ip = lan_ip()
    yerel = f"http://127.0.0.1:{port}"
    tablet = f"http://{ip}:{port}"

    print()
    print("=" * 62)
    print("   KUYUMCU VERESİYE PREMIUM")
    print("=" * 62)
    print(f"   Panel (bu bilgisayar) : {yerel}")
    print(f"   Tablet / diğer cihaz  : {tablet}")
    print("   (Tablet ile aynı Wi-Fi ağında olun)")
    print("-" * 62)
    print("   Yedekleme : saatlik + günlük + aylık (otomatik)")
    print(f"   Veritabanı: {dbmod.VERESIYE_DB}")
    print("=" * 62)
    print()

    if os.environ.get("VERESIYE_TEST") != "1":
        threading.Timer(1.2, lambda: webbrowser.open(yerel)).start()

    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nUygulama kapatıldı. Veriler güvende.")
