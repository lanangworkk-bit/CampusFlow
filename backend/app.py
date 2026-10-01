"""CampusFlow - aplikasi Flask.

Jalankan:
    python3 -m backend.app

atau:
    gunicorn 'backend.app:create_app()'
"""

import os
import sys
import time

from flask import Flask, jsonify, render_template, request

# Path supaya modul bisa diimpor baik lewat `python3 backend/app.py`
# maupun `gunicorn backend.app:create_app()`.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.config import ProductionConfig, get_config  # noqa: E402
from backend.extensions import cors, db, jwt, limiter, migrate  # noqa: E402
from backend.routes.analytics import analytics_bp, system_bp  # noqa: E402
from backend.routes.auth import auth_bp  # noqa: E402
from backend.routes.resources import resources_bp  # noqa: E402
from backend.services.optimize import (  # noqa: E402
    attach_query_optimizer,
    create_performance_indexes,
)
from backend.services.security import security_headers  # noqa: E402


def create_app(config_name=None):
    # config_name bisa berupa string ('testing') atau objek config.
    if isinstance(config_name, str):
        from backend.config import CONFIGS

        config_name = CONFIGS[config_name]

    app = Flask(
        __name__,
        template_folder=os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..', 'templates'
        ),
        static_folder=os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..', 'static'
        ),
    )
    app.config.from_object(config_name or get_config())

    # Baca DATABASE_URL di sini, bukan hanya waktu modul diimpor.
    #
    # Nilai di kelas Config dihitung sekali saat import, jadi kalau
    # DATABASE_URL berubah setelah import (dipakai test, atau oleh
    # skrip yang mengubah env lebih dulu), nilainya basi. Dengan
    # dibaca ulang di sini, env selalu sesuai kondisi saat app dibuat.
    #
    # TestingConfig dikecualikan: ia harus tetap memakai database di
    # memori supaya test tidak pernah menyentuh file milik developer.
    if not app.config.get('TESTING'):
        from backend.config import _database_url

        if os.environ.get('DATABASE_URL'):
            app.config['SQLALCHEMY_DATABASE_URI'] = _database_url()

    _register_pages(app)
    _init_extensions(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_hooks(app)
    _register_cli(app)

    # Semua model harus sudah ter-import sebelum create_all() dipanggil,
    # supaya SQLAlchemy tahu tabel mana yang perlu dibuat. Import-nya
    # diletakkan di dalam fungsi supaya tidak ada circular import.
    if app.config.get('AUTO_CREATE_TABLES', True):
        with app.app_context():
            from backend.models import AuditLog, Course, Note, Task, User  # noqa: F401

            db.create_all()
    else:
        app.logger.info(
            'AUTO_CREATE_TABLES dimatikan. Jalankan '
            '`flask --app backend.app db upgrade` untuk membuat skema.'
        )

    # Index tambahan dan penghitung query. Index memakai
    # CREATE INDEX IF NOT EXISTS, jadi aman dipanggil berulang.
    if not app.config.get('TESTING'):
        attach_query_optimizer(app)
    else:
        # Test tetap butuh index yang sama supaya test performa
        # benar-benar menguji kondisi production.
        with app.app_context():
            create_performance_indexes(app)

    return app


def _register_pages(app):
    """Halaman HTML.

    Daftarkan lewat fungsi, bukan di modul level. Kalau ditulis di
    modul level, route-nya hanya menempel ke satu objek app, dan
    app yang dibuat create_app() di tempat lain (test, gunicorn)
    tidak punya halaman ini sama sekali.
    """

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/healthz')
    def healthz():
        """Alias health check untuk platform yang memanggil /healthz."""
        return jsonify({'status': 'ok'})


def _enable_sqlite_foreign_keys(app):
    """Nyalakan PRIMARY KEY / FOREIGN KEY enforcement di SQLite.

    SQLite membaca PRAGMA ini per koneksi, dan default-nya MATI.
    Akibatnya SQLite diam-diam mengabaikan seluruh constraint kolom
    REFERENCES di skema: task dengan user_id yang tidak ada tetap
    berhasil disimpan. PostgreSQL, yang jadi database production,
    menolaknya. Dua database yang sama jadi berperilaku berbeda
    tergantung mana yang dipakai.

    Event ini dipasang sebelum db.init_app() supaya berlaku ke semua
    koneksi baru dari connection pool, bukan cuma koneksi pertama.

    PRAGMA ini diabaikan diam-diam oleh database selain SQLite, jadi
    pemanggilannya aman untuk semua dialect.
    """
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, 'connect')
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        # Objek koneksi DBAPI tidak menyebut dialect-nya di repr, jadi
        # dicek lewat modul driver: modul 'sqlite3' hanya dipakai
        # koneksi SQLite.
        if dbapi_connection.__class__.__module__.split('.')[0] != 'sqlite3':
            return

        cursor = dbapi_connection.cursor()
        try:
            cursor.execute('PRAGMA foreign_keys=ON')
        finally:
            cursor.close()


