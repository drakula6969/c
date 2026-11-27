// PortableStream operator desk: REST fallback + WebSocket live updates.

const state = {
  key: localStorage.getItem("ps_admin_key") || "",
  clients: new Map(),
  selectedId: null,
  selectedShotId: null,
  ws: null,
  pingTimer: null,
  reconnectTimer: null,
  refreshTimer: null,
  toastTimer: null,
  objectUrl: null,
};

const el = (id) => document.getElementById(id);
const escapeHtml = (value) => {
  const node = document.createElement("span");
  node.textContent = value ?? "";
  return node.innerHTML;
};

function apiHeaders() {
  return { Authorization: `Bearer ${state.key}` };
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { ...apiHeaders(), ...(options.headers || {}) },
  });
  if (response.status === 401 || response.status === 403) {
    state.key = "";
    localStorage.removeItem("ps_admin_key");
    showGate("Ключ не принят. Проверьте ADMIN_API_KEY на сервере.");
    throw new Error("Неверный ключ администратора");
  }
  if (!response.ok) {
    let detail = `Ошибка сервера (${response.status})`;
    try {
      const body = await response.json();
      if (body.detail) detail = String(body.detail);
    } catch (_) {}
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  const text = await response.text();
  return text ? JSON.parse(text) : null;
}

function showGate(error = "") {
  el("keyGate").classList.remove("hidden");
  el("app").classList.add("hidden");
  el("keyError").textContent = error;
  if (error) el("keyInput").focus();
}

function hideGate() {
  el("keyGate").classList.add("hidden");
  el("app").classList.remove("hidden");
}

function showToast(text, kind = "") {
  const toast = el("toast");
  toast.textContent = text;
  toast.className = `toast show ${kind}`;
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => { toast.className = "toast"; }, 3400);
}

// ---------- Login ----------
el("keyForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const value = el("keyInput").value.trim();
  if (!value) return;
  state.key = value;
  localStorage.setItem("ps_admin_key", value);
  await boot();
});

// ---------- Clients ----------
function renderClientList() {
  const list = el("clientList");
  const query = el("clientSearch").value.trim().toLocaleLowerCase();
  const all = [...state.clients.values()].sort((a, b) => Number(b.online) - Number(a.online) || a.id - b.id);
  const visible = all.filter((client) => `${client.code} ${client.name || ""}`.toLocaleLowerCase().includes(query));
  el("onlineCount").textContent = `${all.filter((client) => client.online).length} онлайн`;
  list.replaceChildren();

  if (!visible.length) {
    const empty = document.createElement("li");
    empty.className = "no-clients";
    empty.textContent = query ? "Ничего не найдено. Попробуйте другой запрос." : "Компьютеры пока не подключались. Запустите клиент и обновите страницу.";
    list.appendChild(empty);
    return;
  }

  for (const client of visible) {
    const item = document.createElement("li");
    item.className = `client-item${client.id === state.selectedId ? " active" : ""}`;
    item.innerHTML = `
      <span class="client-label">
        <i class="dot ${client.online ? "online" : ""}"></i>
        <span class="client-label-copy">
          <span class="client-code">${escapeHtml(client.code || `PC-${client.id}`)}</span>
          <span class="client-host">${escapeHtml(client.name || "Имя не указано")}</span>
        </span>
      </span>
      <span class="client-last">${client.online ? "сейчас" : escapeHtml(relativeTime(client.last_seen))}</span>`;
    item.addEventListener("click", () => selectClient(client.id));
    list.appendChild(item);
  }
}

function relativeTime(iso) {
  if (!iso) return "—";
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "недавно";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} мин назад`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} ч назад`;
  return new Date(iso).toLocaleDateString();
}

