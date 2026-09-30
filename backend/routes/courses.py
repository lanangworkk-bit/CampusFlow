"""Route untuk daftar mata kuliah.

Mata kuliah bersifat data referensi yang relatif tetap, jadi
hanya tersedia operasi baca (GET), tambah (POST), dan hapus (DELETE).
"""

from flask import Blueprint, jsonify, request

from db import get_db

courses_bp = Blueprint('courses', __name__, url_prefix='/api/courses')

VALID_SKS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)


@courses_bp.route('', methods=['GET'])
def get_courses():
    db = get_db()
    rows = db.execute('SELECT * FROM courses ORDER BY name ASC').fetchall()
    result = [dict(row) for row in rows]
    db.close()
    return jsonify(result)


@courses_bp.route('', methods=['POST'])
def create_course():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': 'Name is required'}), 400

    sks = data.get('sks', 3)
    if sks not in VALID_SKS:
        sks = 3

    db = get_db()
    cursor = db.execute(
        'INSERT INTO courses (name, code, sks, lecturer, day, time, room)'
        ' VALUES (?, ?, ?, ?, ?, ?, ?)',
        (
            data['name'].strip(),
            data.get('code', '').strip(),
            sks,
            data.get('lecturer', '').strip(),
            data.get('day', '').strip(),
            data.get('time', '').strip(),
            data.get('room', '').strip(),
        ),
    )
    db.commit()
    row = db.execute(
        'SELECT * FROM courses WHERE id = ?', (cursor.lastrowid,)
    ).fetchone()
    result = dict(row)
    db.close()
    return jsonify(result), 201


@courses_bp.route('/<int:course_id>', methods=['DELETE'])
def delete_course(course_id):
    db = get_db()
    db.execute('DELETE FROM courses WHERE id = ?', (course_id,))
    db.commit()
    db.close()
    return jsonify({'message': 'Course deleted'})
