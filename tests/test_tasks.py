"""Test untuk CRUD task, validasi, filter, sort, dan paginasi."""

import pytest


class TestCreateTask:
    def test_create_berhasil(self, auth_client):
        response = auth_client.post('/api/tasks', json={
            'title': 'Belajar Flask',
            'description': 'Baca dokumentasi',
            'priority': 'HIGH',
            'deadline': '2026-12-01',
        })
        assert response.status_code == 201
        body = response.get_json()
        assert body['title'] == 'Belajar Flask'
        assert body['status'] == 'TODO'
        assert body['progress'] == 0

    def test_title_wajib_ada(self, auth_client):
        assert auth_client.post('/api/tasks', json={}).status_code == 400
        assert auth_client.post('/api/tasks', json={'title': '  '}).status_code == 400
        assert auth_client.post('/api/tasks', json={'title': ''}).status_code == 400

    @pytest.mark.parametrize('deadline', ['abc', '2026-13-45', '20-10-2026', '2026/10/20'])
    def test_deadline_format_salah(self, auth_client, deadline):
        response = auth_client.post('/api/tasks', json={
            'title': 'X', 'deadline': deadline,
        })
        assert response.status_code == 400

    def test_deadline_kosong_itu_sah(self, auth_client):
        for value in ('', None, '   '):
            response = auth_client.post('/api/tasks', json={
                'title': 'Tanpa tenggat', 'deadline': value,
            })
            assert response.status_code == 201
            assert response.get_json()['deadline'] is None

    @pytest.mark.parametrize('field', ['status', 'priority'])
    def test_enum_tidak_valid_ditolak(self, auth_client, field):
        response = auth_client.post('/api/tasks', json={
            'title': 'X', field: 'NGABO',
        })
        assert response.status_code == 400

    def test_overdue_tidak_bisa_disimpan(self, auth_client):
        response = auth_client.post('/api/tasks', json={
            'title': 'X', 'status': 'OVERDUE',
        })
        assert response.status_code == 400

    def test_progress_diluar_rentang(self, auth_client):
        for value in (-1, 101, 999):
            response = auth_client.post('/api/tasks', json={
                'title': 'X', 'progress': value,
            })
            assert response.status_code == 400

    def test_teks_dipangkas(self, auth_client):
        response = auth_client.post('/api/tasks', json={
            'title': 'A' * 500, 'description': 'B' * 10000,
        })
        assert response.status_code == 201
        assert len(response.get_json()['title']) == 200
        assert len(response.get_json()['description']) == 5000

    def test_karakter_kontrol_dibuang(self, auth_client, db):
        from backend.models import Task
        auth_client.post('/api/tasks', json={'title': ' Judul\x00aneh\x07 '})
        task = Task.query.first()
        assert '\x00' not in task.title
        assert '\x07' not in task.title
        assert task.title == 'Judulaneh'


