"""Hacılar Kuyumculuk — Veresiye Takip Programı · Flask uygulama fabrikası."""
from __future__ import annotations

import os
import secrets

try:  # masaüstü sürümünde flask paketlenmez; yalnızca web için gerekli
    from flask import Flask, redirect, url_for

    from . import views
except ImportError:  # pragma: no cover
    Flask = None

from . import backup as backup_mod
from . import db as dbmod


def _gizli_anahtar(kok: str) -> str:
    """Oturum anahtarı bir kez üretilir, proje kökünde saklanır."""
    yol = os.path.join(kok, "gizli_anahtar.txt")
    if os.path.exists(yol):
        with open(yol, "r", encoding="utf-8") as f:
            anahtar = f.read().strip()
        if anahtar:
            return anahtar
    anahtar = secrets.token_hex(32)
    with open(yol, "w", encoding="utf-8") as f:
        f.write(anahtar)
    return anahtar


def create_app(port: int = 8765) -> Flask:
    if Flask is None:
        raise RuntimeError("Flask kurulu değil; web sürümü için: pip install flask")
    kok = dbmod.proje_koku()          # veri kökü (db, yedekler, anahtar)
    paket = dbmod.paket_koku()        # şablon/statik kökü
    dbmod.init_db()

    app = Flask(
        __name__,
        template_folder=os.path.join(paket, "templates"),
        static_folder=os.path.join(paket, "static"),
    )
    app.config["SECRET_KEY"] = _gizli_anahtar(kok)
    app.config["PORT"] = port
    app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 30   # 30 gün "beni hatırla"
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024

    app.register_blueprint(views.bp)

    yy = backup_mod.YedekYoneticisi()
    app.extensions["yedek"] = yy
    app.extensions["db_sagligi"] = dbmod.saglik_kontrol()

    @app.route("/favicon.ico")
    def _favicon():
        return "", 204

    return app
