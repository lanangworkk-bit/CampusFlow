"""Seed data realistis untuk menguji endpoint /api/stats.

Jalankan:
    python3 backend/seed_test_data.py

Script ini membaca id yang sebenarnya dari server, bukan menebak.
AUTOINCREMENT membuat nomor id tidak pernah terulang, jadi id di
database lokal bisa berbeda dari mesin ke mesin.
"""

import json
import urllib.error
import urllib.request

BASE = 'http://localhost:5002'


def call(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={'Content-Type': 'application/json'},
    )
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        print(f'GAGAL {method} {path}: {error.code} {error.read().decode()}')
        raise


call('POST', '/api/reset')

COURSES = [
    {'name': 'Pemrograman Dasar', 'code': 'IF101', 'sks': 3,
     'lecturer': 'Budi Santoso, S.T.', 'day': 'Senin',
     'time': '08:00 - 10:30', 'room': 'Lab Informatika'},
    {'name': 'Basis Data', 'code': 'IF103', 'sks': 4,
     'lecturer': 'Andi Wijaya, S.Kom.', 'day': 'Kamis',
     'time': '13:00 - 16:00', 'room': 'Lab Data'},
    {'name': 'Jaringan Komputer', 'code': 'IF201', 'sks': 3,
     'lecturer': 'Rina Kusuma, S.T.', 'day': 'Rabu',
     'time': '10:00 - 12:30', 'room': 'Lab Jaringan'},
]

# Peta nama -> id asli dari server
course_ids = {}
for payload in COURSES:
    created = call('POST', '/api/courses', payload)
    course_ids[created['name']] = created['id']

prog = course_ids['Pemrograman Dasar']
basis = course_ids['Basis Data']
jaringan = course_ids['Jaringan Komputer']

TASKS = [
    {'title': 'Tugas 1 Kalkulator', 'description': 'Program kalkulator sederhana',
     'deadline': '2026-09-25', 'priority': 'URGENT', 'course_id': prog},
    {'title': 'Tugas 2 Array', 'description': 'Latihan array 1 dimensi',
     'deadline': '2026-09-30', 'priority': 'HIGH', 'course_id': prog},
    {'title': 'Tugas 3 Fungsi', 'description': 'Fungsi dan rekursi',
     'deadline': '2026-10-12', 'priority': 'MEDIUM', 'course_id': prog},
    {'title': 'Praktikum SQL', 'description': 'Buat query JOIN',
     'deadline': '2026-10-02', 'priority': 'HIGH', 'course_id': basis},
    {'title': 'Slide Normalisasi', 'description': 'NF1 sampai NF3',
     'deadline': '2026-10-04', 'priority': 'MEDIUM', 'course_id': basis},
    {'title': 'Laporan Praktikum', 'description': 'Dokumentasi praktikum',
     'deadline': '2026-10-08', 'priority': 'MEDIUM', 'course_id': basis},
    {'title': 'Konfigurasi Router', 'description': 'Setup routing static',
     'deadline': '2026-10-15', 'priority': 'LOW', 'course_id': jaringan},
    {'title': 'Tugas tanpa deadline', 'description': 'Belum ditentukan',
     'priority': 'LOW', 'course_id': prog},
    {'title': 'Tugas pribadi', 'description': 'Di luar mata kuliah',
     'priority': 'MEDIUM'},
]

created_ids = []
for payload in TASKS:
    created = call('POST', '/api/tasks', payload)
    created_ids.append(created['id'])

# Tandai sebagian sebagai selesai supaya completion_rate tidak 0
for task_id in created_ids[2:4]:
    call('PUT', f'/api/tasks/{task_id}', {'status': 'COMPLETED'})

# Beri progress sebagian
call('PUT', f"/api/tasks/{created_ids[1]}", {'progress': 50, 'status': 'IN PROGRESS'})

NOTES = [
    'Bikin query JOIN buat tugas Basis Data',
    'Kumpulkan slide normalisasi sebelum Jumat',
    'Tanya dosen soal konfigurasi router',
]
for text in NOTES:
    call('POST', '/api/notes', {'text': text})

print(f"Siap: {len(COURSES)} mata kuliah, {len(TASKS)} task, {len(NOTES)} catatan")
print(f"ID mata kuliah: {course_ids}")
print(f"ID task: {created_ids}")
print(f"\nBuka {BASE}/api/stats untuk melihat hasilnya")
