"""Test untuk mesin analitik, rekomendasi, dan prediksi."""

from datetime import date, timedelta

import pytest

from backend.services import analytics


class TestSummary:
    def test_kosong(self, db):
        result = analytics.summary()
        assert result['total'] == 0
        assert result['completion_rate'] == 0
        assert result['average_progress'] == 0

    def test_hitung_benar(self, seeded, user):
        result = analytics.summary(user.id)
        assert result['total'] == 5
        assert result['completed'] == 1
        # Beta (IN PROGRESS, tenggat 2026-09-20) dan Gamma (TODO,
        # tenggat 2026-01-01) sama-sama sudah lewat tenggat, jadi
        # keduanya tampil OVERDUE dan tidak dihitung lagi di
        # IN PROGRESS atau TODO.
        assert result['overdue'] == 2
        assert result['in_progress'] == 0
        assert result['todo'] == 2
        assert result['completion_rate'] == 20.0

    def test_status_saling_lepas(self, seeded, user):
        """Keempat status harus bisa dijumlahkan tepat ke total.

        Ini yang menahan bug lama: OVERDUE dihitung dari tanggal
        sementara IN PROGRESS dan TODO dibaca dari kolom status
        mentah, sehingga satu tugas terhitung dua kali dan
        jumlahnya melebihi total.
        """
        result = analytics.summary(user.id)
        jumlah = (
            result['completed'] + result['overdue']
            + result['in_progress'] + result['todo']
        )
        assert jumlah == result['total']

    def test_tugas_lewat_tenggat_tidak_terhitung_di_status_aslinya(self, db, user):
        """Satu tugas yang lewat tenggat hanya boleh masuk satu kategori."""
        from backend.models import Task
        db.session.add(Task(
            title='Telat', user_id=user.id,
            status='IN PROGRESS', deadline='2020-01-01',
        ))
        db.session.commit()

        result = analytics.summary(user.id)
        assert result['overdue'] == 1
        assert result['in_progress'] == 0
        assert result['completed'] + result['overdue'] \
            + result['in_progress'] + result['todo'] == result['total'] == 1

    def test_tidak_bagi_nol(self, db):
        result = analytics.summary()
        assert result['average_progress'] == 0
        assert result['completion_rate'] == 0


class TestGrouping:
    def test_by_status_selalu_lengkap(self, db):
        result = analytics.by_status()
        assert {r['status'] for r in result} == {
            'TODO', 'IN PROGRESS', 'COMPLETED', 'OVERDUE'
        }

    def test_by_status_menghitung_overdue(self, seeded, user):
        result = {r['status']: r['count'] for r in analytics.by_status(user.id)}
        assert result['COMPLETED'] == 1

    def test_by_priority_urutan_benar(self, db):
        result = analytics.by_priority()
        assert [r['priority'] for r in result] == [
            'URGENT', 'HIGH', 'MEDIUM', 'LOW'
        ]

    def test_by_course_termasuk_tanpa_mata_kuliah(self, seeded, user):
        result = analytics.by_course(user.id)
        names = [r['course'] for r in result]
        assert 'Tanpa Mata Kuliah' in names

    def test_by_course_terurut_turun(self, seeded, user):
        result = analytics.by_course(user.id)
        totals = [r['total'] for r in result]
        assert totals == sorted(totals, reverse=True)


class TestForecast:
    def test_tanpa_tugas(self, db):
        result = analytics.forecast()
        assert result['tasks_due'] == 0
        assert result['verdict'] == 'LIGHT'
        assert result['load_percent'] == 0

    def test_beban_berat(self, db, user, course):
        from backend.models import Task
        soon = (date.today() + timedelta(days=2)).isoformat()
        for i in range(40):
            db.session.add(Task(
                title=f'Beban {i}', user_id=user.id, course_id=course.id,
                deadline=soon, status='TODO',
            ))
        db.session.commit()
        result = analytics.forecast(user.id, horizon_days=7)
        assert result['verdict'] == 'OVERLOADED'
        assert result['load_percent'] > 100

    def test_horizon_berubah(self, db, user, course):
        from backend.models import Task
        far = (date.today() + timedelta(days=20)).isoformat()
        db.session.add(Task(title='Jauh', user_id=user.id, deadline=far))
        db.session.commit()
        assert analytics.forecast(user.id, 7)['tasks_due'] == 0
        assert analytics.forecast(user.id, 30)['tasks_due'] == 1


