"""Nomor versi aplikasi.

Modul terpisah supaya backend.app, backend.routes, dan skrip lain bisa
semuanya mengimpor versi tanpa circular import.
"""

__version__ = '1.0.0'

# Semester yang sedang dikerjakan. Dipakai di halaman login dan
# endpoint /api/version supaya tidak ada angka versi yang berbeda
# di tempat berbeda.
SEMESTER = 8
