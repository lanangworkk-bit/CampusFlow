// CampusFlow - JavaScript Dasar untuk V1
// Fungsi: Interaksi sederhana untuk task management

// Data sementara (akan digantikan LocalStorage di fase selanjutnya)
const tasks = [
    { id: 1, title: 'Programming Assignment', description: 'Tugas pemrograman mingguan', deadline: '2026-10-01', priority: 'HIGH', status: 'TODO' },
    { id: 2, title: 'Mathematics Quiz', description: 'Quiz matematika mingguan', deadline: '2026-10-02', priority: 'MEDIUM', status: 'IN PROGRESS' },
];

// Fungsi menambah task
function addTask(title, description, deadline, priority) {
    const newTask = {
        id: Date.now(),
        title: title,
        description: description,
        deadline: deadline,
        priority: priority || 'MEDIUM',
        status: 'TODO'
    };
    tasks.push(newTask);
    renderTasks();
    showNotification('Task added successfully!');
}

// Fungsi merender task ke HTML
function renderTasks() {
    const tasksContainer = document.getElementById('tasks-container');
    if (!tasksContainer) return;
    
    tasksContainer.innerHTML = '';
    
    tasks.forEach(task => {
        const taskElement = document.createElement('div');
        taskElement.className = 'task-item p-3 rounded-lg mb-2 bg-white shadow-sm';
        taskElement.innerHTML = `
            <div class="flex items-start">
                <span class="flex-shrink-0 w-6 h-6 rounded-lg bg-${task.priority === 'HIGH' ? 'red' : task.priority === 'MEDIUM' ? 'yellow' : 'green'}-100 flex items-center justify-center mr-3">
                    <svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V5a2 2 0 012-2h2a2 2 0 012 2v14m-6 0l12 4L9 19z"></stroke-linecap></svg>
                </span>
                <div class="flex-1">
                    <p class="text-sm font-medium text-gray-900">${task.title}</p>
                    <p class="text-xs text-gray-500">${task.description}</p>
                </div>
                <span class="ml-2 text-xs rounded bg-${task.status === 'COMPLETED' ? 'green' : task.status === 'OVERDUE' ? 'red' : 'blue'}-100 px-2 py-0.5">${task.status}</span>
            </div>
        `;
        tasksContainer.appendChild(taskElement);
    });
}

// Fungsi menampilkan notifikasi
function showNotification(message) {
    alert(message);
}

// Event listeners saat DOM ready
document.addEventListener('DOMContentLoaded', () => {
    // Inisialisasi render saat halaman dimuat
    renderTasks();
    
    // Contoh: menambah task baru saat tombol diklik
    const addTaskBtn = document.getElementById('add-task-btn');
    if (addTaskBtn) {
        addTaskBtn.addEventListener('click', () => {
            const title = prompt('Masukkan judul task:');
            if (title) {
                addTask(title, 'Deskripsi task', '2026-10-15', 'MEDIUM');
            }
        });
    }
});
