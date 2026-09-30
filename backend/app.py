"""CampusFlow - Server Flask (Semester 2).

File ini hanya bertugas:
  1. membuat objek Flask
  2. mendaftarkan setiap Blueprint
  3. menjalankan server

Semua logika bisnis ada di db.py dan routes/.

Jalankan dengan:
    python backend/app.py
"""

from flask import Flask

from db import init_db, run_migrations
from routes.courses import courses_bp
from routes.main import main_bp
from routes.notes import notes_bp
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

if __name__ == '__main__':
    init_db()
    run_migrations()
    app.run(debug=True, use_reloader=False, port=5002)
