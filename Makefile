# Perintah pintas. Jalankan dengan: make <target>
# Butuh make (sudah ada di macOS dan Linux).

PYTHON ?= python3
VENV   ?= venv
BIN     = $(VENV)/bin
PORT   ?= 5002

.DEFAULT_GOAL := help
.PHONY: help install run dev test lint seed reset clean shell docker-build docker-up docker-down migrate check

help:  ## Tampilkan daftar perintah
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install:  ## Pasang semua dependency
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt

run:  ## Jalankan server (mode production)
	$(BIN)/gunicorn --bind 0.0.0.0:$(PORT) --workers 3 --threads 2 backend.app:app

dev:  ## Jalankan server dengan auto-reload
	FLASK_DEBUG=1 $(BIN)/python3 -m backend.app

test:  ## Jalankan semua test
	$(BIN)/python3 -m pytest tests/ -v

lint:  ## Cek syntax semua file
	$(BIN)/python3 -m compileall -q backend/
	node --check static/script.js

seed:  ## Isi data contoh (demo + admin)
	$(BIN)/flask --app backend.app seed --admin

migrate:  ## Buat/ubah tabel database dari model
	$(BIN)/flask --app backend.app db upgrade

check:  ## Periksa konfigurasi dan koneksi database
	$(BIN)/flask --app backend.app check

reset:  ## HAPUS SEMUA DATA lalu isi ulang
	@read -p "Semua data akan dihapus. Lanjut? [y/N] " ok; \
	if [ "$$ok" = "y" ] || [ "$$ok" = "Y" ]; then \
		$(BIN)/flask --app backend.app seed --admin; \
		echo "Data sudah direset."; \
	else \
		echo "Dibatalkan."; \
	fi

clean:  ## Hapus cache dan file sementara
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf .ruff_cache htmlcov .coverage
	@echo "Bersih."

shell:  ## Buka Python shell dengan database siap
	$(BIN)/flask --app backend.app shell

docker-build:  ## Build image Docker
	docker compose build

docker-up:  ## Jalankan semua service (app + postgres + redis)
	docker compose up -d --build
	@echo "Aplikasi: http://localhost:$(PORT)"

docker-down:  ## Hentikan semua service
	docker compose down

docker-logs:  ## Lihat log container
	docker compose logs -f web
