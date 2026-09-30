// ============================================
// CampusFlow - Semester 2 Version
// HTML + Tailwind CSS + JavaScript + Flask + SQLite
// ============================================

// --------------------------------------------
// 1. API Layer (menggantikan LocalStorage)
// --------------------------------------------
// Data TIDAK lagi disimpan di browser.
// Data diambil dari server lewat fetch() (HTTP request),
// lalu disimpan sementara di memory (cache) supaya
// kode di bawah tidak berubah banyak.
//
//   Browser  --fetch()-->  Flask  --sqlite3-->  database
//
// Catatan: darkMode tetap di LocalStorage karena itu
// preferensi TAMPILAN per perangkat, bukan data.

// Cache di memory
let cachedTasks = [];
let cachedCourses = [];
let cachedNotes = [];

// Pengaman: kalau server error, jangan diamkan -
// tampilkan pesannya supaya mudah di-debug.
function handleApiError(error) {
  console.error("API error:", error);
  alert("Gagal terhubung ke server. Pastikan Flask berjalan di port 5002.");
}

// Fungsi inti untuk semua request ke server.
function api(url, options) {
  return fetch(url, options).then(function (response) {
    if (!response.ok) {
      return response.json().then(function (data) {
        throw new Error(data.error || "HTTP " + response.status);
      });
    }
    return response.json();
  });
}

// Server pakai snake_case (created_at),
// frontend lebih nyaman pakai camelCase (createdAt).
function normalizeTask(task) {
  return {
    id: task.id,
    title: task.title,
    description: task.description || "",
    deadline: task.deadline || "",
    priority: task.priority,
    status: task.status,
    progress: task.progress,
    courseId: task.course_id || null,
    courseName: task.course_name || "",
    createdAt: task.created_at,
  };
}

function normalizeNote(note) {
  return {
    id: note.id,
    text: note.text,
    createdAt: new Date(note.created_at).toLocaleDateString("id-ID"),
  };
}

// Baca semua data dari server sekaligus.
function loadFromServer() {
  return Promise.all([
    api("/api/tasks").catch(function (error) {
      handleApiError(error);
      return [];
    }),
    api("/api/courses").catch(function (error) {
      handleApiError(error);
      return [];
    }),
    api("/api/notes").catch(function (error) {
      handleApiError(error);
      return [];
    }),
  ]).then(function (results) {
    cachedTasks = results[0].map(normalizeTask);
    cachedCourses = results[1];
    cachedNotes = results[2].map(normalizeNote);
  });
}

// Pembacaan data (synchronous, dari cache)
const getTasks = () => cachedTasks;
const getCourses = () => cachedCourses;
const getNotes = () => cachedNotes;

