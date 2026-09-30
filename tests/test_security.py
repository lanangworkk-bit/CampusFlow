"""Test keamanan: header, sanitasi, rate limit, dan otorisasi."""

import pytest


class TestSecurityHeaders:
    @pytest.mark.parametrize('header,expected', [
        ('X-Content-Type-Options', 'nosniff'),
        ('X-Frame-Options', 'DENY'),
        ('Referrer-Policy', 'strict-origin-when-cross-origin'),
    ])
    def test_header_ada(self, client, header, expected):
        response = client.get('/api/health')
        assert response.headers.get(header) == expected

    def test_csp_ada(self, client):
        csp = client.get('/api/health').headers.get('Content-Security-Policy', '')
        assert 'default-src' in csp
        assert "'self'" in csp
        assert 'frame-ancestors' in csp

    def test_permissions_policy_ada(self, client):
        policy = client.get('/api/health').headers.get('Permissions-Policy', '')
        assert 'geolocation=()' in policy

    def test_hsts_tidak_ada_di_debug(self, client):
        """HSTS hanya untuk production, kalau tidak merusak localhost."""
        assert 'Strict-Transport-Security' not in client.get('/api/health').headers

    def test_header_ada_di_halaman_html_juga(self, client):
        response = client.get('/')
        assert response.headers.get('X-Content-Type-Options') == 'nosniff'


class TestSanitasiInput:
    def test_karakter_kontrol_dibuang(self):
        from backend.services.security import clean_text
        assert clean_text('halo\x00dunia\x07') == 'halodunia'

    def test_panjang_dibatasi(self):
        from backend.services.security import clean_text
        assert len(clean_text('a' * 500, max_length=50)) == 50

    def test_none_dipakai(self):
        from backend.services.security import clean_text
        assert clean_text(None) is None

    def test_whitespace_dipangkas(self):
        from backend.services.security import clean_text
        assert clean_text('  teks  ') == 'teks'

    def test_xss_script_dibuang_di_server(self, auth_client, db):
        """Tag berbahaya dibuang di server, bukan hanya saat dirender.

        Dulu tag-nya tersimpan utuh dan aman semata-mata karena
        frontend memakai textContent. Sekarang dibuang lebih dulu,
        jadi tetap aman walau data ini diekspor atau dirender
        oleh klien lain.
        """
        from backend.models import Task
        auth_client.post('/api/tasks', json={
            'title': '<script>alert(1)</script>',
            'description': '<img src=x onerror=alert(1)>',
        })
        task = Task.query.first()
        assert '<script' not in task.title
        assert '</script>' not in task.title
        assert 'onerror' not in task.description
        assert '<img' not in task.description

    def test_teks_normal_tidak_berubah(self, auth_client, db):
        """Sanitasi tidak boleh merusak teks yang wajar."""
        from backend.models import Task
        asli = 'UTS Basis Data: pertanyaan jaringan & 5 < 10 soal'
        auth_client.post('/api/tasks', json={'title': asli})
        assert Task.query.first().title == asli

    def test_perbandingan_angka_tetap_utuh(self, auth_client, db):
        """Tanda '<' di teks biasa tidak boleh ikut terhapus."""
        from backend.models import Task
        auth_client.post('/api/tasks', json={
            'title': 'Nilai a < b dan c > d',
        })
        assert Task.query.first().title == 'Nilai a < b dan c > d'


class TestBodyValidation:
    def test_bukan_json_ditolak(self, auth_client):
        response = auth_client.post(
            '/api/tasks', data='ini bukan json',
            content_type='text/plain',
        )
        assert response.status_code == 415

    def test_json_tidak_valid_ditolak(self, auth_client):
        response = auth_client.post(
            '/api/tasks', data='{bukan json}',
            content_type='application/json',
        )
        assert response.status_code in (400, 415)


class TestApiKey:
    def test_tanpa_key_ditolak(self, client):
        assert client.get('/api/metrics').status_code == 401

    def test_key_salah_ditolak(self, client):
        response = client.get('/api/metrics', headers={'X-API-Key': 'salah'})
        assert response.status_code == 401

    def test_key_benar_diterima(self, client):
        response = client.get(
            '/api/metrics', headers={'X-API-Key': 'test-admin-key'}
        )
        assert response.status_code == 200
        assert 'counts' in response.get_json()

    def test_token_user_tidak_cukup(self, auth_client):
        """JWT user tidak boleh menggantikan API key sistem."""
        assert auth_client.get('/api/metrics').status_code == 401