class TestUpdateTask:
    def test_update_berhasil(self, auth_client, seeded):
        task_id = seeded[0].id
        response = auth_client.put(f'/api/tasks/{task_id}', json={
            'title': 'Judul Baru', 'priority': 'URGENT',
        })
        assert response.status_code == 200
        assert response.get_json()['title'] == 'Judul Baru'

    def test_partial_update_tidak_menghapus_field_lain(self, auth_client, seeded):
        original = seeded[0]
        response = auth_client.put(f'/api/tasks/{original.id}', json={
            'title': 'Hanya Judul',
        })
        body = response.get_json()
        assert body['title'] == 'Hanya Judul'
        assert body['priority'] == original.priority
        # Response API selalu string YYYY-MM-DD, sementara original.deadline
        # sekarang date object karena kolomnya bertipe DATE. Bandingkan
        # dalam format yang sama supaya yang diuji adalah nilai
        # tenggatnya, bukan perbedaan tipe.
        assert body['deadline'] == original.deadline.isoformat()

    def test_completed_maksa_progress_100(self, auth_client, seeded):
        response = auth_client.put(f'/api/tasks/{seeded[0].id}', json={
            'status': 'COMPLETED',
        })
        assert response.get_json()['progress'] == 100

    def test_dari_completed_kembali_progress_0(self, auth_client, seeded):
        response = auth_client.put(f'/api/tasks/{seeded[3].id}', json={
            'status': 'IN PROGRESS',
        })
        assert response.get_json()['progress'] == 0

    def test_progress_berubah_aja(self, auth_client, seeded):
        response = auth_client.put(f'/api/tasks/{seeded[0].id}', json={
            'progress': 75,
        })
        assert response.get_json()['progress'] == 75

    def test_progress_diabaikan_saat_completed(self, auth_client, seeded):
        response = auth_client.put(f'/api/tasks/{seeded[0].id}', json={
            'status': 'COMPLETED', 'progress': 10,
        })
        assert response.get_json()['progress'] == 100

    def test_task_tidak_ada(self, auth_client):
        assert auth_client.put('/api/tasks/99999', json={'title': 'X'}).status_code == 404

    def test_deadline_baru_tidak_valid(self, auth_client, seeded):
        original = seeded[0].deadline
        response = auth_client.put(f'/api/tasks/{seeded[0].id}', json={
            'deadline': 'nanti',
        })
        assert response.status_code == 400
        db_value = seeded[0].deadline
        assert db_value == original


class TestAuthorization:
    def test_tanpa_token_ditolak(self, client, seeded):
        assert client.get('/api/tasks').status_code == 401
        assert client.post('/api/tasks', json={'title': 'X'}).status_code == 401
        assert client.put('/api/tasks/1', json={'title': 'X'}).status_code == 401
        assert client.delete('/api/tasks/1').status_code == 401

    def test_user_tidak_bisa_ubah_task_milik_orang_lain(
        self, auth_client, seeded, client, db, user
    ):
        from backend.models import Task, User
        lain = User(username='oranglain', email='lain@test.id')
        lain.set_password('password123')
        db.session.add(lain)
        db.session.commit()

        task_asing = Task(title='Milik orang lain', user_id=lain.id)
        db.session.add(task_asing)
        db.session.commit()

        assert auth_client.put(
            f'/api/tasks/{task_asing.id}', json={'title': 'Dibajak'}
        ).status_code == 404
        assert auth_client.delete(f'/api/tasks/{task_asing.id}').status_code == 404

    def test_admin_boleh_lihat_semua(self, admin_client, db, user):
        from backend.models import Task
        db.session.add(Task(title='Task user lain', user_id=user.id))
        db.session.commit()
        response = admin_client.get('/api/tasks')
        assert response.status_code == 200


