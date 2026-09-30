"""Route untuk catatan cepat."""

from flask import Blueprint, jsonify, request

from db import get_db

notes_bp = Blueprint('notes', __name__, url_prefix='/api/notes')

MAX_NOTE_LENGTH = 2000


@notes_bp.route('', methods=['GET'])
def get_notes():
    db = get_db()
    rows = db.execute(
        'SELECT * FROM notes ORDER BY created_at DESC'
    ).fetchall()
    result = [dict(row) for row in rows]
    db.close()
    return jsonify(result)


@notes_bp.route('', methods=['POST'])
def create_note():
    data = request.get_json()
    if not data or not data.get('text'):
        return jsonify({'error': 'Text is required'}), 400

    text = data['text'].strip()
    if not text:
        return jsonify({'error': 'Text is required'}), 400
    if len(text) > MAX_NOTE_LENGTH:
        return jsonify(
            {'error': f'Catatan maksimal {MAX_NOTE_LENGTH} karakter'}
        ), 400

    db = get_db()
    cursor = db.execute('INSERT INTO notes (text) VALUES (?)', (text,))
    db.commit()
    row = db.execute(
        'SELECT * FROM notes WHERE id = ?', (cursor.lastrowid,)
    ).fetchone()
    result = dict(row)
    db.close()
    return jsonify(result), 201


@notes_bp.route('/<int:note_id>', methods=['DELETE'])
def delete_note(note_id):
    db = get_db()
    db.execute('DELETE FROM notes WHERE id = ?', (note_id,))
    db.commit()
    db.close()
    return jsonify({'message': 'Note deleted'})
