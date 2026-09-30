"""Test untuk autentikasi: register, login, JWT, dan pembatasan akses."""

import pytest


class TestRegister:
    def test_register_success(self, client):
        response = client.post('/api/auth/register', json={
            'username': 'budi',
            'email': 'budi@campus.id',
            'password': 'rahasia123',
            'full_name': 'Budi Santoso',
        })
        assert response.status_code == 201
        body = response.get_json()
        assert 'token' in body
        assert body['user']['username'] == 'budi'
        assert body['user']['role'] == 'student'

    def test_password_tidak_pernah_disimpan_polos(self, client, db):
        from backend.models import User
        client.post('/api/auth/register', json={
            'username': 'budi',
            'email': 'budi@campus.id',
            'password': 'rahasia123',
        })
        user = User.query.filter_by(username='budi').first()
        assert user is not None
        assert 'rahasia123' not in user.password_hash
        assert user.password_hash != 'rahasia123'
        assert user.check_password('rahasia123') is True

    @pytest.mark.parametrize('username', ['ab', 'a' * 31, 'budi santoso', 'budi!', ''])
    def test_username_tidak_valid(self, client, username):
        response = client.post('/api/auth/register', json={
            'username': username,
            'email': 'x@campus.id',
            'password': 'rahasia123',
        })
        assert response.status_code == 400

    @pytest.mark.parametrize('email', ['bukan-email', 'a@', '@b.com', 'a b@c.com'])
    def test_email_tidak_valid(self, client, email):
        response = client.post('/api/auth/register', json={
            'username': 'budi',
            'email': email,
            'password': 'rahasia123',
        })
        assert response.status_code == 400

    def test_password_kurang_dari_8(self, client):
        response = client.post('/api/auth/register', json={
            'username': 'budi',
            'email': 'budi@campus.id',
            'password': 'pendek',
        })
        assert response.status_code == 400

    def test_username_sudah_dipakai(self, client, user):
        response = client.post('/api/auth/register', json={
            'username': 'testuser',
            'email': 'lain@campus.id',
            'password': 'rahasia123',
        })
        assert response.status_code == 409

    def test_email_sudah_dipakai(self, client, user):
        response = client.post('/api/auth/register', json={
            'username': 'userlain',
            'email': 'test@test.id',
            'password': 'rahasia123',
        })
        assert response.status_code == 409

    def test_username_dinormalisasi(self, client):
        response = client.post('/api/auth/register', json={
            'username': '  BUDI  ',
            'email': 'budi@campus.id',
            'password': 'rahasia123',
        })
        assert response.status_code == 201
        assert response.get_json()['user']['username'] == 'budi'


class TestLogin:
    def test_login_berhasil(self, client, user):
        response = client.post('/api/auth/login', json={
            'username': 'testuser', 'password': 'testpass123',
        })
        assert response.status_code == 200
        assert 'token' in response.get_json()

    def test_login_pakai_email(self, client, user):
        response = client.post('/api/auth/login', json={
            'username': 'test@test.id', 'password': 'testpass123',
        })
        assert response.status_code == 200

    def test_password_salah(self, client, user):
        response = client.post('/api/auth/login', json={
            'username': 'testuser', 'password': 'passwordsalah',
        })
        assert response.status_code == 401

    def test_user_tidak_ada(self, client):
        response = client.post('/api/auth/login', json={
            'username': 'tidakada', 'password': 'apa saja',
        })
        assert response.status_code == 401

    def test_pesan_error_sama_untuk_kedua_kasus(self, client, user):
        """Pesan error tidak boleh membedaakan user tak ada vs password salah."""
        salah = client.post('/api/auth/login', json={
            'username': 'testuser', 'password': 'salah',
        }).get_json()['error']
        tidak_ada = client.post('/api/auth/login', json={
            'username': 'entah', 'password': 'salah',
        }).get_json()['error']
        assert salah == tidak_ada

    def test_field_kosong(self, client):
        response = client.post('/api/auth/login', json={})
        assert response.status_code == 400

    def test_last_login_tercatat(self, client, user, db):
        assert user.last_login_at is None
        client.post('/api/auth/login', json={
            'username': 'testuser', 'password': 'testpass123',
        })
        db.session.refresh(user)
        assert user.last_login_at is not None


class TestToken:
    def test_me_tanpa_token(self, client):
        assert client.get('/api/auth/me').status_code == 401

    def test_me_dengan_token(self, client, user):
        token = client.post('/api/auth/login', json={
            'username': 'testuser', 'password': 'testpass123',
        }).get_json()['token']
        response = client.get('/api/auth/me', headers={
            'Authorization': f'Bearer {token}'
        })
        assert response.status_code == 200
        assert response.get_json()['username'] == 'testuser'

    def test_token_rusak(self, client):
        response = client.get('/api/auth/me', headers={
            'Authorization': 'Bearer token.ngawur.total'
        })
        assert response.status_code == 401

    def test_token_kosong(self, client):
        response = client.get('/api/auth/me', headers={'Authorization': 'Bearer '})
        assert response.status_code == 401

    def test_password_hash_tidak_pernah_keluar(self, client, user):
        token = client.post('/api/auth/login', json={
            'username': 'testuser', 'password': 'testpass123',
        }).get_json()['token']
        body = client.get('/api/auth/me', headers={
            'Authorization': f'Bearer {token}'
        }).get_json()
        assert 'password' not in body
        assert 'password_hash' not in body
