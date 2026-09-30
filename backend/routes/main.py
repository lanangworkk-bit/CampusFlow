"""Route untuk halaman HTML dan operasi lintas tabel.

Route di sini bukan milik satu tabel tertentu, jadi diletakkan
di modul sendiri:

  /            -> merender halaman
  /api/reset   -> menghapus data dari SEMUA tabel sekaligus

Kalau /api/reset diletakkan di tasks.py, pembaca kode akan
mengira reset cuma untuk tasks, padahal ia juga menghapus
notes dan courses. Lokasi file adalah bagian dari dokumentasi.
"""

from flask import Blueprint, jsonify, render_template

from db import get_db

main_bp = Blueprint('main', __name__)

TABLES = ('tasks', 'notes', 'courses')


@main_bp.route('/')
def index():
    return render_template('index.html')


@main_bp.route('/api/reset', methods=['POST'])
def reset_all():
    db = get_db()
    for table in TABLES:
        db.execute(f'DELETE FROM {table}')
    db.commit()
    db.close()
    return jsonify({'message': 'All data deleted'})
