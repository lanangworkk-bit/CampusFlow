#!/bin/sh
# Build step untuk deployment di Vercel.
#
# Skema database diperbarui sebelum aplikasi melayani request. Mode
# production sengaja tidak memakai create_all(), jadi tanpa langkah ini
# tabelnya tidak ada dan /api/health membalas 503.
#
# Migrasi dijalankan lewat DATABASE_URL_UNPOOLED kalau variabel itu ada.
# Endpoint '-pooler' dari Neon memakai PgBouncer dalam mode transaction,
# dan menjalankan DDL lewat sana berisiko. Kalau variabelnya tidak ada
# (mis. database penyedia lain), DATABASE_URL biasa dipakai.

set -e

if [ -n "$DATABASE_URL_UNPOOLED" ]; then
    echo "[vercel] Menjalankan migrasi lewat koneksi langsung (unpooled) ..."
    DATABASE_URL="$DATABASE_URL_UNPOOLED" \
        python -m flask --app backend.app db upgrade
else
    echo "[vercel] Menjalankan migrasi database ..."
    python -m flask --app backend.app db upgrade
fi

echo "[vercel] Build selesai."
