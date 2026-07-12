'use strict';

const state = {
  token: sessionStorage.getItem('jarvis_token') || '',
  conversationId: sessionStorage.getItem('jarvis_conversation') || null,
  recording: false,
  recorder: null,
  chunks: [],
};

const $ = (id) => document.getElementById(id);
const loginView = $('loginView');
const appView = $('appView');
const toast = $('toast');

function showToast(message, isError = false) {
  toast.textContent = message;
  toast.classList.remove('hidden', 'error-toast');
  if (isError) toast.classList.add('error-toast');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.add('hidden'), 3800);
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.token) headers.set('Authorization', `Bearer ${state.token}`);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401) {
    logout();
    throw new Error('セッションが切れました。再度ログインしてください。');
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

function setAuthenticated(authenticated) {
  loginView.classList.toggle('hidden', authenticated);
  appView.classList.toggle('hidden', !authenticated);
  if (authenticated) refreshAll();
}

function logout() {
  state.token = '';
  sessionStorage.removeItem('jarvis_token');
  setAuthenticated(false);
}

$('loginForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('loginError').textContent = '';
  try {
    const result = await api('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username: $('username').value, password: $('password').value }),
    });
    state.token = result.token;
    sessionStorage.setItem('jarvis_token', state.token);
    setAuthenticated(true);
  } catch (error) {
    $('loginError').textContent = error.message;
  }
});

$('logoutButton').addEventListener('click', logout);

const titles = { chat: '会話', home: 'ホーム', routines: 'ルーチン', memory: '記憶', audit: '監査', settings: '設定' };
document.querySelectorAll('#nav button').forEach((button) => {
  button.addEventListener('click', () => {
    const tab = button.dataset.tab;
    document.querySelectorAll('#nav button').forEach((item) => item.classList.toggle('active', item === button));
    document.querySelectorAll('.tab').forEach((item) => item.classList.toggle('active', item.id === `tab-${tab}`));
    $('pageTitle').textContent = titles[tab];
    if (tab === 'home') refreshStatus();
    if (tab === 'routines') loadRoutines();
    if (tab === 'memory') loadMemory();
    if (tab === 'audit') loadAudit();
    if (tab === 'settings') loadSettings();
  });
});

function addMessage(role, text) {
  const wrapper = document.createElement('div');
  wrapper.className = `message ${role}`;
  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = role === 'user' ? 'YOU' : 'J';
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = text;
  wrapper.append(avatar, bubble);
  $('messages').append(wrapper);
  $('messages').scrollTop = $('messages').scrollHeight;
  return wrapper;
}

$('messageInput').addEventListener('input', (event) => {
  event.target.style.height = 'auto';
  event.target.style.height = `${Math.min(event.target.scrollHeight, 160)}px`;
});

$('messageInput').addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    $('chatForm').requestSubmit();
  }
});

$('chatForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const input = $('messageInput');
  const message = input.value.trim();
  if (!message) return;
  input.value = '';
  input.style.height = 'auto';
  addMessage('user', message);
  const pending = addMessage('assistant', '処理中…');
  const sendButton = event.submitter || event.currentTarget.querySelector('button[type="submit"]');
  sendButton.disabled = true;
  try {
    const result = await api('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ message, conversation_id: state.conversationId }),
    });
    state.conversationId = result.conversation_id;
    sessionStorage.setItem('jarvis_conversation', state.conversationId);
    pending.querySelector('.bubble').textContent = result.message;
    if (result.degraded) pending.querySelector('.bubble').textContent += '\n\n［縮退モード］';
    await loadApprovals();
  } catch (error) {
    pending.querySelector('.bubble').textContent = `エラー: ${error.message}`;
  } finally {
    sendButton.disabled = false;
  }
});

function clearAndEmpty(container, emptyText) {
  container.replaceChildren();
  container.classList.add('empty');
  container.textContent = emptyText;
}

function compactItem(title, description) {
  const item = document.createElement('div');
  item.className = 'compact-item';
  const strong = document.createElement('strong');
  strong.textContent = title;
  const p = document.createElement('p');
  p.textContent = description;
  item.append(strong, p);
  return item;
}