def _init_extensions(app):
    _enable_sqlite_foreign_keys(app)
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(
        app,
        resources={r'/api/*': {'origins': app.config['CORS_ORIGINS']}},
    )
    limiter.init_app(app)

    @jwt.unauthorized_loader
    def missing_token(reason):
        return jsonify({'error': 'Token tidak ada. Silakan login.'}), 401

    @jwt.invalid_token_loader
    def invalid_token(reason):
        return jsonify({'error': 'Token tidak valid'}), 401

    @jwt.expired_token_loader
    def expired_token(jwt_header, jwt_payload):
        return jsonify({'error': 'Token kedaluwarsa, silakan login lagi'}), 401

    @jwt.revoked_token_loader
    def revoked_token(jwt_header, jwt_payload):
        return jsonify({'error': 'Token sudah dicabut'}), 401

    @jwt.needs_fresh_token_loader
    def needs_fresh(jwt_header, jwt_payload):
        return jsonify({'error': 'Token lama, silakan login ulang'}), 401

    @jwt.additional_claims_loader
    def add_claims(identity):
        from backend.models import User

        user = db.session.get(User, int(identity)) if identity else None
        if user is None:
            return {}
        return {'role': user.role, 'username': user.username}


def _register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(resources_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(system_bp)


def _register_error_handlers(app):
    def wants_json():
        return (
            request.path.startswith('/api/')
            or request.accept_mimetypes.best == 'application/json'
        )

    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({'error': 'Permintaan tidak valid'}), 400

    @app.errorhandler(404)
    def not_found(error):
        if wants_json():
            return jsonify({'error': 'Endpoint tidak ditemukan'}), 404
        return render_template('404.html'), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        return jsonify({'error': 'Metode tidak diizinkan'}), 405

    @app.errorhandler(413)
    def too_large(error):
        return jsonify({'error': 'Data terlalu besar'}), 413

    @app.errorhandler(415)
    def unsupported_media(error):
        return jsonify({'error': 'Harus berupa JSON'}), 415

    @app.errorhandler(429)
    def rate_limited(error):
        return jsonify({
            'error': 'Terlalu banyak permintaan. Coba lagi nanti.'
        }), 429

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        if wants_json():
            return jsonify({'error': 'Terjadi kesalahan di server'}), 500
        return render_template('500.html'), 500


def _register_hooks(app):
    @app.after_request
    def after(response):
        return security_headers(response)

    @app.before_request
    def track_request():
        from flask import g

        g.start_time = time.perf_counter()

    @app.teardown_appcontext
    def cleanup(exception=None):
        if exception is not None:
            db.session.rollback()


def _register_cli(app):
    import click

    @app.cli.command('init-db')
    def init_db():
        """Buat semua tabel."""
        db.create_all()
        click.echo('Tabel dibuat.')

    @app.cli.command('seed')
    @click.option('--admin', is_flag=True, help='Buat juga akun admin')
    def seed(admin):
        """Isi data contoh."""
        from backend.seed_data import run_seed

        run_seed(admin=admin)

    @app.cli.command('create-user')
    @click.argument('username')
    @click.argument('password')
    @click.option('--email', default=None)
    @click.option('--role', default='student')
    def create_user(username, password, email, role):
        """Buat satu user baru."""
        from backend.models import User

        if User.query.filter_by(username=username.lower()).first():
            click.echo('Username sudah ada.')
            return
        user = User(
            username=username.lower(),
            email=email or f'{username.lower()}@campusflow.id',
            role=role,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f'User {user.username} dibuat dengan role {user.role}.')

    @app.cli.command('check')
    def check():
        """Periksa konfigurasi dan koneksi database."""
        from sqlalchemy import text

        click.echo(f'Environment : {os.environ.get("FLASK_ENV", "development")}')
        click.echo(f'Database    : {app.config["SQLALCHEMY_DATABASE_URI"][:60]}')
        try:
            db.session.execute(text('SELECT 1'))
            click.echo('Database    : OK')
        except Exception as error:
            click.echo(f'Database    : GAGAL - {error}')
        if app.config.get('DEBUG') is False:
            problems = ProductionConfig.validate()
            for problem in problems:
                click.echo(f'PERINGATAN: {problem}')


# Instance default, dipakai oleh `python3 -m backend.app` dan gunicorn.
# Test dan skrip lain sebaiknya memanggil create_app() sendiri.
app = create_app()


if __name__ == '__main__':
    # Jalankan dengan `python3 -m backend.app`.
    #
    # Ini untuk pengembangan lokal. Untuk produksi pakai gunicorn
    # (make run), karena app.run() adalah server bawaan Flask yang
    # memang dirancang untuk development.
    port = int(os.environ.get('PORT', 5002))
    environment = os.environ.get('FLASK_ENV', 'development').lower()

    # Auto-reload hanya aktif di development.
    #
    # Dulu FLASK_DEBUG di sini default-nya '1', sehingga aplikasi
    # jalan dengan mode debug bahkan saat FLASK_ENV=production. Selain
    # memakai server development, itu membuat app.debug jadi True,
    # yang otomatis mematikan header HSTS karena klausul "hanya di
    # produksi". Header itu justru yang paling penting di produksi.
    default_debug = '0' if environment == 'production' else '1'
    debug = os.environ.get('FLASK_DEBUG', default_debug) == '1'

    print(f'  CampusFlow -> http://localhost:{port}')
    print(f'  Health     -> http://localhost:{port}/api/health')
    print(f'  Mode       -> {environment} (debug: {"on" if debug else "off"})')
    if environment == 'production':
        print('  Catatan    -> untuk produksi pakai gunicorn: make run')
    app.run(host='0.0.0.0', port=port, debug=debug, use_reloader=debug)
