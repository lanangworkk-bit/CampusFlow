"""CampusFlow - Server Flask (Semester 2).

File ini hanya bertugas:
  1. membuat objek Flask
  2. mendaftarkan setiap Blueprint
  3. menjalankan server

Semua logika bisnis ada di db.py dan routes/.

Jalankan dengan:
    python backend/app.py
"""

from flask import Flask, jsonify, request

from db import init_db, run_migrations
from routes.courses import courses_bp
from routes.main import main_bp
from routes.notes import notes_bp
from routes.stats import stats_bp
from routes.tasks import tasks_bp

app = Flask(
    __name__,
    template_folder='../templates',
    static_folder='../static',
)

app.register_blueprint(main_bp)
app.register_blueprint(tasks_bp)
app.register_blueprint(notes_bp)
app.register_blueprint(courses_bp)
app.register_blueprint(stats_bp)


@app.errorhandler(404)
def handle_not_found(error):
    """Balas JSON untuk request API, halaman HTML untuk browser.

    Tanpa ini, user yang salah ketik URL /api/tasks/typo akan
    melihat halaman error HTML instead of JSON, dan JavaScript
    akan gagal parse-nya dengan pesan yang membingungkan.
    """
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Endpoint not found'}), 404
    return jsonify({'error': 'Page not found'}), 404


@app.errorhandler(405)
def handle_method_not_allowed(error):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Method not allowed'}), 405
    return jsonify({'error': 'Method not allowed'}), 405


@app.errorhandler(500)
def handle_server_error(error):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error'}), 500
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    init_db()
    run_migrations()
    app.run(debug=True, use_reloader=False, port=5002)