async function loadApprovals() {
  try {
    const approvals = await api('/api/approvals');
    $('approvalCount').textContent = approvals.length;
    const box = $('approvals');
    box.replaceChildren();
    box.classList.toggle('empty', approvals.length === 0);
    if (!approvals.length) {
      box.textContent = 'ありません';
      return;
    }
    approvals.forEach((approval) => {
      const item = compactItem(approval.tool_name, `${approval.risk.toUpperCase()} — ${approval.reason}`);
      const args = document.createElement('p');
      args.textContent = JSON.stringify(approval.arguments);
      const actions = document.createElement('div');
      actions.className = 'compact-actions';
      const approve = document.createElement('button');
      approve.className = 'secondary';
      approve.textContent = '承認して実行';
      approve.addEventListener('click', () => decideApproval(approval.id, true));
      const reject = document.createElement('button');
      reject.className = 'ghost danger';
      reject.textContent = '拒否';
      reject.addEventListener('click', () => decideApproval(approval.id, false));
      actions.append(approve, reject);
      item.append(args, actions);
      box.append(item);
    });
  } catch (error) {
    showToast(error.message, true);
  }
}

async function decideApproval(id, approved) {
  try {
    const result = await api(`/api/approvals/${id}`, {
      method: 'POST',
      body: JSON.stringify({ approved }),
    });
    showToast(approved ? (result.ok ? '承認済み。操作を実行しました。' : `実行失敗: ${result.error}`) : '操作を拒否しました。', approved && !result.ok);
    await loadApprovals();
    await refreshStatus();
  } catch (error) {
    showToast(error.message, true);
  }
}

function statusLine(label, ok, detail = '') {
  const row = document.createElement('div');
  row.className = 'status-row';
  const left = document.createElement('span');
  const dot = document.createElement('span');
  dot.className = `dot ${ok ? 'ok' : 'bad'}`;
  left.append(dot, document.createTextNode(label));
  const right = document.createElement('span');
  right.textContent = detail || (ok ? 'ONLINE' : 'OFFLINE');
  row.append(left, right);
  return row;
}

async function refreshStatus() {
  try {
    const status = await api('/api/status');
    const quick = $('quickStatus');
    quick.replaceChildren(
      statusLine('JARVIS Core', status.ok),
      statusLine('Ollama', status.ollama.ok, status.ollama.ok ? status.ollama.configured_model : 'OFFLINE'),
      statusLine('Home Assistant', status.home_assistant.ok),
      statusLine('Audit Chain', status.audit.ok),
    );
    $('corePill').className = `pill ${status.ok && status.audit.ok ? 'ok' : 'bad'}`;
    $('corePill').lastChild.textContent = status.ok && status.audit.ok ? '稼働中' : '要確認';
    const full = $('fullStatus');
    full.replaceChildren();
    const values = [
      ['バージョン', status.version],
      ['環境', status.environment],
      ['ツール数', String(status.tools)],
      ['Shell', status.shell_enabled ? '有効' : '無効'],
      ['Plugin', status.plugins.length ? status.plugins.join(', ') : 'なし'],
      ['Workspace', status.workspace_roots.length ? status.workspace_roots.join(', ') : '未設定'],
    ];
    values.forEach(([key, value]) => {
      const row = document.createElement('div');
      const dt = document.createElement('dt'); dt.textContent = key;
      const dd = document.createElement('dd'); dd.textContent = value;
      row.append(dt, dd); full.append(row);
    });
    return status;
  } catch (error) {
    $('corePill').className = 'pill bad';
    showToast(error.message, true);
    return null;
  }
}

$('refreshButton').addEventListener('click', refreshAll);