// Operasi tulis ke server
function apiCreateTask(data) {
  return api("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

function apiUpdateTask(id, data) {
  return api("/api/tasks/" + id, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

function apiDeleteTask(id) {
  return api("/api/tasks/" + id, { method: "DELETE" });
}

function apiCreateCourse(data) {
  return api("/api/courses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

function apiDeleteCourse(id) {
  return api("/api/courses/" + id, { method: "DELETE" });
}

function apiResetAll() {
  return api("/api/reset", { method: "POST" });
}

function apiCreateNote(data) {
  return api("/api/notes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

function apiDeleteNote(id) {
  return api("/api/notes/" + id, { method: "DELETE" });
}

// --------------------------------------------
// 1b. LocalStorage Helpers (hanya untuk settings)
// --------------------------------------------

const STORAGE_KEYS = {
  settings: "campusflow_settings",
};

function loadFromStorage(key, fallback) {
  const raw = localStorage.getItem(key);
  if (raw === null) {
    return fallback;
  }
  try {
    return JSON.parse(raw);
  } catch (error) {
    console.warn("Data rusak, menggunakan default:", key);
    return fallback;
  }
}

function saveToStorage(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

const getSettings = () =>
  loadFromStorage(STORAGE_KEYS.settings, { darkMode: false });
const saveSettings = (data) => saveToStorage(STORAGE_KEYS.settings, data);

// --------------------------------------------
// 2. Utilitas
// --------------------------------------------

// Tanggal hari ini dalam format YYYY-MM-DD.
// locally harus 2 digit (09, bukan 9)
function todayISO() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return now.getFullYear() + "-" + month + "-" + day;
}

// OVERDUE bukan disimpan di database.
// Status ini dihitung setiap render berdasarkan tanggal.
function getEffectiveStatus(task) {
  if (task.status === "COMPLETED") {
    return "COMPLETED";
  }
  if (task.deadline && task.deadline < todayISO()) {
    return "OVERDUE";
  }
  return task.status;
}

function daysUntil(dateISO) {
  if (!dateISO) return null;
  const target = new Date(dateISO + "T00:00:00");
  const today = new Date(todayISO() + "T00:00:00");
  return Math.round((target - today) / 86400000);
}

function formatDeadline(dateISO) {
  const diff = daysUntil(dateISO);
  if (diff === null) return "Tanpa deadline";
  if (diff === 0) return "Hari ini";
  if (diff === 1) return "Besok";
  if (diff < 0) return "Terlambat " + Math.abs(diff) + " hari";
  if (diff <= 7) return diff + " hari lagi";
  return dateISO;
}

function escapeHTML(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

const PRIORITIES = ["LOW", "MEDIUM", "HIGH", "URGENT"];

const priorityColor = (p) => {
  if (p === "URGENT") return "red";
  if (p === "HIGH") return "orange";
  if (p === "MEDIUM") return "yellow";
  return "green";
};

const statusColor = (s) => {
  if (s === "COMPLETED") return "green";
  if (s === "OVERDUE") return "red";
  if (s === "IN PROGRESS") return "blue";
  return "gray";
};

// --------------------------------------------
// 3. Data Awal (hanya sekali, jika storage kosong)
// --------------------------------------------

// --------------------------------------------
// 3. Data Awal (disimpan ke server, hanya sekali)
// --------------------------------------------
// Sekarang data awal dikirim ke server lewat API,
// bukan disimpan di LocalStorage.
// Kalau database masih kosong, isi dengan contoh.
// Kalau sudah ada, lewati saja.

function seedIfEmpty() {
  if (getTasks().length === 0) {
    const sample = [
      {
        title: "Tugas Pemrograman Dasar",
        description: "Buat program kalkulator sederhana",
        deadline: offsetDate(2),
        priority: "HIGH",
      },
      {
        title: "Laporan Praktikum Matematika",
        description: "Laporan modul integral",
        deadline: offsetDate(6),
        priority: "MEDIUM",
      },
      {
        title: "Presentasi Basis Data",
        description: "Slide normalisasi relasi",
        deadline: offsetDate(-2),
        priority: "URGENT",
      },
    ];

    // Kirim satu per satu, lalu render setelah semua selesai
    return Promise.all(sample.map(apiCreateTask))
      .then(function (created) {
        created.forEach(function (task) {
          cachedTasks.push(normalizeTask(task));
        });
      })
      .then(function () {
        cachedTasks[0].status = "IN PROGRESS";
        cachedTasks[0].progress = 40;
        cachedTasks[2].progress = 10;
        return Promise.all([
          apiUpdateTask(cachedTasks[0].id, {
            status: "IN PROGRESS",
            progress: 40,
          }),
          apiUpdateTask(cachedTasks[2].id, { progress: 10 }),
        ]);
      })
      .then(function () {
        return loadFromServer();
      });
  }
}

function seedCoursesIfEmpty() {
  if (getCourses().length > 0) return Promise.resolve();

  const sample = [
    {
      name: "Pemrograman Dasar",
      code: "IF101",
      sks: 3,
      lecturer: "Budi Santoso, S.T.",
      day: "Senin",
      time: "08:00 - 10:30",
      room: "Lab Informatika",
    },
    {
      name: "Matematika Diskret",
      code: "IF102",
      sks: 3,
      lecturer: "Siti Aminah, S.Si.",
      day: "Selasa",
      time: "10:00 - 12:30",
      room: "Ruang 301",
    },
    {
      name: "Basis Data",
      code: "IF103",
      sks: 4,
      lecturer: "Andi Wijaya, S.Kom.",
      day: "Kamis",
      time: "13:00 - 16:00",
      room: "Lab Data",
    },
  ];

  return Promise.all(sample.map(apiCreateCourse))
    .then(function (created) {
      cachedCourses = created;
    })
    .catch(handleApiError);
}

function offsetDate(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return d.getFullYear() + "-" + month + "-" + day;
}

// --------------------------------------------
// 4. Render Tasks
// --------------------------------------------
// Search/filter/sort sekarang dikirim ke SERVER lewat query parameter.
// Server yang memfilter, lalu hasilnya yang di-render.
//
// Debounce: menunggu 300ms setelah user berhenti mengetik.
// Tanpa ini, ketik "flutter" = 7 request (f, fl, flu, flut, ...).
// Dengan debounce, cukup 1 request.
let filterTimer = null;
let searchCache = "";
let currentFilters = {
  search: "",
  status: "all",
  priority: "all",
  sort: "deadline",
  order: "asc",
};

// Hitung ulang daftar dari server sesuai filter saat ini.
function applyFilters(immediate) {
  clearTimeout(filterTimer);
  filterTimer = setTimeout(refreshFromServer, immediate ? 0 : 300);
}

// Minta daftar task ke server dengan filter yang sedang aktif.
function refreshFromServer() {
  const params = new URLSearchParams();
  if (currentFilters.search) params.set("search", currentFilters.search);
  if (currentFilters.status !== "all") params.set("status", currentFilters.status);
  if (currentFilters.priority !== "all")
    params.set("priority", currentFilters.priority);
  params.set("sort", currentFilters.sort);
  params.set("order", currentFilters.order);

  return api("/api/tasks?" + params.toString())
    .then(function (tasks) {
      cachedTasks = tasks.map(normalizeTask);
      renderTasks();
      renderStats();
      renderAnalytics();
    })
    .catch(handleApiError);
}

function renderTasks() {
  const listEl = document.getElementById("task-list");
  const tasks = getTasks();

  if (tasks.length === 0) {
    listEl.innerHTML = emptyStateHTML();
    return;
  }

  listEl.innerHTML = "";
  tasks.forEach(function (task) {
    listEl.insertAdjacentHTML("beforeend", taskCardHTML(task));
  });
}

function emptyStateHTML() {
  return `
        <div class="text-center py-12">
            <p class="text-4xl mb-2">📝</p>
            <p class="text-sm text-gray-500 dark:text-gray-400">Belum ada tugas.</p>
            <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Tambahkan tugas pertama kamu di atas.</p>
        </div>
    `;
}

function taskCardHTML(task) {
  const status = getEffectiveStatus(task);
  const deadline = formatDeadline(task.deadline);
  const isLate = status === "OVERDUE";

  return `
        <div class="border border-gray-200 dark:border-gray-700 rounded-lg p-4 bg-white dark:bg-gray-800">
            <div class="flex items-start gap-3">
                <input
                    type="checkbox"
                    data-action="toggle"
                    data-id="${task.id}"
                    ${status === "COMPLETED" ? "checked" : ""}
                    class="mt-1 h-4 w-4"
                    aria-label="Tandai selesai: ${escapeHTML(task.title)}"
                >
                <div class="flex-1 min-w-0">
                    <p class="text-sm font-medium ${status === "COMPLETED" ? "line-through text-gray-400" : ""}">
                        ${escapeHTML(task.title)}
                    </p>
                    <p class="text-xs text-gray-500 dark:text-gray-400">
                        ${escapeHTML(task.description || "-")}
                    </p>
                    <p class="text-xs mt-1 ${isLate ? "text-red-500" : "text-gray-500 dark:text-gray-400"}">
                        📅 ${deadline}${isLate ? " - TERLAMBAT" : ""}
                    </p>
                    ${
                      task.courseName
                        ? `<p class="text-xs mt-1 text-indigo-600 dark:text-indigo-400">
                               📚 ${escapeHTML(task.courseName)}
                           </p>`
                        : ""
                    }

                    <div class="mt-3">
                        <div class="flex justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
                            <span>Progress</span>
                            <span data-progress-label data-id="${task.id}">${task.progress || 0}%</span>
                        </div>
                        <div class="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
                            <div data-progress-bar data-id="${task.id}" class="progress-fill bg-blue-500 h-full rounded-full" style="width: ${task.progress || 0}%"></div>
                        </div>
                        <input
                            type="range"
                            min="0" max="100" step="10"
                            value="${task.progress || 0}"
                            data-action="progress"
                            data-id="${task.id}"
                            class="w-full mt-2"
                            aria-label="Progress: ${escapeHTML(task.title)}"
                        >
                    </div>
                </div>
                <div class="flex flex-col items-end gap-2">
                    <span class="text-xs rounded px-2 py-0.5 bg-${statusColor(status)}-100 text-${statusColor(status)}-700">
                        ${status}
                    </span>
                    <span class="text-xs rounded px-2 py-0.5 bg-${priorityColor(task.priority)}-100 text-${priorityColor(task.priority)}-700">
                        ${task.priority}
                    </span>
                    <div class="flex gap-1">
                        <button data-action="edit" data-id="${task.id}" class="text-xs text-blue-600 hover:underline">Edit</button>
                        <button data-action="delete" data-id="${task.id}" class="text-xs text-red-500 hover:underline">Hapus</button>
                    </div>
                </div>
            </div>
        </div>
    `;
}

// --------------------------------------------
// 5. Task Actions
// --------------------------------------------

function addTask(event) {
  event.preventDefault();

  const titleInput = document.getElementById("task-title");
  const errorEl = document.getElementById("form-error");
  const title = titleInput.value.trim();

  if (title === "") {
    errorEl.textContent = "Judul tugas tidak boleh kosong.";
    titleInput.focus();
    return;
  }

  errorEl.textContent = "";

  const newTask = {
    title: title,
    description: document.getElementById("task-description").value.trim(),
    deadline: document.getElementById("task-deadline").value,
    priority: document.getElementById("task-priority").value,
    // String kosong berarti tidak ada mata kuliah (NULL di server).
    course_id: document.getElementById("task-course").value || null,
  };

  apiCreateTask(newTask)
    .then(function () {
      event.target.reset();
      refresh();
    })
    .catch(handleApiError);
}

function toggleTask(id) {
  const task = getTasks().find(function (t) {
    return t.id == id;
  });

  if (!task) return;

  const nextStatus = task.status === "COMPLETED" ? "TODO" : "COMPLETED";

  apiUpdateTask(id, { status: nextStatus }).then(refresh).catch(handleApiError);
}

function updateProgress(id, value) {
  const task = getTasks().find(function (t) {
    return t.id == id;
  });

  if (!task) return;

  // Update tampilan lebih dulu supaya slider tidak lag
  task.progress = Number(value);

  if (task.progress === 100) {
    task.status = "COMPLETED";
  } else if (task.status === "COMPLETED") {
    task.status = "IN PROGRESS";
  }

  // Jangan render ulang seluruh list, karena slider yang sedang
  // di-drag akan ikut hilang. Update langsung elemennya saja.
  const bar = document.querySelector(
    '[data-progress-bar][data-id="' + id + '"]',
  );
  const label = document.querySelector(
    '[data-progress-label][data-id="' + id + '"]',
  );

  if (bar) bar.style.width = task.progress + "%";
  if (label) label.textContent = task.progress + "%";

  renderStats();
  renderAnalytics();

  // Kirim ke server (tanpa render ulang list)
  apiUpdateTask(id, { progress: task.progress, status: task.status }).catch(
    handleApiError,
  );
}

function deleteTask(id) {
  const task = getTasks().find(function (t) {
    return t.id == id;
  });

  if (!task) return;
  if (!window.confirm('Hapus tugas "' + task.title + '"?')) return;

  apiDeleteTask(id).then(refresh).catch(handleApiError);
}

function updateStatus(id, newStatus) {
  const task = getTasks().find(function (t) {
    return t.id == id;
  });

  if (!task) return;

  apiUpdateTask(id, { status: newStatus }).then(refresh).catch(handleApiError);
}

// --------------------------------------------
// 6. Edit Modal
// --------------------------------------------

function openEditModal(id) {
  const task = getTasks().find(function (t) {
    return t.id == id;
  });
  if (!task) return;

  document.getElementById("edit-id").value = task.id;
  document.getElementById("edit-title").value = task.title;
  document.getElementById("edit-description").value = task.description || "";
  document.getElementById("edit-deadline").value = task.deadline || "";
  document.getElementById("edit-priority").value = task.priority;
  document.getElementById("edit-course").value = task.courseId || "";

  const statusSelect =
    document.getElementById("edit-status") || createStatusSelect();
  statusSelect.value = task.status;

  const modal = document.getElementById("edit-modal");
  modal.classList.remove("hidden");
  modal.classList.add("flex");
  document.getElementById("edit-title").focus();
}

function createStatusSelect() {
  const select = document.createElement("select");
  select.id = "edit-status";
  select.setAttribute("aria-label", "Status");
  select.className = "input w-full";
  ["TODO", "IN PROGRESS", "COMPLETED"].forEach(function (s) {
    const opt = document.createElement("option");
    opt.value = s;
    opt.textContent = s;
    select.appendChild(opt);
  });
  document.getElementById("edit-priority").parentNode.appendChild(select);
  return select;
}

function closeEditModal() {
  const modal = document.getElementById("edit-modal");
  modal.classList.add("hidden");
  modal.classList.remove("flex");
}

function saveEdit(event) {
  event.preventDefault();

  const id = Number(document.getElementById("edit-id").value);
  const title = document.getElementById("edit-title").value.trim();

  if (title === "") {
    window.alert("Judul tidak boleh kosong.");
    return;
  }

  const task = getTasks().find(function (t) {
    return t.id === id;
  });
  if (!task) return;

  const changes = {
    title: title,
    description: document.getElementById("edit-description").value.trim(),
    deadline: document.getElementById("edit-deadline").value,
    priority: document.getElementById("edit-priority").value,
    course_id: document.getElementById("edit-course").value || null,
  };

  const statusSelect = document.getElementById("edit-status");
  if (statusSelect) {
    changes.status = statusSelect.value;
  }

  apiUpdateTask(id, changes)
    .then(function () {
      closeEditModal();
      refresh();
    })
    .catch(handleApiError);
}

// --------------------------------------------
// 7. Stats & Analytics
// --------------------------------------------

function renderStats() {
  const tasks = getTasks();

  const completed = tasks.filter(function (t) {
    return getEffectiveStatus(t) === "COMPLETED";
  }).length;

  const overdue = tasks.filter(function (t) {
    return getEffectiveStatus(t) === "OVERDUE";
  }).length;

  document.getElementById("stat-total").textContent = tasks.length;
  document.getElementById("stat-completed").textContent = completed;
  document.getElementById("stat-pending").textContent =
    tasks.length - completed - overdue;
  document.getElementById("stat-overdue").textContent = overdue;
}

function renderAnalytics() {
  const tasks = getTasks();

  const completed = tasks.filter(function (t) {
    return getEffectiveStatus(t) === "COMPLETED";
  }).length;

  const rate =
    tasks.length === 0 ? 0 : Math.round((completed / tasks.length) * 100);

  document.getElementById("completion-bar").style.width = rate + "%";
  document.getElementById("completion-label").textContent = rate + "%";

  const breakdown = document.getElementById("priority-breakdown");
  breakdown.innerHTML = "";

  PRIORITIES.forEach(function (priority) {
    const count = tasks.filter(function (t) {
      return t.priority === priority;
    }).length;

    const li = document.createElement("li");
    li.className = "flex justify-between";
    li.innerHTML = `
            <span class="inline-flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-${priorityColor(priority)}-500"></span>
                ${priority}
            </span>
            <span class="font-medium">${count}</span>
        `;
    breakdown.appendChild(li);
  });
}

// --------------------------------------------
// 8. Courses
// --------------------------------------------

// Isi dropdown "Mata Kuliah" di form tambah dan form edit.
// Dua dropdown memakai daftar yang sama, jadi cukup dibangun sekali.
function renderCourseOptions() {
  const options = getCourses()
    .map(function (course) {
      const label = course.code
        ? course.name + " (" + course.code + ")"
        : course.name;
      return `<option value="${course.id}">${escapeHTML(label)}</option>`;
    })
    .join("");

  const html = '<option value="">Tanpa mata kuliah</option>' + options;

  ["task-course", "edit-course"].forEach(function (id) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
  });
}

function renderCourses() {
  const listEl = document.getElementById("course-list");
  const courses = getCourses();

  renderCourseOptions();

  if (courses.length === 0) {
    listEl.innerHTML =
      '<p class="text-sm text-gray-500 dark:text-gray-400">Belum ada mata kuliah.</p>';
    return;
  }

  listEl.innerHTML = "";

  courses.forEach(function (course) {
    listEl.insertAdjacentHTML(
      "beforeend",
      `
            <div class="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                <div class="flex justify-between items-start">
                    <div>
                        <p class="font-medium text-sm">${escapeHTML(course.name)}</p>
                        <p class="text-xs text-gray-500 dark:text-gray-400">${escapeHTML(course.code)} - ${course.sks} SKS</p>
                    </div>
                    <span class="text-xs bg-indigo-100 text-indigo-700 rounded px-2 py-0.5">${course.sks} SKS</span>
                </div>
                <p class="text-xs text-gray-500 dark:text-gray-400 mt-2">${escapeHTML(course.lecturer)}</p>
                <p class="text-xs text-gray-500 dark:text-gray-400">${escapeHTML(course.day)} - ${escapeHTML(course.time)}</p>
                <p class="text-xs text-gray-400 dark:text-gray-500">${escapeHTML(course.room)}</p>
            </div>
        `,
    );
  });
}

// --------------------------------------------
// 9. Calendar
// --------------------------------------------

let currentMonth = new Date().getMonth();
let currentYear = new Date().getFullYear();

function renderCalendar() {
  const grid = document.getElementById("calendar-grid");
  const titleEl = document.getElementById("calendar-title");

  const monthNames = [
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
  ];

  titleEl.textContent = monthNames[currentMonth] + " " + currentYear;

  const firstDay = new Date(currentYear, currentMonth, 1).getDay();
  const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();

  const tasks = getTasks();
  const deadlinesByDate = {};
  tasks.forEach(function (task) {
    if (task.deadline) {
      if (!deadlinesByDate[task.deadline]) deadlinesByDate[task.deadline] = 0;
      deadlinesByDate[task.deadline]++;
    }
  });

  grid.innerHTML = "";

  for (let i = 0; i < firstDay; i++) {
    grid.insertAdjacentHTML("beforeend", '<div class="py-2"></div>');
  }

  const today = todayISO();

  for (let day = 1; day <= daysInMonth; day++) {
    const month = String(currentMonth + 1).padStart(2, "0");
    const dateKey =
      currentYear + "-" + month + "-" + String(day).padStart(2, "0");
    const isToday = dateKey === today;
    const deadlineCount = deadlinesByDate[dateKey] || 0;

    const classes = isToday
      ? "bg-blue-600 text-white rounded-full font-bold"
      : "hover:bg-gray-100 dark:hover:bg-gray-700 rounded";

    grid.insertAdjacentHTML(
      "beforeend",
      `<div class="py-2 ${classes}">${day}${deadlineCount ? '<span class="text-xs"> ●</span>' : ""}</div>`,
    );
  }
}

function changeMonth(offset) {
  currentMonth += offset;
  if (currentMonth < 0) {
    currentMonth = 11;
    currentYear--;
  } else if (currentMonth > 11) {
    currentMonth = 0;
    currentYear++;
  }
  renderCalendar();
}

// --------------------------------------------
// 10. Notes
// --------------------------------------------

function renderNotes() {
  const listEl = document.getElementById("note-list");
  const notes = getNotes();

  if (notes.length === 0) {
    listEl.innerHTML =
      '<p class="text-sm text-gray-500 dark:text-gray-400">Belum ada catatan.</p>';
    return;
  }

  listEl.innerHTML = "";

  notes.forEach(function (note) {
    const li = document.createElement("li");
    li.className =
      "flex items-start gap-3 border border-gray-200 dark:border-gray-700 rounded-lg p-3";
    li.innerHTML = `
            <div class="flex-1">
                <p class="text-sm">${escapeHTML(note.text)}</p>
                <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">${note.createdAt}</p>
            </div>
            <button data-note-id="${note.id}" class="text-xs text-red-500 hover:underline">Hapus</button>
        `;
    listEl.appendChild(li);
  });
}

function addNote(event) {
  event.preventDefault();

  const input = document.getElementById("note-text");
  const text = input.value.trim();

  if (text === "") return;

  apiCreateNote({ text: text })
    .then(function (note) {
      cachedNotes.unshift(normalizeNote(note));
      event.target.reset();
      renderNotes();
    })
    .catch(handleApiError);
}

function deleteNote(id) {
  apiDeleteNote(id)
    .then(function () {
      cachedNotes = cachedNotes.filter(function (note) {
        return note.id != id;
      });
      renderNotes();
    })
    .catch(handleApiError);
}

// --------------------------------------------
// 11. Theme (Dark Mode)
// --------------------------------------------

function applyTheme(isDark) {
  document.documentElement.classList.toggle("dark", isDark);
  document.getElementById("setting-dark-mode").checked = isDark;

  const settings = getSettings();
  settings.darkMode = isDark;
  saveSettings(settings);
}

function toggleTheme() {
  const isDark = document.documentElement.classList.contains("dark");
  applyTheme(!isDark);
}

// --------------------------------------------
// 12. Navigation & Mobile
// --------------------------------------------

function setupNavigation() {
  document
    .getElementById("nav-list")
    .addEventListener("click", function (event) {
      const link = event.target.closest(".nav-link");
      if (!link) return;

      event.preventDefault();
      document.querySelectorAll(".nav-link").forEach(function (el) {
        el.classList.remove("active");
      });
      link.classList.add("active");

      const targetId = link.getAttribute("href").substring(1);
      const target = document.getElementById(targetId);
      if (target) {
        target.scrollIntoView({ behavior: "smooth" });
      }

      document.getElementById("sidebar").classList.remove("open");
    });
}

function setupMobileMenu() {
  const btn = document.getElementById("mobile-menu-btn");
  const sidebar = document.getElementById("sidebar");

  btn.addEventListener("click", function () {
    sidebar.classList.toggle("open");
  });
}

// --------------------------------------------
// 13. Event Delegation untuk Task List
// --------------------------------------------

function setupTaskList() {
  const listEl = document.getElementById("task-list");

  listEl.addEventListener("click", function (event) {
    const target = event.target.closest("[data-action]");
    if (!target) return;

    const action = target.dataset.action;
    const id = target.dataset.id;

    if (action === "delete") deleteTask(id);
    if (action === "edit") openEditModal(id);
  });

  listEl.addEventListener("change", function (event) {
    const target = event.target.closest('[data-action="toggle"]');
    if (target) toggleTask(target.dataset.id);
  });

  listEl.addEventListener("input", function (event) {
    const target = event.target.closest('[data-action="progress"]');
    if (target) updateProgress(target.dataset.id, target.value);
  });
}

// --------------------------------------------
// 14. Init
// --------------------------------------------

function renderGreeting() {
  const hour = new Date().getHours();
  let greeting = "Good evening";
  if (hour < 11) greeting = "Good morning";
  else if (hour < 15) greeting = "Good afternoon";
  else if (hour < 18) greeting = "Good evening";

  document.getElementById("greeting").textContent = greeting + ", Lanang";
  document.getElementById("today-date").textContent =
    new Date().toLocaleDateString("id-ID", {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    });
}

// Setelah data berubah, selalu ambil ulang dari server supaya
// filter/sort yang aktif ikut ter-update. Contoh: kalau filter
// "TODO" aktif lalu task dicentang jadi COMPLETED, task itu
// harus hilang dari daftar -- kalau hanya render dari cache,
// dia masih kelihatan sampai refresh halaman.
function refresh() {
  return refreshFromServer().then(function () {
    renderCalendar();
  });
}

function init() {
  applyTheme(getSettings().darkMode);
  renderGreeting();

  document.getElementById("task-form").addEventListener("submit", addTask);
  document.getElementById("note-form").addEventListener("submit", addNote);
  document.getElementById("edit-form").addEventListener("submit", saveEdit);
  document
    .getElementById("edit-cancel")
    .addEventListener("click", closeEditModal);
  document
    .getElementById("theme-toggle")
    .addEventListener("click", toggleTheme);
  document
    .getElementById("calendar-prev")
    .addEventListener("click", function () {
      changeMonth(-1);
    });
  document
    .getElementById("calendar-next")
    .addEventListener("click", function () {
      changeMonth(1);
    });
  // Search: debounce 300ms supaya tidak spam request
  document.getElementById("task-search").addEventListener("input", function () {
    currentFilters.search = this.value.trim();
    applyFilters();
  });

  // Filter & sort: langsung, karena user tidak mengetik
  document
    .getElementById("filter-status")
    .addEventListener("change", function () {
      currentFilters.status = this.value;
      applyFilters(true);
    });

  document
    .getElementById("filter-priority")
    .addEventListener("change", function () {
      currentFilters.priority = this.value;
      applyFilters(true);
    });

  document.getElementById("sort-by").addEventListener("change", function () {
    currentFilters.sort = this.value;
    applyFilters(true);
  });

  document.getElementById("sort-order").addEventListener("click", function () {
    currentFilters.order = currentFilters.order === "asc" ? "desc" : "asc";
    this.textContent = currentFilters.order === "asc" ? "↑" : "↓";
    this.setAttribute(
      "aria-label",
      currentFilters.order === "asc" ? "Urutkan menurun" : "Urutkan menaik",
    );
    applyFilters(true);
  });
  document
    .getElementById("setting-dark-mode")
    .addEventListener("change", function (event) {
      applyTheme(event.target.checked);
    });
  document.getElementById("reset-data").addEventListener("click", function () {
    if (
      !window.confirm(
        "Hapus SEMUA data CampusFlow? Tindakan ini tidak bisa dibatalkan.",
      )
    )
      return;
    apiResetAll()
      .then(function () {
        localStorage.removeItem(STORAGE_KEYS.settings);
        window.location.reload();
      })
      .catch(handleApiError);
  });

  document
    .getElementById("note-list")
    .addEventListener("click", function (event) {
      const btn = event.target.closest("[data-note-id]");
      if (btn) deleteNote(btn.dataset.noteId);
    });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closeEditModal();
  });

  setupNavigation();
  setupMobileMenu();
  setupTaskList();

  // Data harus dimuat dari server DULUAN, baru render.
  // Kalau render duluan, halaman akan tampil kosong
  // lalu berubah sendiri setelah server menjawab (flicker).
  loadFromServer()
    .then(seedIfEmpty)
    .then(seedCoursesIfEmpty)
    .then(function () {
      renderTasks();
      renderStats();
      renderAnalytics();
      renderCourses();
      renderNotes();
      renderCalendar();
    })
    .catch(handleApiError);
}

document.addEventListener("DOMContentLoaded", init);
