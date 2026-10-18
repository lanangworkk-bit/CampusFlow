"""Test untuk autentikasi: register, login, JWT, refresh, dan logout."""

from datetime import timedelta

import pytest
from flask_jwt_extended import decode_token as decode


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


def _login(client):
    """Login dan kembalikan access + refresh token."""
    return client.post('/api/auth/login', json={
        'username': 'testuser', 'password': 'testpass123',
    }).get_json()


class TestRefreshToken:
    def test_login_memberikan_kedua_token(self, client, user):
        body = _login(client)
        assert body['token']
        assert body['refresh_token']
        assert body['token'] != body['refresh_token']

    def test_register_juga_memberikan_refresh_token(self, client):
        body = client.post('/api/auth/register', json={
            'username': 'budi',
            'email': 'budi@campus.id',
            'password': 'rahasia123',
        }).get_json()
        assert body['refresh_token']

    def test_login_mencatat_sesi(self, client, user, db):
        from backend.models import RefreshToken
        _login(client)
        assert RefreshToken.query.count() == 1
        row = RefreshToken.query.first()
        assert row.user_id == user.id
        assert row.revoked_at is None
        assert row.is_active is True

    def test_refresh_memberikan_token_baru(self, client, user):
        awal = _login(client)
        response = client.post('/api/auth/refresh', headers={
            'Authorization': f'Bearer {awal["refresh_token"]}'
        })
        assert response.status_code == 200
        body = response.get_json()
        assert body['token'] != awal['token']
        assert body['refresh_token'] != awal['refresh_token']
        assert body['user']['username'] == 'testuser'

    def test_access_token_baru_sah(self, client, user):
        awal = _login(client)
        baru = client.post('/api/auth/refresh', headers={
            'Authorization': f'Bearer {awal["refresh_token"]}'
        }).get_json()
        response = client.get('/api/auth/me', headers={
            'Authorization': f'Bearer {baru["token"]}'
        })
        assert response.status_code == 200

    def test_token_lama_dicabut_setelah_rotasi(self, client, user, db):
        from backend.models import RefreshToken
        awal = _login(client)
        lama = client.post('/api/auth/refresh', headers={
            'Authorization': f'Bearer {awal["refresh_token"]}'
        }).get_json()

        record_lama = RefreshToken.query.filter_by(
            replaced_by=decode(lama['refresh_token'])['jti']
        ).first()
        assert record_lama is not None
        assert record_lama.revoked_at is not None
        assert record_lama.revoked_reason == 'rotated'

    def test_token_lama_tidak_boleh_dipakai_dua_kali(self, client, user):
        awal = _login(client)
        client.post('/api/auth/refresh', headers={
            'Authorization': f'Bearer {awal["refresh_token"]}'
        })
        kedua = client.post('/api/auth/refresh', headers={
            'Authorization': f'Bearer {awal["refresh_token"]}'
        })
        assert kedua.status_code == 401
        assert 'dipakai' in kedua.get_json()['error']

    def test_pakai_ulang_mencabut_semua_sesi(self, client, user, db):
        from backend.models import RefreshToken
        # Dua login: satu di laptop, satu lagi di ponsel.
        laptop = _login(client)
        ponsel = client.post('/api/auth/login', json={
            'username': 'testuser', 'password': 'testpass123',
        }).get_json()

        # Laptop refresh lebih dulu. Setelah itu token laptop basi,
        # sementara sesi ponsel masih aktif dan tidak tersentuh.
        assert client.post('/api/auth/refresh', headers={
            'Authorization': f'Bearer {laptop["refresh_token"]}'
        }).status_code == 200
        assert RefreshToken.query.filter_by(revoked_at=None).count() == 2

        # Seseorang memakai ulang token laptop yang sudah dipakai.
        response = client.post('/api/auth/refresh', headers={
            'Authorization': f'Bearer {laptop["refresh_token"]}'
        })
        assert response.status_code == 401

        # Semua sesi ikut dibersihkan, termasuk sesi ponsel yang sah:
        # kita tidak tahu siapa pemilik aslinya dan siapa pencuri.
        assert RefreshToken.query.filter_by(revoked_at=None).count() == 0
        assert RefreshToken.query.filter(
            RefreshToken.reuse_detected_at.is_not(None)
        ).count() == 1

    def test_token_kedaluwarsa_ditolak(self, client, user, db):
        from backend.models import RefreshToken, utcnow
        body = _login(client)
        record = RefreshToken.query.first()
        record.expires_at = utcnow() - timedelta(seconds=1)
        db.session.commit()

        response = client.post('/api/auth/refresh', headers={
            'Authorization': f'Bearer {body["refresh_token"]}'
        })
        assert response.status_code == 401
        assert 'kedaluwarsa' in response.get_json()['error']

    def test_token_rusak_ditolak(self, client, user):
        response = client.post('/api/auth/refresh', headers={
            'Authorization': 'Bearer bukan.token.validasi'
        })
        assert response.status_code == 401

    def test_tanpa_token_ditolak(self, client, user):
        assert client.post('/api/auth/refresh').status_code == 401

    def test_access_token_tidak_bisa_dipakai_sebagai_refresh(self, client, user):
        awal = _login(client)
        response = client.post('/api/auth/refresh', headers={
            'Authorization': f'Bearer {awal["token"]}'
        })
        assert response.status_code == 401

    def test_refresh_token_tidak_bisa_dipakai_sebagai_access(self, client, user):
        awal = _login(client)
        response = client.get('/api/auth/me', headers={
            'Authorization': f'Bearer {awal["refresh_token"]}'
        })
        assert response.status_code == 401


