/* ===================================================================
   CampusFlow - client side
   ===================================================================
   Aturan main di file ini:
   1. Semua data dari server. LocalStorage hanya untuk preferensi
      tampilan (dark mode), bukan untuk data tugas.
   2. Setiap request ke server memakai token JWT.
   3. Elemen HTML dibangun lewat textContent atau escapeHTML, bukan
      disisipkan mentah lewat innerHTML.
   =================================================================== */

const API = '';
const TOKEN_KEY = 'campusflow.token';
const USER_KEY = 'campusflow.user';
const THEME_KEY = 'campusflow.theme';

// --------------------------------------------------------------- state
const state = {
    token: localStorage.getItem(TOKEN_KEY),
    user: JSON.parse(localStorage.getItem(USER_KEY) || 'null'),
    tasks: [],
    courses: [],
    courseOptions: [],
    notes: [],
    taskPage: 1,
    coursePage: 1,
    perPage: 10,
    filters: { search: '', status: '', priority: '', courseId: '' },
    sort: { key: 'deadline', order: 'asc' },
    courseSort: { key: 'name', order: 'asc' },
    stats: null,
    currentFilter: 'all',
};

// --------------------------------------------------------------- util
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

/**
 * Terapkan nilai yang butuh CSSOM: lebar progress bar dan warna aksen.
 *
 * Nilai-nilai ini sengaja tidak ditulis sebagai atribut style="..." di
 * dalam HTML. Content-Security-Policy memakai style-src 'self' memblokir
 * atribut style, jadi progress bar akan selalu tampil kosong. Mengatur
 * element.style lewat JavaScript tidak diblokir CSP, jadi ini cara yang
 * aman sekaligus jalan.
 */
function applyInlineStyles(root) {
    root.querySelectorAll('[data-progress]').forEach((el) => {
        const pct = Math.max(0, Math.min(100, Number(el.dataset.progress) || 0));
        el.style.width = `${pct}%`;
    });
    root.querySelectorAll('[data-accent]').forEach((el) => {
        el.style.setProperty('--accent', el.dataset.accent);
    });
}

function escapeHTML(value) {
    const div = document.createElement('div');
    div.textContent = value == null ? '' : String(value);
    return div.innerHTML;
}

