const API_URL = '/api/tasks';

document.addEventListener('DOMContentLoaded', function () {
    loadTasks();

    const form = document.getElementById('task-form');
    if (form) {
        form.addEventListener('submit', handleSubmit);
    }
});

function handleSubmit(event) {
    event.preventDefault();

    const form = event.target;
    const titleInput = document.getElementById('task-title');
    const errorEl = document.getElementById('form-error');

    const title = titleInput.value.trim();

    if (title === '') {
        errorEl.textContent = 'Judul tugas tidak boleh kosong.';
        return;
    }

    errorEl.textContent = '';

    const payload = {
        title: title,
        description: document.getElementById('task-description').value.trim(),
        deadline: document.getElementById('task-deadline').value,
        priority: document.getElementById('task-priority').value
    };

    fetch(API_URL, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
    })
        .then(function (response) {
            return response.json();
        })
        .then(function () {
            form.reset();
            loadTasks();
        })
        .catch(function (error) {
            console.error('Gagal menyimpan tugas:', error);
            errorEl.textContent = 'Terjadi kesalahan. Coba lagi.';
        });
}

function loadTasks() {
    fetch(API_URL)
        .then(function (response) {
            return response.json();
        })
        .then(function (tasks) {
            renderTasks(tasks);
            updateStats(tasks);
        })
        .catch(function (error) {
            console.error('Gagal memuat tasks:', error);
            const container = document.getElementById('tasks-container');
            if (container) {
                container.innerHTML = '<p class="text-sm text-red-500">Gagal memuat data. Pastikan server berjalan.</p>';
            }
        });
}

function renderTasks(tasks) {
    const container = document.getElementById('tasks-container');

    if (!container) {
        return;
    }

    container.innerHTML = '';

    if (tasks.length === 0) {
        container.innerHTML = '<p class="text-sm text-gray-500">Belum ada tugas.</p>';
        return;
    }

    tasks.forEach(function (task) {
        const item = document.createElement('div');
        item.className = 'task-item flex items-start px-2 py-2 rounded hover:bg-gray-50';
        item.innerHTML = `
            <div class="flex-1">
                <p class="text-sm font-medium text-gray-900">${task.title}</p>
                <p class="text-xs text-gray-500">Due: ${task.deadline || '-'}</p>
            </div>
            <span class="ml-2 text-xs rounded bg-${priorityColor(task.priority)}-100 px-2 py-0.5">${task.priority}</span>
        `;
        container.appendChild(item);
    });
}

function priorityColor(priority) {
    if (priority === 'URGENT' || priority === 'HIGH') return 'red';
    if (priority === 'MEDIUM') return 'yellow';
    return 'green';
}

function updateStats(tasks) {
    const today = new Date().toISOString().split('T')[0];

    const total = tasks.length;
    const completed = tasks.filter(function (t) {
        return t.status === 'COMPLETED';
    }).length;
    const pending = tasks.filter(function (t) {
        return t.status !== 'COMPLETED';
    }).length;
    const overdue = tasks.filter(function (t) {
        return t.deadline && t.deadline < today && t.status !== 'COMPLETED';
    }).length;

    const totalEl = document.getElementById('stat-total');
    const completedEl = document.getElementById('stat-completed');
    const pendingEl = document.getElementById('stat-pending');
    const overdueEl = document.getElementById('stat-overdue');

    if (totalEl) totalEl.textContent = total;
    if (completedEl) completedEl.textContent = completed;
    if (pendingEl) pendingEl.textContent = pending;
    if (overdueEl) overdueEl.textContent = overdue;
}