class TestRoleBasedAccess:
    def test_audit_log_khusus_admin(self, client, admin):
        token = client.post('/api/auth/login', json={
            'username': 'admin', 'password': 'adminpass123',
        }).get_json()['token']
        response = client.get(
            '/api/audit-logs', headers={'Authorization': f'Bearer {token}'}
        )
        assert response.status_code == 200

    def test_student_dilarang_audit_log(self, auth_client):
        assert auth_client.get('/api/audit-logs').status_code == 403

    def test_student_tidak_bisa_hapus_mata_kuliah(self, auth_client, course):
        assert auth_client.delete(f'/api/courses/{course.id}').status_code == 403

    def test_admin_bisa_hapus_mata_kuliah(self, admin_client, course):
        assert admin_client.delete(f'/api/courses/{course.id}').status_code == 200

    def test_hapus_mata_kuliah_yang_dipakai_ditolak(self, admin_client, course, db, user):
        from backend.models import Task
        db.session.add(Task(title='X', user_id=user.id, course_id=course.id))
        db.session.commit()
        response = admin_client.delete(f'/api/courses/{course.id}')
        assert response.status_code == 409
        assert response.get_json()['task_count'] == 1

    def test_force_melepas_task(self, admin_client, course, db, user):
        from backend.models import Task
        task = Task(title='X', user_id=user.id, course_id=course.id)
        db.session.add(task)
        db.session.commit()
        response = admin_client.delete(f'/api/courses/{course.id}?force=true')
        assert response.status_code == 200
        assert response.get_json()['detached_tasks'] == 1


class TestAuditLog:
    def test_tercatat_setelah_create(self, auth_client, db):
        from backend.models import AuditLog
        auth_client.post('/api/tasks', json={'title': 'Diawasi'})
        entries = AuditLog.query.all()
        assert len(entries) == 1
        assert entries[0].action == 'create'
        assert entries[0].resource == 'task'

    def test_tercatat_setelah_update(self, auth_client, seeded, db):
        from backend.models import AuditLog
        auth_client.put(f'/api/tasks/{seeded[0].id}', json={'title': 'Baru'})
        actions = [e.action for e in AuditLog.query.all()]
        assert 'update' in actions

    def test_tercatat_setelah_delete(self, auth_client, seeded, db):
        from backend.models import AuditLog
        auth_client.delete(f'/api/tasks/{seeded[0].id}')
        actions = [e.action for e in AuditLog.query.all()]
        assert 'delete' in actions

    def test_gagal_tidak_tercatat(self, auth_client, db):
        from backend.models import AuditLog
        auth_client.post('/api/tasks', json={'title': ''})
        assert AuditLog.query.count() == 0

    def test_admin_bisa_filter_action(self, admin_client, db):
        admin_client.post('/api/tasks', json={'title': 'Satu'})
        admin_client.delete('/api/tasks/1')
        response = admin_client.get('/api/audit-logs?action=delete')
        assert response.status_code == 200
        for entry in response.get_json()['items']:
            assert entry['action'] == 'delete'


class TestPasswordStorage:
    def test_hash_bukan_password(self, db):
        from backend.models import User
        user = User(username='x', email='x@x.id')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        assert user.password_hash != 'password123'
        assert len(user.password_hash) > 40
        assert user.check_password('password123')
        assert not user.check_password('passwordsalah')

    def test_hash_berbeda_walau_password_sama(self, db):
        from backend.models import User
        a = User(username='a', email='a@x.id')
        a.set_password('sama')
        b = User(username='b', email='b@x.id')
        b.set_password('sama')
        assert a.password_hash != b.password_hash


class TestContentSecurityPolicy:
    """CSP harus ketat: tanpa 'unsafe-inline' pun tanpa CDN pihak ketiga.

    Kalau ada 'unsafe-inline' di script-src, header ini tidak menambah
    perlindungan apa pun terhadap XSS.
    """

    def _csp(self, client):
        return client.get('/').headers.get('Content-Security-Policy', '')

    def test_tanpa_unsafe_inline(self, client):
        csp = self._csp(client)
        assert "'unsafe-inline'" not in csp
        assert "'unsafe-eval'" not in csp

    def test_tanpa_cdn_pihak_ketiga(self, client):
        csp = self._csp(client)
        assert 'https://' not in csp, f'masih ada sumber eksternal: {csp}'

    def test_script_dan_style_punya_batas(self, client):
        csp = self._csp(client)
        assert "script-src 'self'" in csp
        assert "style-src 'self'" in csp

    def test_frame_ancestors_none(self, client):
        assert "frame-ancestors 'none'" in self._csp(client)

    def test_error_page_juga_terlindungi(self, client):
        assert client.get('/halaman-hilang').status_code == 404

    def test_tidak_ada_inline_script_di_template(self):
        """Halaman error tidak boleh menyisipkan script inline.

        Kalau ada, CSP script-src 'self' akan memblokirnya dan fitur
        kecil di halaman itu akan gagal diam-diam.
        """
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        for name in ('404.html', '500.html', 'index.html'):
            html = (root / 'templates' / name).read_text()
            assert '<script>' not in html, f'{name} punya script inline'
            assert ' style="' not in html, f'{name} punya atribut style inline'
            assert '<style>' not in html, f'{name} punya blok style inline'
