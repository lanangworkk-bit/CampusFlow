from flask import Flask, request, jsonify, render_template
import sqlite3
import os

app = Flask(__name__, template_folder='../templates', static_folder='../static')

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'database', 'campusflow.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            deadline DATE,
            priority TEXT DEFAULT 'MEDIUM',
            status TEXT DEFAULT 'TODO',
            progress INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT,
            sks INTEGER DEFAULT 3,
            lecturer TEXT,
            day TEXT,
            time TEXT,
            room TEXT
        );

        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    db.commit()
    db.close()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    db = get_db()
    rows = db.execute('SELECT * FROM tasks ORDER BY deadline ASC').fetchall()
    result = [dict(row) for row in rows]
    db.close()
    return jsonify(result)


@app.route('/api/tasks', methods=['POST'])
def create_task():
    data = request.get_json()
    if not data or not data.get('title'):
        return jsonify({'error': 'Title is required'}), 400

    db = get_db()
    cursor = db.execute(
        'INSERT INTO tasks (title, description, deadline, priority) VALUES (?, ?, ?, ?)',
        (data['title'], data.get('description', ''), data.get('deadline'), data.get('priority', 'MEDIUM'))
    )
    db.commit()
    task_id = cursor.lastrowid
    row = db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
    result = dict(row)
    db.close()
    return jsonify(result), 201


@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    db = get_db()
    existing = db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
    if existing is None:
        db.close()
        return jsonify({'error': 'Task not found'}), 404

    title = data.get('title', existing['title'])
    description = data.get('description', existing['description'])
    deadline = data.get('deadline', existing['deadline'])
    priority = data.get('priority', existing['priority'])
    status = data.get('status', existing['status'])
    progress = data.get('progress', existing['progress'])

    if status == 'COMPLETED':
        progress = 100
    elif progress == 100 and status != 'COMPLETED':
        progress = 0

    db.execute(
        'UPDATE tasks SET title = ?, description = ?, deadline = ?, priority = ?, status = ?, progress = ? WHERE id = ?',
        (title, description, deadline, priority, status, progress, task_id)
    )
    db.commit()
    row = db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
    result = dict(row)
    db.close()
    return jsonify(result)


@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    db = get_db()
    db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    db.commit()
    db.close()
    return jsonify({'message': 'Task deleted'})


@app.route('/api/courses', methods=['GET'])
def get_courses():
    db = get_db()
    rows = db.execute('SELECT * FROM courses ORDER BY name ASC').fetchall()
    result = [dict(row) for row in rows]
    db.close()
    return jsonify(result)


@app.route('/api/courses', methods=['POST'])
def create_course():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': 'Name is required'}), 400

    db = get_db()
    cursor = db.execute(
        'INSERT INTO courses (name, code, sks, lecturer, day, time, room) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (
            data['name'],
            data.get('code', ''),
            data.get('sks', 3),
            data.get('lecturer', ''),
            data.get('day', ''),
            data.get('time', ''),
            data.get('room', ''),
        )
    )
    db.commit()
    course_id = cursor.lastrowid
    row = db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
    result = dict(row)
    db.close()
    return jsonify(result), 201


@app.route('/api/courses/<int:course_id>', methods=['DELETE'])
def delete_course(course_id):
    db = get_db()
    db.execute('DELETE FROM courses WHERE id = ?', (course_id,))
    db.commit()
    db.close()
    return jsonify({'message': 'Course deleted'})


@app.route('/api/reset', methods=['POST'])
def reset_all():
    """Hapus semua data (untuk tombol Reset Data)."""
    db = get_db()
    db.executescript('DELETE FROM tasks; DELETE FROM notes; DELETE FROM courses;')
    db.commit()
    db.close()
    return jsonify({'message': 'All data deleted'})


@app.route('/api/notes', methods=['GET'])
def get_notes():
    db = get_db()
    rows = db.execute('SELECT * FROM notes ORDER BY created_at DESC').fetchall()
    result = [dict(row) for row in rows]
    db.close()
    return jsonify(result)


@app.route('/api/notes', methods=['POST'])
def create_note():
    data = request.get_json()
    if not data or not data.get('text'):
        return jsonify({'error': 'Text is required'}), 400

    db = get_db()
    cursor = db.execute('INSERT INTO notes (text) VALUES (?)', (data['text'],))
    db.commit()
    note_id = cursor.lastrowid
    row = db.execute('SELECT * FROM notes WHERE id = ?', (note_id,)).fetchone()
    result = dict(row)
    db.close()
    return jsonify(result), 201


@app.route('/api/notes/<int:note_id>', methods=['DELETE'])
def delete_note(note_id):
    db = get_db()
    db.execute('DELETE FROM notes WHERE id = ?', (note_id,))
    db.commit()
    db.close()
    return jsonify({'message': 'Note deleted'})


if __name__ == '__main__':
    init_db()
    app.run(debug=True, use_reloader=False, port=5002)