function formatDate(iso) {
    if (!iso) return '-';
    const days = ['Minggu', 'Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu'];
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun',
        'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'];
    const d = new Date(iso + 'T00:00:00');
    if (Number.isNaN(d.getTime())) return iso;
    return `${days[d.getDay()]}, ${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
}

function daysLeft(iso) {
    if (!iso) return null;
    const target = new Date(iso + 'T00:00:00');
    const now = new Date();
    now.setHours(0, 0, 0, 0);
    return Math.round((target - now) / 86400000);
}

function deadlineLabel(iso) {
    const left = daysLeft(iso);
    if (left === null) return { text: 'Tanpa tenggat', cls: 'muted' };
    if (left < 0) return { text: `Terlambat ${Math.abs(left)} hari`, cls: 'danger' };
    if (left === 0) return { text: 'Hari ini', cls: 'danger' };
    if (left === 1) return { text: 'Besok', cls: 'warn' };
    if (left <= 3) return { text: `${left} hari lagi`, cls: 'warn' };
    if (left <= 7) return { text: `${left} hari lagi`, cls: 'info' };
    return { text: `${left} hari lagi`, cls: 'muted' };
}

function toast(message, type = 'info') {
    const host = $('#toasts');
    if (!host) return;
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.setAttribute('role', type === 'error' ? 'alert' : 'status');
    el.textContent = message;
    host.appendChild(el);
    setTimeout(() => el.remove(), 4200);
}

// --------------------------------------------------------- networking
async function api(path, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    if (state.token) headers.Authorization = `Bearer ${state.token}`;

    let response;
    try {
        response = await fetch(API + path, { ...options, headers });
    } catch (err) {
        throw new Error('Tidak bisa menghubungi server. Coba jalankan ulang server.');
    }

    if (response.status === 401) {
        if (path.startsWith('/api/auth/')) {
            const body = await response.json().catch(() => ({}));
            throw new Error(body.error || 'Email atau password salah');
        }
        logout(true);
        throw new Error('Sesi habis. Silakan login lagi.');
    }

    const body = await response.json().catch(() => ({}));

    if (!response.ok) {
        if (response.status === 429) {
            throw new Error('Terlalu banyak permintaan. Tunggu sebentar.');
        }
        const err = new Error(body.error || `Error ${response.status}`);
        err.status = response.status;
        err.field = body.details && body.details.field;
        throw err;
    }

    return body;
}

// ------------------------------------------------------------- theme
function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_KEY, theme);
    const btn = $('#themeToggle');
    if (btn) btn.textContent = theme === 'dark' ? 'Light' : 'Dark';
}

// -------------------------------------------------------------- auth
async function login(username, password) {
    const data = await api('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
    });
    state.token = data.token;
    state.user = data.user;
    localStorage.setItem(TOKEN_KEY, data.token);
    localStorage.setItem(USER_KEY, JSON.stringify(data.user));
    return data;
}

async function register(payload) {
    return api('/api/auth/register', {
        method: 'POST',
        body: JSON.stringify(payload),
    });
}

function logout(silent = false) {
    state.token = null;
    state.user = null;
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    showAuth();
    if (!silent) toast('Kamu sudah keluar', 'info');
}

// ------------------------------------------------------------- render
function renderAuth() {
    const app = $('#app');
    const auth = $('#auth');
    if (state.token && state.user) {
        auth.classList.add('hidden');
        app.classList.remove('hidden');
        const who = $('#currentUser');
        if (who) who.textContent = state.user.full_name || state.user.username;
    } else {
        auth.classList.remove('hidden');
        app.classList.add('hidden');
    }
}

function showAuth() { renderAuth(); }

function renderTasks() {
    const host = $('#taskList');
    if (!host) return;

    if (state.tasks.length === 0) {
        host.innerHTML = `
            <div class="empty">
                <p>Belum ada tugas.</p>
                <p class="muted">Tambahkan tugas pertamamu di atas.</p>
            </div>`;
        renderTaskPagination();
        return;
    }

    host.innerHTML = state.tasks.map((task) => {
        const dl = deadlineLabel(task.deadline);
        const course = task.course_code
            ? `<span class="badge badge-course">${escapeHTML(task.course_code)}</span>`
            : '';
        const progressBar = task.status !== 'COMPLETED'
            ? `<div class="progress"><div class="progress-fill" data-progress="${Number(task.progress) || 0}"></div></div>
               <span class="progress-text">${task.progress}%</span>`
            : '';

        return `
        <article class="task-card" data-id="${task.id}">
            <div class="task-main">
                <div class="task-title-row">
                    <h3 class="task-title">${escapeHTML(task.title)}</h3>
                    ${course}
                </div>
                ${task.description ? `<p class="task-desc">${escapeHTML(task.description)}</p>` : ''}
                <div class="task-meta">
                    <span class="badge badge-${task.status.toLowerCase().replace(/\s/g, '-')}">${task.status}</span>
                    <span class="badge badge-priority-${task.priority.toLowerCase()}">${task.priority}</span>
                    <span class="deadline ${dl.cls}">${escapeHTML(dl.text)}</span>
                </div>
                ${progressBar}
            </div>
            <div class="task-actions">
                <button class="btn-icon" data-action="toggle" title="Tandai selesai">✓</button>
                <button class="btn-icon" data-action="edit" title="Edit">✎</button>
                <button class="btn-icon danger" data-action="delete" title="Hapus">🗑</button>
            </div>
        </article>`;
    }).join('');

    renderTaskPagination();
}

function renderTaskPagination() {
    const host = $('#taskPagination');
    if (!host) return;
    const total = state.taskTotal || 0;
    const pages = Math.max(1, Math.ceil(total / state.perPage));
    if (pages <= 1) { host.innerHTML = ''; return; }

    const buttons = [];
    buttons.push(`<button data-page="${state.taskPage - 1}" ${state.taskPage === 1 ? 'disabled' : ''}>‹</button>`);
    for (let p = 1; p <= pages; p++) {
        buttons.push(`<button data-page="${p}" class="${p === state.taskPage ? 'active' : ''}">${p}</button>`);
    }
    buttons.push(`<button data-page="${state.taskPage + 1}" ${state.taskPage === pages ? 'disabled' : ''}>›</button>`);
    host.innerHTML = buttons.join('');
}

function renderCourses() {
    const host = $('#courseList');
    if (!host) return;

    if (state.courses.length === 0) {
        host.innerHTML = '<div class="empty"><p>Tidak ada mata kuliah.</p></div>';
        renderCoursePagination();
        return;
    }

    const canDelete = state.user && state.user.role === 'admin';
    host.innerHTML = state.courses.map((c) => {
        const pct = c.task_count ? Math.round((c.task_done / c.task_count) * 100) : 0;
        return `
        <article class="course-card" data-accent="${escapeHTML(c.color || '#6366f1')}">
            <div class="course-head">
                <span class="course-code">${escapeHTML(c.code)}</span>
                ${pct === 100 ? '<span class="badge badge-completed">Selesai</span>' : ''}
            </div>
            <h3>${escapeHTML(c.name)}</h3>
            <p class="muted">${escapeHTML(c.lecturer || '-')}</p>
            <p class="muted small">${escapeHTML(c.day || '')} ${escapeHTML(c.time || '')} · ${escapeHTML(c.room || '')}</p>
            <div class="course-progress">
                <div class="progress"><div class="progress-fill" data-progress="${pct}"></div></div>
                <span class="small">${c.task_done}/${c.task_count} tugas</span>
            </div>
            ${canDelete ? `<button class="btn-sm danger" data-course-delete="${c.id}">Hapus</button>` : ''}
        </article>`;
    }).join('');
    applyInlineStyles(host);

    renderCoursePagination();
}

function renderCoursePagination() {
    const host = $('#coursePagination');
    if (!host) return;
    const total = state.courseTotal || 0;
    const pages = Math.max(1, Math.ceil(total / 6));
    if (pages <= 1) { host.innerHTML = ''; return; }

    const buttons = [];
    buttons.push(`<button data-cpage="${state.coursePage - 1}" ${state.coursePage === 1 ? 'disabled' : ''}>‹</button>`);
    for (let p = 1; p <= pages; p++) {
        buttons.push(`<button data-cpage="${p}" class="${p === state.coursePage ? 'active' : ''}">${p}</button>`);
    }
    buttons.push(`<button data-cpage="${state.coursePage + 1}" ${state.coursePage === pages ? 'disabled' : ''}>›</button>`);
    host.innerHTML = buttons.join('');
}

function renderNotes() {
    const host = $('#noteList');
    if (!host) return;
    if (state.notes.length === 0) {
        host.innerHTML = '<div class="empty"><p>Belum ada catatan.</p></div>';
        return;
    }
    host.innerHTML = state.notes.map((n) => `
        <div class="note note-${escapeHTML(n.color)} ${n.pinned ? 'pinned' : ''}" data-id="${n.id}">
            <p>${escapeHTML(n.text)}</p>
            <div class="note-actions">
                <button class="btn-icon" data-note-action="pin" title="Sematkan">📌</button>
                <button class="btn-icon danger" data-note-action="delete" title="Hapus">🗑</button>
            </div>
        </div>`).join('');
}

function renderCourseOptions() {
    const sel = $('#taskCourse');
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = '<option value="">Tanpa mata kuliah</option>' +
        state.courseOptions.map((c) =>
            `<option value="${c.id}">${escapeHTML(c.code)} — ${escapeHTML(c.name)}</option>`
        ).join('');
    if (current) sel.value = current;
}

function renderStats() {
    const host = $('#statsGrid');
    if (!host || !state.stats) return;
    const s = state.stats;

    host.innerHTML = `
        <div class="stat"><span class="stat-value">${s.total}</span><span class="stat-label">Total Tugas</span></div>
        <div class="stat ok"><span class="stat-value">${s.completed}</span><span class="stat-label">Selesai</span></div>
        <div class="stat danger"><span class="stat-value">${s.overdue}</span><span class="stat-label">Terlambat</span></div>
        <div class="stat info"><span class="stat-value">${s.in_progress}</span><span class="stat-label">Dikerjakan</span></div>
        <div class="stat"><span class="stat-value">${s.completion_rate}%</span><span class="stat-label">Tingkat Selesai</span></div>
        <div class="stat"><span class="stat-value">${s.average_progress}%</span><span class="stat-label">Rata-rata Progres</span></div>
    `;

    const ins = $('#insightPanel');
    if (ins) {
        const fg = state.forecast;
        const sug = state.suggestions || [];
        ins.innerHTML = `
            <h3>Insight</h3>
            ${fg ? `<p class="forecast forecast-${fg.verdict.toLowerCase()}">
                <strong>${fg.verdict}</strong> — ${escapeHTML(fg.message)}
                (${fg.tasks_due} tugas dalam ${fg.horizon_days} hari, beban ${fg.load_percent}%)
            </p>` : ''}
            ${sug.length ? `<p class="muted small">Prioritas berikutnya:</p><ol class="suggestions">${
                sug.slice(0, 3).map((t) => `<li>
                    <strong>${escapeHTML(t.title)}</strong>
                    <span class="muted small">skor ${t.urgency_score} · ${escapeHTML((t.reasons || []).join(', '))}</span>
                </li>`).join('')
            }</ol>` : '<p class="muted small">Tidak ada saran. Semua beres.</p>'}
        `;
    }
}

// -------------------------------------------------------------- data
async function loadTasks(page = state.taskPage) {
    const params = new URLSearchParams();
    params.set('page', page);
    params.set('per_page', state.perPage);
    params.set('sort', state.sort.key);
    params.set('order', state.sort.order);

    if (state.currentFilter !== 'all') params.set('status', state.currentFilter);
    if (state.filters.search) params.set('search', state.filters.search);
    if (state.filters.priority) params.set('priority', state.filters.priority);
    if (state.filters.courseId) params.set('course_id', state.filters.courseId);

    const data = await api(`/api/tasks?${params}`);
    state.tasks = data.items;
    state.taskTotal = data.total;
    state.taskPage = data.page;
    renderTasks();
}

async function loadCourses(page = state.coursePage) {
    const params = new URLSearchParams();
    params.set('page', page);
    params.set('per_page', 6);
    params.set('sort', state.courseSort.key);
    params.set('order', state.courseSort.order);

    const data = await api(`/api/courses?${params}`);
    state.courses = data.items;
    state.courseTotal = data.total;
    state.coursePage = data.page;
    renderCourses();
}

async function loadOptions() {
    state.courseOptions = await api('/api/courses/options');
    renderCourseOptions();
}

async function loadNotes() {
    state.notes = await api('/api/notes');
    renderNotes();
}

async function loadStats() {
    const [stats, suggestions, forecast] = await Promise.all([
        api('/api/stats'),
        api('/api/analytics/suggestions?limit=5'),
        api('/api/analytics/forecast?days=7'),
    ]);
    state.stats = stats;
    state.suggestions = suggestions.items;
    state.forecast = forecast;
    renderStats();
}

async function loadAll() {
    try {
        await loadOptions();
        await Promise.all([loadTasks(), loadCourses(), loadNotes(), loadStats()]);
    } catch (err) {
        toast(err.message, 'error');
    }
}

// -------------------------------------------------------------- task
async function submitTask(event) {
    event.preventDefault();
    const form = event.target;
    const payload = {
        title: $('#taskTitle').value.trim(),
        description: $('#taskDescription').value.trim(),
        deadline: $('#taskDeadline').value || null,
        priority: $('#taskPriority').value,
        course_id: $('#taskCourse').value ? Number($('#taskCourse').value) : null,
    };

    if (!payload.title) {
        toast('Judul tidak boleh kosong', 'error');
        return;
    }

    const editingId = form.dataset.editing;
    try {
        if (editingId) {
            await api(`/api/tasks/${editingId}`, {
                method: 'PUT', body: JSON.stringify(payload),
            });
            toast('Tugas diperbarui', 'success');
        } else {
            await api('/api/tasks', { method: 'POST', body: JSON.stringify(payload) });
            toast('Tugas ditambahkan', 'success');
        }
        form.reset();
        delete form.dataset.editing;
        $('#taskSubmit').textContent = 'Tambah';
        $('#taskCancel').classList.add('hidden');
        await Promise.all([loadTasks(), loadStats()]);
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function handleTaskAction(button) {
    const card = button.closest('.task-card');
    const id = card.dataset.id;
    const action = button.dataset.action;

    try {
        if (action === 'delete') {
            if (!confirm('Hapus tugas ini?')) return;
            await api(`/api/tasks/${id}`, { method: 'DELETE' });
            toast('Tugas dihapus', 'success');
            await Promise.all([loadTasks(), loadStats(), loadCourses()]);
        } else if (action === 'toggle') {
            const task = state.tasks.find((t) => t.id === Number(id));
            const next = task.status === 'COMPLETED' ? 'IN PROGRESS' : 'COMPLETED';
            await api(`/api/tasks/${id}`, {
                method: 'PUT', body: JSON.stringify({ status: next }),
            });
            await Promise.all([loadTasks(), loadStats(), loadCourses()]);
        } else if (action === 'edit') {
            const task = state.tasks.find((t) => t.id === Number(id));
            const form = $('#taskForm');
            form.dataset.editing = id;
            $('#taskTitle').value = task.title;
            $('#taskDescription').value = task.description || '';
            $('#taskDeadline').value = task.deadline || '';
            $('#taskPriority').value = task.priority;
            $('#taskCourse').value = task.course_id || '';
            $('#taskSubmit').textContent = 'Simpan';
            $('#taskCancel').classList.remove('hidden');
            $('#taskTitle').focus();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    } catch (err) {
        toast(err.message, 'error');
    }
}

// ------------------------------------------------------------- notes
async function addNote(event) {
    event.preventDefault();
    const input = $('#noteInput');
    const text = input.value.trim();
    if (!text) return;
    try {
        await api('/api/notes', { method: 'POST', body: JSON.stringify({ text }) });
        input.value = '';
        await loadNotes();
        toast('Catatan ditambahkan', 'success');
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function handleNoteAction(button) {
    const note = button.closest('.note');
    const id = note.dataset.id;
    try {
        if (button.dataset.noteAction === 'delete') {
            await api(`/api/notes/${id}`, { method: 'DELETE' });
            await loadNotes();
        } else {
            const current = state.notes.find((n) => n.id === Number(id));
            await api(`/api/notes/${id}`, {
                method: 'PUT', body: JSON.stringify({ pinned: !current.pinned }),
            });
            await loadNotes();
        }
    } catch (err) {
        toast(err.message, 'error');
    }
}

// -------------------------------------------------------------- auth ui
async function handleAuthSubmit(event) {
    event.preventDefault();
    const isRegister = event.target.id === 'registerForm';
    const errorBox = $('#authError');

    const payload = isRegister ? {
        username: $('#regUsername').value.trim().toLowerCase(),
        email: $('#regEmail').value.trim().toLowerCase(),
        password: $('#regPassword').value,
        full_name: $('#regName').value.trim() || null,
    } : {
        username: $('#loginUsername').value.trim().toLowerCase(),
        password: $('#loginPassword').value,
    };

    errorBox.textContent = '';
    try {
        if (isRegister) {
            const created = await register(payload);
            state.token = created.token;
            state.user = created.user;
            localStorage.setItem(TOKEN_KEY, created.token);
            localStorage.setItem(USER_KEY, JSON.stringify(created.user));
            toast('Akun dibuat. Selamat datang!', 'success');
        } else {
            await login(payload.username, payload.password);
            toast(`Halo, ${state.user.full_name || state.user.username}`, 'success');
        }
        renderAuth();
        await loadAll();
    } catch (err) {
        errorBox.textContent = err.message;
    }
}

// -------------------------------------------------------------- events
function bindEvents() {
    $('#taskForm').addEventListener('submit', submitTask);
    $('#noteForm').addEventListener('submit', addNote);

    $('#taskList').addEventListener('click', (e) => {
        const btn = e.target.closest('[data-action]');
        if (btn) handleTaskAction(btn);
    });
    $('#noteList').addEventListener('click', (e) => {
        const btn = e.target.closest('[data-note-action]');
        if (btn) handleNoteAction(btn);
    });
    $('#courseList').addEventListener('click', async (e) => {
        const btn = e.target.closest('[data-course-delete]');
        if (!btn) return;
        if (!confirm('Hapus mata kuliah ini? Tugas terkait tidak akan terhapus.')) return;
        try {
            await api(`/api/courses/${btn.dataset.courseDelete}?force=true`, { method: 'DELETE' });
            toast('Mata kuliah dihapus', 'success');
            await Promise.all([loadCourses(), loadOptions(), loadTasks()]);
        } catch (err) {
            toast(err.message, 'error');
        }
    });

    $('#taskPagination').addEventListener('click', (e) => {
        const btn = e.target.closest('[data-page]');
        if (btn && !btn.disabled) loadTasks(Number(btn.dataset.page));
    });
    $('#coursePagination').addEventListener('click', (e) => {
        const btn = e.target.closest('[data-cpage]');
        if (btn && !btn.disabled) loadCourses(Number(btn.dataset.cpage));
    });

    $('#searchInput').addEventListener('input', debounce((e) => {
        state.filters.search = e.target.value.trim();
        loadTasks(1);
    }, 350));

    $('#priorityFilter').addEventListener('change', (e) => {
        state.filters.priority = e.target.value;
        loadTasks(1);
    });
    $('#courseFilter').addEventListener('change', (e) => {
        state.filters.courseId = e.target.value;
        loadTasks(1);
    });

    $$('[data-filter]').forEach((btn) => {
        btn.addEventListener('click', () => {
            state.currentFilter = btn.dataset.filter;
            $$('[data-filter]').forEach((b) => b.classList.remove('active'));
            btn.classList.add('active');
            loadTasks(1);
        });
    });

    $('#sortSelect').addEventListener('change', (e) => {
        const [key, order] = e.target.value.split(':');
        state.sort = { key, order };
        loadTasks(1);
    });

    $('#courseSortSelect').addEventListener('change', (e) => {
        const [key, order] = e.target.value.split(':');
        state.courseSort = { key, order };
        loadCourses(1);
    });

    $('#taskCancel').addEventListener('click', () => {
        const form = $('#taskForm');
        form.reset();
        delete form.dataset.editing;
        $('#taskSubmit').textContent = 'Tambah';
        $('#taskCancel').classList.add('hidden');
    });

    $('#themeToggle').addEventListener('click', () => {
        const now = document.documentElement.getAttribute('data-theme');
        applyTheme(now === 'dark' ? 'light' : 'dark');
    });

    $('#logoutBtn').addEventListener('click', () => logout());

    $('#loginForm').addEventListener('submit', handleAuthSubmit);
    $('#registerForm').addEventListener('submit', handleAuthSubmit);

    $$('[data-auth-tab]').forEach((tab) => {
        tab.addEventListener('click', () => {
            const target = tab.dataset.authTab;
            $$('[data-auth-tab]').forEach((t) => t.classList.remove('active'));
            tab.classList.add('active');
            $('#loginPanel').classList.toggle('hidden', target !== 'login');
            $('#registerPanel').classList.toggle('hidden', target !== 'register');
            $('#authError').textContent = '';
        });
    });
}

function debounce(fn, wait) {
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), wait);
    };
}

// --------------------------------------------------------------- init
async function init() {
    applyTheme(localStorage.getItem(THEME_KEY) || 'light');
    bindEvents();
    renderAuth();

    if (state.token && state.user) {
        try {
            await api('/api/auth/me');
            await loadAll();
        } catch (err) {
            logout(true);
        }
    }
}

document.addEventListener('DOMContentLoaded', init);