async function loadEntities() {
  const box = $('entities');
  clearAndEmpty(box, '取得中…');
  try {
    const domain = $('domainFilter').value;
    const entities = await api(`/api/home/entities${domain ? `?domain=${encodeURIComponent(domain)}` : ''}`);
    box.replaceChildren();
    box.classList.toggle('empty', entities.length === 0);
    if (!entities.length) {
      box.textContent = '対象エンティティがありません。';
      return;
    }
    entities.forEach((entity) => {
      const card = document.createElement('div'); card.className = 'entity';
      const name = document.createElement('strong'); name.textContent = entity.attributes.friendly_name || entity.entity_id;
      name.title = entity.entity_id;
      const value = document.createElement('span'); value.textContent = `${entity.state}${entity.attributes.unit_of_measurement ? ` ${entity.attributes.unit_of_measurement}` : ''}`;
      card.append(name, value); box.append(card);
    });
  } catch (error) {
    clearAndEmpty(box, error.message);
  }
}
$('loadEntities').addEventListener('click', loadEntities);

async function loadRoutines() {
  try {
    const routines = await api('/api/routines');
    const box = $('routineList');
    box.replaceChildren(); box.classList.toggle('empty', routines.length === 0);
    if (!routines.length) { box.textContent = 'まだありません'; return; }
    routines.forEach((routine) => {
      const item = compactItem(routine.name, `${routine.description || '説明なし'}${routine.cron ? ` / ${routine.cron}` : ''}`);
      const actions = document.createElement('div'); actions.className = 'compact-actions';
      const run = document.createElement('button'); run.className = 'secondary'; run.textContent = '実行';
      run.addEventListener('click', async () => {
        try { const result = await api(`/api/routines/${routine.id}/run`, { method: 'POST' }); showToast(`${result.name}を実行しました`); await loadApprovals(); }
        catch (error) { showToast(error.message, true); }
      });
      const del = document.createElement('button'); del.className = 'ghost danger'; del.textContent = '削除';
      del.addEventListener('click', async () => {
        try { await api(`/api/routines/${routine.id}`, { method: 'DELETE' }); await loadRoutines(); }
        catch (error) { showToast(error.message, true); }
      });
      actions.append(run, del); item.append(actions); box.append(item);
    });
  } catch (error) { showToast(error.message, true); }
}
$('reloadRoutines').addEventListener('click', loadRoutines);
$('routineForm').addEventListener('submit', async (event) => {
  event.preventDefault(); $('routineError').textContent = '';
  try {
    const steps = JSON.parse($('routineSteps').value);
    await api('/api/routines', { method: 'POST', body: JSON.stringify({ name: $('routineName').value, description: $('routineDescription').value, cron: $('routineCron').value || null, enabled: true, steps }) });
    event.target.reset();
    $('routineSteps').value = '[{"tool":"home.call_service","arguments":{"domain":"light","service":"turn_off","target":{"entity_id":"light.living_room"}}}]';
    await loadRoutines(); showToast('ルーチンを保存しました');
  } catch (error) { $('routineError').textContent = error.message; }
});

$('memoryImportance').addEventListener('input', () => { $('importanceValue').textContent = $('memoryImportance').value; });
$('memoryForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await api('/api/memory', { method: 'POST', body: JSON.stringify({ content: $('memoryContent').value, kind: $('memoryKind').value, importance: Number($('memoryImportance').value), tags: $('memoryTags').value.split(',').map((v) => v.trim()).filter(Boolean) }) });
    event.target.reset(); $('importanceValue').textContent = '5'; await loadMemory(); showToast('記憶しました');
  } catch (error) { showToast(error.message, true); }
});
async function loadMemory() {
  try {
    const q = $('memoryQuery').value;
    const memories = await api(`/api/memory?q=${encodeURIComponent(q)}&limit=100`);
    const box = $('memoryList'); box.replaceChildren(); box.classList.toggle('empty', memories.length === 0);
    if (!memories.length) { box.textContent = 'まだありません'; return; }
    memories.forEach((memory) => {
      const item = compactItem(`${memory.kind} · 重要度 ${memory.importance}`, memory.content);
      if (memory.tags.length) { const tags = document.createElement('p'); tags.textContent = memory.tags.map((tag) => `#${tag}`).join(' '); item.append(tags); }
      const actions = document.createElement('div'); actions.className = 'compact-actions';
      const del = document.createElement('button'); del.className = 'ghost danger'; del.textContent = '削除';
      del.addEventListener('click', async () => { try { await api(`/api/memory/${memory.id}`, { method: 'DELETE' }); await loadMemory(); } catch (error) { showToast(error.message, true); } });
      actions.append(del); item.append(actions); box.append(item);
    });
  } catch (error) { showToast(error.message, true); }
}
$('searchMemory').addEventListener('click', loadMemory);