class TestLogout:
    def test_logout_mencabut_sesi(self, client, user, db):
        from backend.models import RefreshToken
        body = _login(client)
        response = client.post('/api/auth/logout', headers={
            'Authorization': f'Bearer {body["token"]}'
        }, json={'refresh_token': body['refresh_token']})
        assert response.status_code == 200

        record = RefreshToken.query.first()
        assert record.revoked_at is not None
        assert record.revoked_reason == 'logout'

    def test_setelah_logout_refresh_ditolak(self, client, user):
        body = _login(client)
        client.post('/api/auth/logout', headers={
            'Authorization': f'Bearer {body["token"]}'
        }, json={'refresh_token': body['refresh_token']})

        response = client.post('/api/auth/refresh', headers={
            'Authorization': f'Bearer {body["refresh_token"]}'
        })
        assert response.status_code == 401

    def test_setelah_logout_sesi_lama_jatuh(self, client, user):
        """Rotasi setelah logout dianggap penyalahgunaan.

        Sesi ini sudah dicabut dengan sengaja, jadi memakainya lagi
        diperlakukan seperti pencuri: seluruh sesi ikut dibersihkan.
        """
        body = _login(client)
        client.post('/api/auth/logout', headers={
            'Authorization': f'Bearer {body["token"]}'
        }, json={'refresh_token': body['refresh_token']})
        response = client.post('/api/auth/refresh', headers={
            'Authorization': f'Bearer {body["refresh_token"]}'
        })
        assert response.status_code == 401

    def test_logout_tanpa_token_tidak_error(self, client, user):
        assert client.post('/api/auth/logout').status_code == 200

    def test_logout_dua_kali_tetap_berhasil(self, client, user):
        body = _login(client)
        for _ in range(2):
            response = client.post('/api/auth/logout', headers={
                'Authorization': f'Bearer {body["token"]}'
            }, json={'refresh_token': body['refresh_token']})
            assert response.status_code == 200

    def test_logout_orang_lain_tidak_boleh(self, client, user, db, admin):
        from backend.models import RefreshToken
        body = _login(client)

        # Admin login, lalu mencoba logout sesi milik testuser.
        admin_body = client.post('/api/auth/login', json={
            'username': 'admin', 'password': 'adminpass123',
        }).get_json()
        client.post('/api/auth/logout', headers={
            'Authorization': f'Bearer {admin_body["token"]}'
        }, json={'refresh_token': body['refresh_token']})

        # Sesi testuser harus utuh.
        masih_aktif = RefreshToken.query.filter_by(
            user_id=user.id, revoked_at=None
        ).count()
        assert masih_aktif == 1

    def test_logout_semua_sesi(self, client, user, db):
        from backend.models import RefreshToken
        _login(client)
        kedua = client.post('/api/auth/login', json={
            'username': 'testuser', 'password': 'testpass123',
        }).get_json()

        response = client.post('/api/auth/logout', headers={
            'Authorization': f'Bearer {kedua["token"]}'
        }, json={'all_sessions': True})
        assert response.status_code == 200
        assert RefreshToken.query.filter_by(revoked_at=None).count() == 0

    def test_logout_tercatat_di_audit_log(self, client, user, db):
        from backend.models import AuditLog
        body = _login(client)
        client.post('/api/auth/logout', headers={
            'Authorization': f'Bearer {body["token"]}'
        }, json={'refresh_token': body['refresh_token']})
        assert AuditLog.query.filter_by(action='logout').first() is not None


class TestSessions:
    def test_sesi_aktif_terlihat(self, client, user):
        body = _login(client)
        response = client.get('/api/auth/sessions', headers={
            'Authorization': f'Bearer {body["token"]}'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['total'] == 1
        assert data['sessions'][0]['jti']

    def test_sesi_lama_tidak_dihitung(self, client, user):
        awal = _login(client)
        client.post('/api/auth/refresh', headers={
            'Authorization': f'Bearer {awal["refresh_token"]}'
        })
        baru = client.post('/api/auth/login', json={
            'username': 'testuser', 'password': 'testpass123',
        }).get_json()

        data = client.get('/api/auth/sessions', headers={
            'Authorization': f'Bearer {baru["token"]}'
        }).get_json()
        # Ada dua sesi aktif: hasil rotasi dan login terakhir. Yang
        # dicabut rotasi tidak dihitung.
        assert data['total'] == 2

    def test_sesi_orang_lain_tidak_terlihat(self, client, user, admin):
        body = _login(client)
        admin_body = client.post('/api/auth/login', json={
            'username': 'admin', 'password': 'adminpass123',
        }).get_json()
        data = client.get('/api/auth/sessions', headers={
            'Authorization': f'Bearer {admin_body["token"]}'
        }).get_json()
        jti_milik_user = decode(body['refresh_token'])['jti']
        assert all(s['jti'] != jti_milik_user for s in data['sessions'])

    def test_hanya_bisa_lihat_sesi_sendiri(self, client, user, admin):
        _login(client)
        admin_body = client.post('/api/auth/login', json={
            'username': 'admin', 'password': 'adminpass123',
        }).get_json()
        data = client.get('/api/auth/sessions', headers={
            'Authorization': f'Bearer {admin_body["token"]}'
        }).get_json()
        assert data['total'] == 1

    def test_sesi_tanpa_token_ditolak(self, client, user):
        assert client.get('/api/auth/sessions').status_code == 401
