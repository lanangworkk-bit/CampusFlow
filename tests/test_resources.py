"""Test untuk mata kuliah dan catatan."""

import pytest


class TestCourse:
    def test_create(self, auth_client):
        response = auth_client.post('/api/courses', json={
            'name': 'Kecerdasan Artifisial', 'code': 'IF301', 'sks': 3,
        })
        assert response.status_code == 201
        assert response.get_json()['code'] == 'IF301'

    def test_code_normalisasi_kapital(self, auth_client):
        response = auth_client.post('/api/courses', json={
            'name': 'X', 'code': 'lower',
        })
        assert response.get_json()['code'] == 'LOWER'

    def test_name_dan_code_wajib(self, auth_client):
        assert auth_client.post('/api/courses', json={'code': 'X1'}).status_code == 400
        assert auth_client.post('/api/courses', json={'name': 'X'}).status_code == 400

    def test_kode_duplikat(self, auth_client, course):
        response = auth_client.post('/api/courses', json={
            'name': 'Duplikat', 'code': course.code,
        })
        assert response.status_code == 409

    @pytest.mark.parametrize('sks', [-1, 13, 99])
    def test_sks_diluar_rentang(self, auth_client, sks):
        response = auth_client.post('/api/courses', json={
            'name': 'X', 'code': 'X1', 'sks': sks,
        })
        assert response.status_code == 400

    def test_sks_bukan_angka(self, auth_client):
        response = auth_client.post('/api/courses', json={
            'name': 'X', 'code': 'X1', 'sks': 'tiga',
        })
        assert response.status_code == 400

    def test_list_dengan_statistik_task(self, auth_client, course, db, user):
        from backend.models import Task
        db.session.add_all([
            Task(title='A', user_id=user.id, course_id=course.id),
            Task(title='B', user_id=user.id, course_id=course.id, status='COMPLETED'),
        ])
        db.session.commit()
        items = auth_client.get('/api/courses').get_json()['items']
        found = [i for i in items if i['id'] == course.id][0]
        assert found['task_count'] == 2
        assert found['task_done'] == 1

    def test_search_berbagai_kolom(self, auth_client, course):
        for keyword in ('Basis', 'BD101', 'Andi'):
            response = auth_client.get('/api/courses', query_string={'search': keyword})
            assert response.get_json()['total'] == 1, keyword

    def test_options_tanpa_paginasi(self, auth_client, db):
        from backend.models import Course
        for i in range(15):
            db.session.add(Course(name=f'MK {i}', code=f'C{i}'))
        db.session.commit()
        response = auth_client.get('/api/courses/options')
        assert response.status_code == 200
        # Tanpa fixture course, totalnya 15. Endpoint ini sengaja
        # tidak berpaginasi karena dipakai untuk mengisi dropdown.
        assert len(response.get_json()) == 15

    def test_update(self, auth_client, course):
        response = auth_client.put(f'/api/courses/{course.id}', json={
            'name': 'Nama Baru',
        })
        assert response.get_json()['name'] == 'Nama Baru'

    def test_update_kode_bentrok(self, auth_client, course, db):
        from backend.models import Course
        other = Course(name='Lain', code='OTHER')
        db.session.add(other)
        db.session.commit()
        response = auth_client.put(
            f'/api/courses/{course.id}', json={'code': other.code}
        )
        assert response.status_code == 409

    def test_update_tidak_ada(self, auth_client):
        assert auth_client.put('/api/courses/9999', json={'name': 'X'}).status_code == 404

    def test_paginasi_mata_kuliah(self, auth_client, db):
        from backend.models import Course
        for i in range(20):
            db.session.add(Course(name=f'MK {i:02d}', code=f'C{i:02d}'))
        db.session.commit()
        body = auth_client.get('/api/courses?per_page=7&page=1').get_json()
        assert body['total'] == 20
        assert body['total_pages'] == 3
        assert body['has_next'] is True
        last = auth_client.get('/api/courses?per_page=7&page=3').get_json()
        assert len(last['items']) == 6
        assert last['has_next'] is False

    def test_sort_kolom_valid(self, auth_client, db):
        from backend.models import Course
        db.session.add_all([
            Course(name='B', code='B', sks=2),
            Course(name='A', code='A', sks=4),
        ])
        db.session.commit()
        items = auth_client.get('/api/courses?sort=sks&order=desc').get_json()['items']
        assert items[0]['sks'] == 4


