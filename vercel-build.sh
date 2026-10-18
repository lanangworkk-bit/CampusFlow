#!/bin/sh
# Build step untuk deployment di Vercel.
#
# Dua hal yang harus terjadi sebelum aplikasi melayani request:
#
# 1. Aset statis (style.css, script.js, css/) disalin ke public/.
#    Vercel menyajikan folder public/ langsung dari CDN dan tidak
#    membaca app.static_folder milik Flask. Folder static/ yang asli
#    tetap dipertahankan karena dipakai saat jalan lokal dan di Docker.
#
# 2. Skema database diperbarui. Mode production sengaja tidak memakai
#    create_all(), jadi tanpa langkah ini tabelnya tidak ada dan
#    /api/health membalas 503.

set -e

echo "[vercel] Menyalin aset statis ke public/ ..."
mkdir -p public
cp -R static public/static

echo "[vercel] Menjalankan migrasi database ..."
python -m flask --app backend.app db upgrade

echo "[vercel] Build selesai."
