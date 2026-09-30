"""Test performa: index, pagination, dan batas waktu respons."""

import time

import pytest

from backend.services import optimize


class TestIndex:
    def test_index_penting_ada(self, app):
        """Index yang dipakai filter dan sort harus benar-benar ada."""
        with app.app_context():
            rows = optimize.db.session.execute(
                optimize.text(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                )
            ).fetchall()
            names = {r[0] for r in rows}

        wajib = {
            'ix_tasks_status',
            'ix_tasks_priority',
            'ix_tasks_deadline',
            'ix_tasks_user_id',
            'ix_courses_code',
        }
        assert wajib <= names, f'Index hilang: {wajib - names}'

    def test_index_majemuk_ada(self, app):
        with app.app_context():
            rows = optimize.db.session.execute(
                optimize.text("SELECT name FROM sqlite_master WHERE type='index'")
            ).fetchall()
            names = {r[0] for r in rows}
        assert 'ix_tasks_status_deadline' in names
        assert 'ix_tasks_user_deadline' in names

    def test_index_memang_dipakai(self, app, seeded):
        """Query harus jadi SEARCH (index seek), bukan SCAN (tabel penuh)."""
        with app.app_context():
            plan = optimize.explain(
                app,
                "SELECT * FROM tasks WHERE status = 'TODO' ORDER BY deadline",
            )
        detail = ' '.join(str(p.get('detail', '')) for p in plan)
        assert 'USING INDEX' in detail or 'USING COVERING INDEX' in detail
        assert 'SCAN' not in detail


class TestPaginationScalability:
    def test_halaman_terakhir_tetap_cepat(self, app, db, user):
        """Walaupun datanya banyak, satu halaman tetap di-bound per_page."""
        from backend.models import Task
        for i in range(500):
            db.session.add(Task(
                title=f'Tugas {i}', user_id=user.id, status='TODO',
            ))
        db.session.commit()

        client = app.test_client()
        token = client.post('/api/auth/login', json={
            'username': 'testuser', 'password': 'testpass123',
        }).get_json()['token']
        headers = {'Authorization': f'Bearer {token}'}

        start = time.perf_counter()
        body = client.get(
            '/api/tasks?per_page=20&page=25', headers=headers
        ).get_json()
        elapsed = time.perf_counter() - start

        assert body['total'] == 500
        assert body['total_pages'] == 25
        assert len(body['items']) == 20
        assert elapsed < 2.0, f'Lemot: {elapsed:.2f}s'

    def test_per_page_selalu_dibatasi(self, auth_client):
        for value in (1, 50, 100, 500, 100000):
            body = auth_client.get(f'/api/tasks?per_page={value}').get_json()
            assert 1 <= body['per_page'] <= 100


class TestResponseTime:
    @pytest.mark.parametrize('path', [
        '/api/tasks',
        '/api/courses',
        '/api/stats',
        '/api/notes',
    ])
    def test_respons_cepat(self, auth_client, seeded, path):
        start = time.perf_counter()
        response = auth_client.get(path)
        elapsed = time.perf_counter() - start
        assert response.status_code == 200
        assert elapsed < 1.0, f'{path} lambat: {elapsed:.2f}s'


class TestNPlusOne:
    def test_list_course_gunakan_query_terpisah(self, app, db, user):
        """Jumlah task per course harus dihitung dalam satu GROUP BY."""
        from backend.models import Course, Task
        courses = []
        for i in range(5):
            c = Course(name=f'MK {i}', code=f'C{i}')
            db.session.add(c)
            courses.append(c)
        db.session.commit()
        for c in courses:
            for j in range(10):
                db.session.add(Task(
                    title=f'T{c.id}-{j}', user_id=user.id, course_id=c.id,
                ))
        db.session.commit()

        with app.app_context():
            totals, dones = optimize.load_courses_with_counts()
        assert sum(totals.values()) == 50
        assert len(totals) == 5


class TestCache:
    def test_cache_fungsi_dasar(self):
        cache = optimize.SimpleCache()
        assert cache.get('tidak-ada') is None
        cache.set('x', 42, ttl=60)
        assert cache.get('x') == 42
        cache.clear()
        assert cache.get('x') is None

    def test_cache_kedaluwarsa(self):
        cache = optimize.SimpleCache()
        cache.set('x', 42, ttl=-1)
        assert cache.get('x') is None

    def test_cache_ada_batas_ukuran(self):
        cache = optimize.SimpleCache(max_size=5)
        for i in range(20):
            cache.set(f'k{i}', i, ttl=60)
        assert len(cache._data) <= 5

    def test_decorator_cached(self):
        calls = []

        @optimize.cached('test-key-unik', ttl=60)
        def hitung():
            calls.append(1)
            return len(calls)

        optimize.cache.clear()
        before = optimize.stats['hits']
        assert hitung() == 1
        assert hitung() == 1
        # Fungsi asli hanya boleh dipanggil sekali.
        assert len(calls) == 1
        assert optimize.stats['hits'] == before + 1


class TestTableStats:
    def test_stats_tersedia(self, app, seeded):
        with app.app_context():
            stats = optimize.table_stats(app)
        assert 'tasks' in stats
        assert stats['tasks'] == 5
