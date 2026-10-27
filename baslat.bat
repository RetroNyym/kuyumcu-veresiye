@echo off
chcp 65001 >nul
title Kuyumcu Veresiye Premium
cd /d "%~dp0"
python baslat.py
if errorlevel 1 (
    echo.
    echo Python bulunamadi veya hata olustu.
    pause
)
