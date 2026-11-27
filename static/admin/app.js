// Админ-панель PortableStream. Без сборки, просто fetch + WebSocket.

const state = {
  key: localStorage.getItem("ps_admin_key") || "",
  clients: new Map(), // id -> client object
  selectedId: null,
  ws: null,
};

const el = (id) => document.getElementById(id);

function apiHeaders() {
  return { Authorization: `Bearer ${state.key}` };
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { ...apiHeaders(), ...(options.headers || {}) },
  });
  if (res.status === 401 || res.status === 403) {
    showGate("Неверный ключ администратора");
    throw new Error("unauthorized");
  }
  if (!res.ok) {
    throw new Error(`API error ${res.status}`);
  }
  if (res.status === 204) return null;
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

// ---------- Ключ администратора ----------

function showGate(error) {
  el("keyGate").classList.remove("hidden");
  el("app").classList.add("hidden");
  if (error) el("keyError").textContent = error;
}

function hideGate() {
  el("keyGate").classList.add("hidden");
  el("app").classList.remove("hidden");
}

el("keySubmit").addEventListener("click", async () => {
  const value = el("keyInput").value.trim();
  if (!value) return;
  state.key = value;
  localStorage.setItem("ps_admin_key", value);
  await boot();
});

// ---------- Список клиентов ----------

function renderClientList() {
  const ul = el("clientList");
  ul.innerHTML = "";
  const items = Array.from(state.clients.values()).sort((a, b) => a.id - b.id);
  for (const c of items) {
    const li = document.createElement("li");
    li.className = "client-item" + (c.id === state.selectedId ? " active" : "");
    // Имя компьютера приходит от клиента, поэтому экранируем его перед
    // вставкой через innerHTML (иначе возможна stored XSS в админ-панели).
    const label = c.name
      ? `${escapeHtml(c.code)} · ${escapeHtml(c.name)}`
      : escapeHtml(c.code);
    li.innerHTML = `
      <span><span class="dot ${c.online ? "online" : ""}"></span>
      <span class="name">${label}</span></span>
      <span class="time">${c.online ? "online" : formatTime(c.last_seen)}</span>
    `;
    li.addEventListener("click", () => selectClient(c.id));
    ul.appendChild(li);
  }
}

function formatTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString();
}

async function refreshClients() {
  const list = await api("/api/admin/clients");
  for (const c of list) state.clients.set(c.id, c);
  renderClientList();
  if (state.selectedId) refreshClientHeader();
}

// ---------- Экран конкретного клиента ----------

async function selectClient(id) {
  state.selectedId = id;
  el("emptyState").classList.add("hidden");
  el("clientView").classList.remove("hidden");
  renderClientList();
  refreshClientHeader();
  await Promise.all([loadScreenshots(id), loadMessages(id)]);
}

function refreshClientHeader() {
  const c = state.clients.get(state.selectedId);
  if (!c) return;
  el("clientTitle").textContent = c.name ? `${c.code} — ${c.name}` : c.code;
  el("clientSub").textContent = c.online ? "онлайн" : `был(а) в сети: ${formatTime(c.last_seen)}`;
}

let lastObjectUrl = null;

async function loadScreenshots(clientId) {
  const shots = await api(`/api/admin/clients/${clientId}/screenshots`);
  const thumbs = el("screenshotThumbs");
  thumbs.innerHTML = "";
  if (shots.length === 0) {
    el("screenshotImg").classList.add("hidden");
    el("screenshotPlaceholder").classList.remove("hidden");
    return;
  }
  shots.forEach((s, idx) => {
    const li = document.createElement("li");
    li.textContent = formatTime(s.created_at);
    li.className = idx === 0 ? "active" : "";
    li.addEventListener("click", () => showScreenshot(s.id, li));
    thumbs.appendChild(li);
  });
  await showScreenshot(shots[0].id, thumbs.firstChild);
}

async function showScreenshot(id, activeLi) {
  Array.from(el("screenshotThumbs").children).forEach((c) => c.classList.remove("active"));
  if (activeLi) activeLi.classList.add("active");

  const res = await fetch(`/api/admin/screenshots/${id}/file`, { headers: apiHeaders() });
  if (!res.ok) return;
  const blob = await res.blob();
  if (lastObjectUrl) URL.revokeObjectURL(lastObjectUrl);
  lastObjectUrl = URL.createObjectURL(blob);
  const img = el("screenshotImg");
  img.src = lastObjectUrl;
  img.classList.remove("hidden");
  el("screenshotPlaceholder").classList.add("hidden");
}

async function loadMessages(clientId) {
  const msgs = await api(`/api/admin/clients/${clientId}/messages`);
  const ul = el("messageList");
  ul.innerHTML = "";
  for (const m of msgs) {
    const li = document.createElement("li");
    li.className = m.sender;
    li.innerHTML = `${escapeHtml(m.text)}<span class="meta">${formatTime(m.created_at)}</span>`;
    ul.appendChild(li);
  }
  ul.scrollTop = ul.scrollHeight;
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

el("replyForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const textarea = el("replyText");
  const text = textarea.value.trim();
  if (!text || !state.selectedId) return;
  textarea.value = "";
  await api(`/api/admin/clients/${state.selectedId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  await loadMessages(state.selectedId);
});

// ---------- WebSocket для live-обновлений ----------

function connectWs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/admin?token=${encodeURIComponent(state.key)}`);
  state.ws = ws;

  ws.onopen = () => {
    el("connStatus").textContent = "online";
    el("connStatus").classList.add("online");
  };
  ws.onclose = () => {
    el("connStatus").textContent = "offline";
    el("connStatus").classList.remove("online");
    // Render free tier может "засыпать" — пробуем переподключиться.
    setTimeout(connectWs, 3000);
  };
  ws.onerror = () => ws.close();

  ws.onmessage = async (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "status") {
      const c = state.clients.get(msg.client_id);
      if (c) {
        c.online = msg.online;
        renderClientList();
        if (msg.client_id === state.selectedId) refreshClientHeader();
      } else {
        refreshClients();
      }
    } else if (msg.type === "screenshot") {
      if (msg.client_id === state.selectedId) {
        await loadScreenshots(msg.client_id);
      }
      refreshClients();
    }
  };

  // keepalive, чтобы прокси/Render не закрывали простаивающее соединение
  setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) ws.send("ping");
  }, 20000);
}

// ---------- Инициализация ----------

async function boot() {
  try {
    await refreshClients();
  } catch (e) {
    showGate("Неверный ключ администратора или сервер недоступен");
    return;
  }
  hideGate();
  connectWs();
  setInterval(refreshClients, 10000); // подстраховка поверх WebSocket
}

if (state.key) {
  boot();
} else {
  showGate();
}