function formatDate(iso) {
  if (!iso) return "Время неизвестно";
  return new Date(iso).toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

async function refreshClients() {
  const clients = await api("/api/admin/clients");
  for (const client of clients) state.clients.set(client.id, client);
  renderClientList();
  if (state.selectedId) refreshClientHeader();
}

async function selectClient(id) {
  state.selectedId = id;
  state.selectedShotId = null;
  el("emptyState").classList.add("hidden");
  el("clientView").classList.remove("hidden");
  el("sendStatus").textContent = "";
  renderClientList();
  refreshClientHeader();
  await Promise.allSettled([loadScreenshots(id), loadMessages(id)]);
}

function refreshClientHeader() {
  const client = state.clients.get(state.selectedId);
  if (!client) return;
  el("clientTitle").textContent = client.name ? `${client.code} · ${client.name}` : client.code;
  el("clientSub").textContent = client.online ? "В сети · ответ придёт автоматически" : `Не в сети · был(а) ${relativeTime(client.last_seen)}`;
  el("presenceDot").classList.toggle("online", Boolean(client.online));
}

el("clientSearch").addEventListener("input", renderClientList);

// ---------- Screenshots ----------
async function loadScreenshots(clientId, forceLatest = false) {
  const shots = await api(`/api/admin/clients/${clientId}/screenshots`);
  if (clientId !== state.selectedId) return;
  const list = el("screenshotThumbs");
  list.replaceChildren();
  el("shotCount").textContent = shots.length ? `(${shots.length})` : "(0)";

  if (!shots.length) {
    state.selectedShotId = null;
    if (state.objectUrl) { URL.revokeObjectURL(state.objectUrl); state.objectUrl = null; }
    el("screenshotImg").removeAttribute("src");
    el("screenshotImg").classList.add("hidden");
    el("screenshotPlaceholder").classList.remove("hidden");
    el("shotTimestamp").textContent = "Скриншот появится здесь после отправки с компьютера";
    el("downloadShot").classList.add("hidden");
    el("expandShot").disabled = true;
    el("deleteShot").disabled = true;
    el("replyToShot").disabled = true;
    el("replyContext").classList.add("hidden");
    return;
  }

  for (const shot of shots) {
    const button = document.createElement("li");
    button.className = `shot-thumb${shot.id === state.selectedShotId ? " active" : ""}`;
    button.textContent = formatDate(shot.created_at);
    button.title = `Открыть скриншот от ${formatDate(shot.created_at)}`;
    button.addEventListener("click", () => showScreenshot(shot, button));
    list.appendChild(button);
  }

  const target = forceLatest || !state.selectedShotId
    ? shots[0]
    : shots.find((shot) => shot.id === state.selectedShotId) || shots[0];
  if (target.id !== state.selectedShotId || forceLatest) {
    const targetButton = [...list.children].find((node, index) => shots[index].id === target.id);
    await showScreenshot(target, targetButton);
  } else {
    [...list.children].forEach((node, index) => node.classList.toggle("active", shots[index].id === state.selectedShotId));
  }
}

async function showScreenshot(shot, activeButton) {
  state.selectedShotId = shot.id;
  [...el("screenshotThumbs").children].forEach((node) => node.classList.toggle("active", node === activeButton));
  el("deleteShot").disabled = true;
  el("replyToShot").disabled = true;
  el("replyContext").classList.add("hidden");
  el("shotLoading").classList.remove("hidden");
  el("screenshotPlaceholder").classList.add("hidden");
  try {
    const response = await fetch(`/api/admin/screenshots/${shot.id}/file`, { headers: apiHeaders() });
    if (response.status === 401 || response.status === 403) {
      showGate("Ключ не принят. Проверьте ADMIN_API_KEY на сервере.");
      return;
    }
    if (!response.ok) throw new Error(`Не удалось загрузить изображение (${response.status})`);
    const blob = await response.blob();
    if (state.selectedShotId !== shot.id) return;
    if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
    state.objectUrl = URL.createObjectURL(blob);
    const image = el("screenshotImg");
    image.src = state.objectUrl;
    image.classList.remove("hidden");
    el("screenshotPlaceholder").classList.add("hidden");
    el("shotTimestamp").textContent = `Снято ${formatDate(shot.created_at)}`;
    const download = el("downloadShot");
    download.href = state.objectUrl;
    download.classList.remove("hidden");
    el("expandShot").disabled = false;
    el("deleteShot").disabled = false;
    el("replyToShot").disabled = false;
    el("replyShotTime").textContent = formatDate(shot.created_at);
    el("replyContext").classList.remove("hidden");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    el("shotLoading").classList.add("hidden");
  }
}

async function refreshCurrentShots() {
  if (!state.selectedId) return;
  try { await loadScreenshots(state.selectedId, true); }
  catch (error) { showToast(error.message, "error"); }
}

el("refreshShots").addEventListener("click", refreshCurrentShots);
el("replyToShot").addEventListener("click", () => {
  if (!state.selectedShotId) return;
  el("replyText").focus();
  el("sendStatus").className = "send-status";
  el("sendStatus").textContent = `Ответ будет отправлен пользователю ${el("clientTitle").textContent} по выбранному скриншоту.`;
});
el("deleteShot").addEventListener("click", async () => {
  const shotId = state.selectedShotId;
  if (!shotId) return;
  if (!confirm(`Удалить выбранный скриншот (${el("shotTimestamp").textContent})? Это действие нельзя отменить.`)) return;
  const button = el("deleteShot");
  button.disabled = true;
  try {
    await api(`/api/admin/screenshots/${shotId}`, { method: "DELETE" });
    state.selectedShotId = null;
    showToast("Скриншот удалён.");
    await loadScreenshots(state.selectedId, true);
  } catch (error) {
    button.disabled = false;
    showToast(`Не удалось удалить скриншот: ${error.message}`, "error");
  }
});
el("screenshotImg").addEventListener("click", () => openImageDialog());
el("expandShot").addEventListener("click", () => openImageDialog());
function openImageDialog() {
  if (!state.objectUrl) return;
  const dialog = el("imageDialog");
  el("dialogImage").src = state.objectUrl;
  el("dialogCaption").textContent = el("shotTimestamp").textContent;
  dialog.showModal();
}
el("closeDialog").addEventListener("click", () => el("imageDialog").close());
el("imageDialog").addEventListener("click", (event) => {
  if (event.target === el("imageDialog")) el("imageDialog").close();
});

// ---------- Conversation / operator reply ----------
async function loadMessages(clientId) {
  const messages = await api(`/api/admin/clients/${clientId}/messages`);
  if (clientId !== state.selectedId) return;
  const list = el("messageList");
  list.replaceChildren();
  if (!messages.length) {
    const empty = document.createElement("li");
    empty.className = "empty-messages";
    empty.innerHTML = "<strong>Начните диалог</strong><span>Посмотрите скриншот и напишите пользователю, что нужно сделать.</span>";
    list.appendChild(empty);
    return;
  }
  for (const message of messages) {
    const item = document.createElement("li");
    item.className = message.sender === "admin" ? "admin" : "client";
    item.innerHTML = `${escapeHtml(message.text)}<span class="meta">${message.sender === "admin" ? "Вы" : "Клиент"} · ${escapeHtml(formatDate(message.created_at))}</span>`;
    list.appendChild(item);
  }
  list.scrollTop = list.scrollHeight;
}

el("replyForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = el("replyText").value.trim();
  const clientId = state.selectedId;
  if (!text || !clientId) {
    if (!clientId) showToast("Сначала выберите компьютер слева.");
    return;
  }
  const button = el("sendReply");
  button.disabled = true;
  el("sendStatus").className = "send-status";
  el("sendStatus").textContent = "Отправляю ответ…";
  try {
    const sendResult = await api(`/api/admin/clients/${clientId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    el("replyText").value = "";
    await loadMessages(clientId);
    const online = Boolean(state.clients.get(clientId)?.online);
    el("sendStatus").className = "send-status success";
    if (sendResult && sendResult.delivered === true) {
      el("sendStatus").textContent = "Ответ дошёл до клиента по активному соединению.";
    } else if (sendResult && sendResult.delivered === false) {
      el("sendStatus").textContent = online
        ? "Ответ сохранён. Прямой канал недоступен — клиент заберёт его через резервную проверку."
        : "Ответ сохранён, но компьютер офлайн. Он получит его после подключения.";
    } else {
      el("sendStatus").textContent = online
        ? "Ответ отправлен. Клиент проверит сообщение автоматически."
        : "Ответ сохранён. Клиент получит его при следующем подключении.";
    }
    el("replyText").focus();
  } catch (error) {
    el("sendStatus").className = "send-status error";
    el("sendStatus").textContent = `Не удалось отправить: ${error.message}`;
  } finally {
    button.disabled = false;
  }
});

el("replyText").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    el("replyForm").requestSubmit();
  }
});

// ---------- Live updates and polling fallback ----------
function setConnection(online) {
  el("connDot").classList.toggle("online", online);
  el("connStatus").textContent = online ? "Связь с сервером активна" : "Переподключаемся к серверу…";
}

function connectWs() {
  if (!state.key || (state.ws && [WebSocket.OPEN, WebSocket.CONNECTING].includes(state.ws.readyState))) return;
  clearTimeout(state.reconnectTimer);
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${location.host}/ws/admin?token=${encodeURIComponent(state.key)}`);
  state.ws = socket;
  socket.onopen = () => {
    if (state.ws !== socket) return;
    setConnection(true);
    clearInterval(state.pingTimer);
    state.pingTimer = setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) socket.send("ping");
    }, 20000);
  };
  socket.onclose = () => {
    if (state.ws !== socket) return;
    setConnection(false);
    clearInterval(state.pingTimer);
    state.ws = null;
    state.reconnectTimer = setTimeout(connectWs, 3000);
  };
  socket.onerror = () => socket.close();
  socket.onmessage = async (event) => {
    let message;
    try { message = JSON.parse(event.data); } catch (_) { return; }
    if (message.type === "status") {
      const client = state.clients.get(message.client_id);
      if (client) client.online = Boolean(message.online);
      else {
        try { await refreshClients(); } catch (_) {}
      }
      renderClientList();
      if (message.client_id === state.selectedId) refreshClientHeader();
    } else if (message.type === "screenshot") {
      if (message.client_id === state.selectedId) {
        try { await loadScreenshots(message.client_id, true); } catch (error) { showToast(error.message, "error"); }
      }
      try { await refreshClients(); } catch (_) {}
    }
  };
}

async function boot() {
  try {
    await refreshClients();
  } catch (error) {
    showGate(error.message === "Неверный ключ администратора" ? error.message : `Не удалось подключиться к серверу: ${error.message}`);
    return;
  }
  hideGate();
  connectWs();
  clearInterval(state.refreshTimer);
  // REST-проверки страхуют интерфейс, если уведомление WebSocket было потеряно.
  state.refreshTimer = setInterval(async () => {
    try {
      await refreshClients();
      if (state.selectedId) await Promise.allSettled([loadScreenshots(state.selectedId), loadMessages(state.selectedId)]);
    } catch (_) {}
  }, 15000);
}

if (state.key) {
  el("keyInput").value = state.key;
  boot();
} else {
  showGate();
  el("keyInput").focus();
}
