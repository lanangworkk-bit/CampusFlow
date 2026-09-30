"""Semua ekstensi Flask di satu tempat.

Kenapa dipisah? Kalau instance dibuat di dalam app.py, circular import
kena saat routes ikut mengimpor app. Dengan begini, routes cukup
`from extensions import db` tanpa perlu tahu cara db dibuat.
"""

from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
cors = CORS()
limiter = Limiter(key_func=get_remote_address, default_limits=['300 per hour'])