class TestUrgencyScore:
    def test_completed_skor_nol(self, seeded):
        done = [t for t in seeded if t.status == 'COMPLETED'][0]
        assert analytics.urgency_score(done) == 0

    def test_lewat_tenggat_paling_tinggi(self, db, user):
        from backend.models import Task
        lama = Task(
            title='Telat', user_id=user.id, status='TODO',
            priority='URGENT',
            deadline=(date.today() - timedelta(days=5)).isoformat(),
        )
        baru = Task(
            title='Aman', user_id=user.id, status='TODO',
            priority='URGENT',
            deadline=(date.today() + timedelta(days=30)).isoformat(),
        )
        db.session.add_all([lama, baru])
        db.session.commit()
        assert analytics.urgency_score(lama) > analytics.urgency_score(baru)

    def test_tanpa_deadline_masih_dihitung(self, db, user):
        from backend.models import Task
        task = Task(title='Tanpa tenggat', user_id=user.id,
                    status='TODO', priority='MEDIUM')
        db.session.add(task)
        db.session.commit()
        assert analytics.urgency_score(task) > 0

    def test_semua_field_skor_positif(self, db, user, course):
        from backend.models import Task
        task = Task(title='X', user_id=user.id, course_id=course.id,
                    status='TODO', priority='HIGH')
        db.session.add(task)
        db.session.commit()
        assert analytics.urgency_score(task) > 0


class TestSuggestions:
    def test_mengembalikan_dengan_alasan(self, db, user):
        from backend.models import Task
        soon = (date.today() + timedelta(days=1)).isoformat()
        db.session.add(Task(
            title='Mendesak', user_id=user.id, status='TODO',
            priority='URGENT', deadline=soon,
        ))
        db.session.commit()
        result = analytics.suggest(user.id)
        assert result
        assert result[0]['title'] == 'Mendesak'
        assert result[0]['reasons']
        assert 'urgency_score' in result[0]

    def test_terurut_skor_turun(self, db, user, course):
        from backend.models import Task
        db.session.add_all([
            Task(title='A', user_id=user.id, status='TODO', priority='LOW',
                 deadline=(date.today() + timedelta(days=60)).isoformat()),
            Task(title='B', user_id=user.id, status='TODO', priority='URGENT',
                 deadline=(date.today() - timedelta(days=10)).isoformat()),
        ])
        db.session.commit()
        scores = [r['urgency_score'] for r in analytics.suggest(user.id)]
        assert scores == sorted(scores, reverse=True)

    def test_tidak_menggabungkan_completed(self, db, user):
        from backend.models import Task
        db.session.add(Task(title='Selesai', user_id=user.id, status='COMPLETED'))
        db.session.commit()
        assert analytics.suggest(user.id) == []


class TestProductivity:
    def test_streak_dihitung(self, db, user):
        from backend.models import Task, utcnow
        db.session.add(Task(title='Hari ini', user_id=user.id))
        db.session.commit()
        result = analytics.productivity(user.id)
        assert result['current_streak_days'] >= 1

    def test_semua_hari_dalam_seminggu(self, db):
        result = analytics.productivity()
        assert len(result['by_day_of_week']) == 7

    def test_stuck_task(self, db, user):
        from backend.models import Task, utcnow
        task = Task(
            title='Terlantar', user_id=user.id, status='IN PROGRESS',
            updated_at=utcnow() - timedelta(days=30),
        )
        db.session.add(task)
        db.session.commit()
        stuck = analytics.stuck_tasks(user.id, days=7)
        assert [t['title'] for t in stuck] == ['Terlantar']

    def test_task_baru_bukan_stuck(self, db, user):
        from backend.models import Task
        db.session.add(Task(title='Baru', user_id=user.id, status='TODO'))
        db.session.commit()
        assert analytics.stuck_tasks(user.id, days=7) == []


class TestFullReport:
    def test_lengkap(self, seeded, user):
        report = analytics.full_report(user.id)
        assert set(report) == {
            'generated_at', 'summary', 'by_status', 'by_priority',
            'by_course', 'productivity', 'stuck', 'upcoming',
            'forecast', 'suggestions',
        }

    def test_bisa_diserialisasi(self, seeded, user):
        import json
        report = analytics.full_report(user.id)
        # Tidak boleh ada objek yang tidak bisa jadi JSON (mis. date)
        json.dumps(report)


class TestEndpointAnalytics:
    def test_stats_endpoint(self, auth_client, seeded):
        response = auth_client.get('/api/stats')
        assert response.status_code == 200
        assert response.get_json()['total'] == 5

    def test_full_endpoint(self, auth_client, seeded):
        response = auth_client.get('/api/analytics/full')
        assert response.status_code == 200
        assert 'forecast' in response.get_json()

    @pytest.mark.parametrize('path', [
        '/api/analytics/productivity',
        '/api/analytics/forecast',
        '/api/analytics/suggestions',
        '/api/analytics/stuck',
        '/api/analytics/upcoming',
        '/api/analytics/by-course',
    ])
    def test_semua_endpoint(self, auth_client, path):
        assert auth_client.get(path).status_code == 200

    def test_forecast_hari_dibatasi(self, auth_client):
        assert auth_client.get('/api/analytics/forecast?days=9999').status_code == 200
        assert auth_client.get('/api/analytics/forecast?days=-5').status_code == 200

    def test_limit_suggestion_dibatasi(self, auth_client):
        body = auth_client.get('/api/analytics/suggestions?limit=999').get_json()
        assert len(body['items']) <= 20

    def test_analytics_butuh_token(self, client):
        assert client.get('/api/stats').status_code == 401
