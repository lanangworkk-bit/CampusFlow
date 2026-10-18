"""Titik masuk WSGI untuk platform serverless seperti Vercel.

Vercel mencari instance Flask bernama `app` di salah satu nama file
yang dikenali: app.py, index.py, server.py, main.py, wsgi.py, atau
asgi.py. Aplikasi sebenarnya ada di backend/app.py, dan file ini cuma
jembatan supaya ditemukan tanpa harus memindahkan seluruh paket
backend ke root proyek.

Jalur gunicorn di Dockerfile tetap memakai backend.app:app, jadi
keduanya menunjuk ke aplikasi yang sama.
"""

from backend.app import app  # noqa: F401
