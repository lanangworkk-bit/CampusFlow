#!/bin/sh
# Entry point container.
#
# Fungsinya satu: pastikan skema database ada sebelum aplikasi mulai
# melayani request.
#
# Mode production sengaja tidak memakai create_all(). Kalau tabel dibuat
# otomatis, tidak ada riwayat migration yang tercatat dan perubahan
# skema berikutnya tidak bisa diterapkan dengan benar. Konsekuensinya,
# aplikasi harus menjalankan `flask db upgrade` lebih dulu.
#
# Tanpa langkah ini, container tetap hidup tapi /api/health membalas 503
# karena tabelnya belum ada, dan healthcheck menandainya unhealthy.

set -e

echo "[entrypoint] Menjalankan migrasi database..."

# Alembic butuh satu revision untuk tiap menjalankan paralel. Kalau
# beberapa container start bersamaan, yang kedua akan menunggu di
# kunci file sampai yang pertama selesai, lalu melihat revision terbaru
# dan berhenti tanpa melakukan apa-apa. Ini membuat 'db upgrade' aman
# dijalankan di beberapa replica sekaligus.
flask --app backend.app db upgrade

echo "[entrypoint] Migrasi selesai, menjalankan: $*"
exec "$@"