from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static'),
)
CORS(app)

DATABASE = os.path.join(os.path.dirname(__file__), '..', 'database', 'campusflow.db')

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with app.app_context():
        db = get_db()
        schema_path = os.path.join(os.path.dirname(__file__), '..', 'database', 'schema.sql')
        with app.open_resource(schema_path, mode='r') as f:
            db.executescript(f.read())
        db.commit()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    db = get_db()
    tasks = db.execute('SELECT * FROM tasks ORDER BY deadline ASC').fetchall()
    return jsonify([dict(t) for t in tasks])

@app.route('/api/tasks', methods=['POST'])
def create_task():
    data = request.get_json()
    db = get_db()
    db.execute(
        'INSERT INTO tasks (title, description, deadline, priority, status) VALUES (?, ?, ?, ?, ?)',
        (data['title'], data.get('description'), data.get('deadline'), data.get('priority', 'MEDIUM'), data.get('status', 'TODO'))
    )
    db.commit()
    return jsonify({'message': 'Task created successfully'}), 201

@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    data = request.get_json()
    db = get_db()
    db.execute(
        'UPDATE tasks SET title = ?, description = ?, deadline = ?, priority = ?, status = ? WHERE id = ?',
        (data['title'], data.get('description'), data.get('deadline'), data.get('priority'), data.get('status'), task_id)
    )
    db.commit()
    return jsonify({'message': 'Task updated successfully'})

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    db = get_db()
    db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    db.commit()
    return jsonify({'message': 'Task deleted successfully'})

if __name__ == '__main__':
    init_db()
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=5002)
