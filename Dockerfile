# syntax=docker/dockerfile:1
# ===================================================================
# CampusFlow - multi-stage build
# ===================================================================
# Dipisah jadi beberapa tahap supaya:
#   - image akhir tidak ikut membawa compiler dan file sumber
#   - dependency dibangun sekali, dipakai ulang di tahap berikutnya
#   - container menjalankan user non-root

# ---------- Tahap 1: build dependency ----------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Wheel di-build di sini supaya tahap runtime tidak butuh compiler.
RUN pip wheel --wheel-dir /wheels -r requirements.txt


# ---------- Tahap 2: runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FLASK_ENV=production \
    PORT=8000

# libpq5 saja (runtime), bukan build-essential. Image jadi jauh lebih kecil.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 curl \
 && rm -rf /var/lib/apt/lists/*

# User non-root: kalau container berhasil ditembus, attacker tidak
# langsung dapat akses root di dalam container.
#
# -m itu penting, bukan ACCESSORI. Tanpa folder home, Gunicorn tidak
# bisa membuat socket kontrolnya di $HOME/.gunicorn/ karena /home
# dimiliki root, lalu arbiter mencatat
# "Control server error: [Errno 13] Permission denied: '/home/appuser'".
# Worker tetap jalan, tapi perintah `gunicorn ctl` jadi tidak bisa dipakai
# untuk graceful reload.
RUN groupadd -r appuser && useradd -r -m -g appuser appuser

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .

RUN pip install --no-index --find-links=/wheels -r requirements.txt \
 && rm -rf /wheels

COPY --chown=appuser:appuser . .

# Folder yang butuh izin tulis untuk appuser.
#
# instance/ dipakai saat DATABASE_URL menunjuk SQLite relatif, dan
# database/ untuk SQLite default. Alembic juga menulis di instance/.
RUN mkdir -p /app/database /app/instance \
 && chown -R appuser:appuser /app/database /app/instance

# Entry point harus executable di dalam image. Melepasnya dari Git
# membuat file kehilangan bit+x saat di-checkout di host.
RUN chmod +x /app/docker-entrypoint.sh

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

# Gunicorn dengan 3 worker, sesuai jumlah CPU.
# --preload memuat aplikasi sekali sebelum worker mulai,
# supaya RAM tidak dipakai berulang kali.
#
# Container dijalankan lewat entrypoint, bukan langsung ke gunicorn.
# Entrypoint menjalankan `flask db upgrade` lebih dulu; tanpa itu
# skema tidak pernah dibuat karena mode production tidak auto-create,
# dan /api/health akan membalas 503.
ENTRYPOINT ["/app/docker-entrypoint.sh"]

CMD ["gunicorn", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--threads", "2", \
     "--timeout", "60", \
     "--graceful-timeout", "30", \
     "--preload", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "backend.app:app"]