class TestFilterSortPaginate:
    def test_filter_status(self, auth_client, seeded):
        response = auth_client.get('/api/tasks?status=TODO')
        assert all(t['status'] == 'TODO' for t in response.get_json()['items'])

    def test_filter_overdue_menghitung_berulang(self, auth_client, seeded):
        response = auth_client.get('/api/tasks?status=OVERDUE')
        items = response.get_json()['items']
        # Beta dan Gamma punya tenggat relatif 10 dan 200 hari lalu, jadi
        # keduanya pasti OVERDUE. Delta selesai dan Alpha masih 30 hari
        # ke depan, jadi tidak ikut terhitung.
        #
        # Sebelumnya test ini memakai pengaman
        # `2 if date.today() >= '2026-09-20' else 1`, yang membuat
        # test bisa lolos tanpa benar-benar memeriksa apa pun saat
        # tanggalnya belum tercapai. Sekarang tenggatnya relatif, jadi
        # jumlahannya pasti 2 kapan pun test dijalankan.
        assert len(items) == 2
        assert {i['title'] for i in items} == {'Tugas Beta', 'Tugas Gamma'}
        assert all(i['status'] == 'OVERDUE' for i in items)

    def test_task_tidak_muncul_di_dua_filter(self, auth_client, seeded):
        """Status yang tampil harus sama dengan filter yang dipilih."""
        for status in ('TODO', 'IN PROGRESS', 'COMPLETED', 'OVERDUE'):
            items = auth_client.get(f'/api/tasks?status={status}').get_json()['items']
            assert all(i['status'] == status for i in items), status

    def test_filter_priority(self, auth_client, seeded):
        response = auth_client.get('/api/tasks?priority=URGENT')
        assert len(response.get_json()['items']) == 1

    def test_search(self, auth_client, seeded):
        response = auth_client.get('/api/tasks?search=Flask')
        assert len(response.get_json()['items']) == 1

    def test_search_kosong_returns_semua(self, auth_client, seeded):
        response = auth_client.get('/api/tasks?search=')
        assert response.get_json()['total'] == len(seeded)

    def test_sort_by_deadline(self, auth_client, seeded):
        items = auth_client.get(
            '/api/tasks?sort=deadline&order=asc'
        ).get_json()['items']
        ada_deadline = [i for i, t in enumerate(items) if t['deadline']]
        assert ada_deadline == sorted(ada_deadline)

    def test_null_deadline_di_akhir(self, auth_client, seeded):
        items = auth_client.get(
            '/api/tasks?sort=deadline&order=asc'
        ).get_json()['items']
        assert items[-1]['deadline'] is None

    def test_sort_title_desc(self, auth_client, seeded):
        items = auth_client.get(
            '/api/tasks?sort=title&order=desc'
        ).get_json()['items']
        titles = [i['title'] for i in items]
        assert titles == sorted(titles, reverse=True)

    def test_sort_tidak_dikenal_diabaikan(self, auth_client, seeded):
        assert auth_client.get('/api/tasks?sort=ngawur').status_code == 200

    def test_paginasi_metadata(self, auth_client, seeded):
        response = auth_client.get('/api/tasks?per_page=2&page=1')
        body = response.get_json()
        assert set(body) == {
            'items', 'total', 'page', 'per_page',
            'total_pages', 'has_next', 'has_prev',
        }
        assert len(body['items']) == 2
        assert body['has_next'] is True
        assert body['has_prev'] is False

    def test_per_page_dibatasi(self, auth_client, seeded):
        assert auth_client.get('/api/tasks?per_page=9999').get_json()['per_page'] == 100

    def test_page_melebihi_batas_diklem(self, auth_client, seeded):
        response = auth_client.get('/api/tasks?per_page=2&page=999')
        assert response.get_json()['page'] == response.get_json()['total_pages']

    def test_semua_item_muncul_tepat_sekali(self, auth_client, seeded):
        seen = []
        page = 1
        while True:
            body = auth_client.get(
                f'/api/tasks?per_page=2&page={page}'
            ).get_json()
            seen.extend(i['id'] for i in body['items'])
            if not body['has_next']:
                break
            page += 1
        assert len(seen) == len(set(seen)) == len(seeded)


class TestInjection:
    """Query harus tahan terhadap SQL injection."""

    def test_injection_di_search(self, auth_client, seeded):
        for payload in ["' OR 1=1 --", "'; DROP TABLE tasks; --", "' UNION SELECT * FROM users --"]:
            response = auth_client.get('/api/tasks', query_string={'search': payload})
            assert response.status_code == 200
            assert response.get_json()['total'] == 0

    def test_injection_di_sort(self, auth_client, seeded):
        response = auth_client.get(
            '/api/tasks?sort=' + 'id%3B%20DROP%20TABLE%20tasks'
        )
        assert response.status_code == 200

    def test_injection_di_order(self, auth_client, seeded):
        response = auth_client.get(
            '/api/tasks?order=ASC%3B%20DROP%20TABLE%20tasks'
        )
        assert response.status_code == 200

    def test_tabel_utuh_setelah_injection(self, auth_client, seeded):
        auth_client.get('/api/tasks?search=%27%20OR%201%3D1%20--')
        assert auth_client.get('/api/tasks').get_json()['total'] == len(seeded)