async function loadAudit() {
  try {
    const [integrity, rows] = await Promise.all([api('/api/audit/verify'), api('/api/audit?limit=300')]);
    $('auditIntegrity').textContent = integrity.ok ? 'ハッシュチェーン整合性: 正常' : `破損を検出: 行 ${integrity.broken_at}`;
    const body = $('auditRows'); body.replaceChildren();
    rows.forEach((row) => {
      const tr = document.createElement('tr');
      [new Date(row.timestamp).toLocaleString(), row.actor, row.action, row.resource, row.outcome].forEach((value) => { const td = document.createElement('td'); td.textContent = value; tr.append(td); });
      body.append(tr);
    });
  } catch (error) { showToast(error.message, true); }
}
$('loadAudit').addEventListener('click', loadAudit);

async function loadSettings() {
  try {
    const settings = await api('/api/settings/integrations');
    $('ollamaUrl').value = settings.ollama_url;
    $('ollamaModel').value = settings.ollama_model;
    $('haUrl').value = settings.home_assistant_url;
    $('haToken').placeholder = settings.home_assistant_token_configured ? '設定済み（変更時のみ入力）' : '未設定';
  } catch (error) { showToast(error.message, true); }
}
async function saveSettings(payload) {
  try { await api('/api/settings/integrations', { method: 'PUT', body: JSON.stringify(payload) }); await refreshStatus(); showToast('設定を保存しました'); }
  catch (error) { showToast(error.message, true); }
}
$('ollamaForm').addEventListener('submit', (event) => { event.preventDefault(); saveSettings({ ollama_url: $('ollamaUrl').value, ollama_model: $('ollamaModel').value }); });
$('haForm').addEventListener('submit', (event) => { event.preventDefault(); const payload = { home_assistant_url: $('haUrl').value }; if ($('haToken').value) payload.home_assistant_token = $('haToken').value; saveSettings(payload); $('haToken').value = ''; });

$('backupButton').addEventListener('click', async () => {
  $('backupResult').textContent = '作成中…';
  try { const result = await api('/api/backups', { method: 'POST' }); $('backupResult').textContent = `${result.path}\nSHA-256: ${result.sha256}`; }
  catch (error) { $('backupResult').textContent = error.message; }
});

$('voiceButton').addEventListener('click', async () => {
  const button = $('voiceButton');
  if (state.recording && state.recorder) { state.recorder.stop(); return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    state.chunks = [];
    state.recorder = new MediaRecorder(stream);
    state.recorder.ondataavailable = (event) => { if (event.data.size) state.chunks.push(event.data); };
    state.recorder.onstop = async () => {
      state.recording = false; button.textContent = '◉'; stream.getTracks().forEach((track) => track.stop());
      const blob = new Blob(state.chunks, { type: state.recorder.mimeType || 'audio/webm' });
      const form = new FormData(); form.append('audio', blob, 'voice.webm');
      try { const result = await api('/api/voice/transcribe', { method: 'POST', body: form }); $('messageInput').value = result.text; $('messageInput').focus(); }
      catch (error) { showToast(error.message, true); }
    };
    state.recorder.start(); state.recording = true; button.textContent = '■'; showToast('録音中。もう一度押すと停止します。');
  } catch (error) { showToast(`マイクを開始できません: ${error.message}`, true); }
});

async function refreshAll() {
  await Promise.allSettled([refreshStatus(), loadApprovals()]);
}

function updateClock() { $('clock').textContent = new Date().toLocaleString('ja-JP', { month: 'short', day: 'numeric', weekday: 'short', hour: '2-digit', minute: '2-digit' }); }
updateClock(); setInterval(updateClock, 30000); setInterval(() => { if (state.token) Promise.allSettled([refreshStatus(), loadApprovals()]); }, 15000);

if (state.token) {
  api('/api/auth/me').then(() => setAuthenticated(true)).catch(() => logout());
} else {
  setAuthenticated(false);
}