class TestNote:
    def test_create(self, auth_client):
        response = auth_client.post('/api/notes', json={'text': 'Catatan penting'})
        assert response.status_code == 201
        assert response.get_json()['text'] == 'Catatan penting'

    def test_text_wajib(self, auth_client):
        assert auth_client.post('/api/notes', json={}).status_code == 400
        assert auth_client.post('/api/notes', json={'text': '  '}).status_code == 400

    def test_pinned_default_false(self, auth_client):
        body = auth_client.post('/api/notes', json={'text': 'X'}).get_json()
        assert body['pinned'] is False

    def test_pinned_bisa_diatur(self, auth_client):
        body = auth_client.post(
            '/api/notes', json={'text': 'X', 'pinned': True}
        ).get_json()
        assert body['pinned'] is True

    def test_terupdate_terlebih_dulu(self, auth_client, db, user):
        from backend.models import Note
        db.session.add_all([
            Note(text='Pinned', user_id=user.id, pinned=True),
            Note(text='Biasa', user_id=user.id),
        ])
        db.session.commit()
        items = auth_client.get('/api/notes').get_json()
        assert items[0]['pinned'] is True

    def test_update(self, auth_client):
        note = auth_client.post('/api/notes', json={'text': 'Awal'}).get_json()
        response = auth_client.put(f"/api/notes/{note['id']}", json={
            'text': 'Akhir', 'pinned': True,
        })
        assert response.status_code == 200
        assert response.get_json()['text'] == 'Akhir'
        assert response.get_json()['pinned'] is True

    def test_delete(self, auth_client):
        note = auth_client.post('/api/notes', json={'text': 'X'}).get_json()
        assert auth_client.delete(f"/api/notes/{note['id']}").status_code == 200
        assert auth_client.put(
            f"/api/notes/{note['id']}", json={'text': 'Y'}
        ).status_code == 404

    def test_catatan_private(self, auth_client, db, user):
        from backend.models import Note
        lain = Note(text='Rahasia orang lain', user_id=None)
        db.session.add(lain)
        db.session.commit()
        texts = [n['text'] for n in auth_client.get('/api/notes').get_json()]
        assert 'Rahasia orang lain' not in texts


class TestSystemEndpoints:
    def test_health_healthy(self, client):
        response = client.get('/api/health')
        assert response.status_code == 200
        assert response.get_json()['status'] == 'healthy'

    def test_health_cek_database(self, client):
        checks = client.get('/api/health').get_json()['checks']
        assert 'database' in checks
        assert 'orm' in checks

    def test_health_tidak_butuh_token(self, client):
        assert client.get('/api/health').status_code == 200

    def test_version(self, client):
        body = client.get('/api/version').get_json()
        assert body['semester'] == 8
        assert 'python' in body

    def test_healthz_alias(self, client):
        assert client.get('/healthz').status_code == 200

    def test_halaman_404_html(self, client):
        response = client.get('/halaman-tidak-ada')
        assert response.status_code == 404
        assert response.content_type.startswith('text/html')

    def test_api_404_json(self, client):
        response = client.get('/api/tidak-ada')
        assert response.status_code == 404
        assert response.content_type.startswith('application/json')
        assert 'error' in response.get_json()


class TestKontrakValidasi:
    """Nilai yang sah harus diterima.

    Test di atas hanya memeriksa nilai yang ditolak. Test ini menjaga
    agar penolakan tidak jadi terlalu longgar, misalnya karena sebuah
    validasi ditambahkan dengan filter yang keliru.
    """

    def test_priority_urgent_valid(self, auth_client):
        response = auth_client.post('/api/tasks', json={
            'title': 'Darurat', 'priority': 'URGENT',
        })
        assert response.status_code == 201
        assert response.get_json()['priority'] == 'URGENT'

    def test_semua_priority_diterima(self, auth_client):
        for p in ('LOW', 'MEDIUM', 'HIGH', 'URGENT'):
            r = auth_client.post('/api/tasks', json={'title': f'T {p}', 'priority': p})
            assert r.status_code == 201, p

    def test_priority_kosong_default_medium(self, auth_client):
        body = auth_client.post('/api/tasks', json={'title': 'Tanpa priority'}).get_json()
        assert body['priority'] == 'MEDIUM'

    def test_sks_nol_diterima(self, auth_client):
        """SKS 0 sah (misal praktikum tanpa bobot) dan 0-12 valid."""
        r = auth_client.post('/api/courses', json={'name': 'Praktikum', 'code': 'P1', 'sks': 0})
        assert r.status_code == 201
        assert r.get_json()['sks'] == 0

    def test_sks_batas_atas(self, auth_client):
        r = auth_client.post('/api/courses', json={'name': 'Capstone', 'code': 'C12', 'sks': 12})
        assert r.status_code == 201

    def test_deskripsi_boleh_panjang(self, auth_client):
        body = auth_client.post('/api/tasks', json={
            'title': 'Panjang', 'description': 'B' * 5000,
        }).get_json()
        assert len(body['description']) == 5000

    def test_tugas_tanpa_deadline_diterima(self, auth_client):
        assert auth_client.post('/api/tasks', json={'title': 'Noid'}).status_code == 201
