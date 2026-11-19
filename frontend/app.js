const $ = id => document.getElementById(id);
let token = '', epoch = 0, controller = new AbortController();
function node(tag, text, cls) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (cls) el.className = cls;
  return el;
}
function clearSession() {
  epoch += 1; controller.abort(); controller = new AbortController(); token = '';
  try { localStorage.removeItem('commutepolicy_token'); } catch (e) {}
  $('messages').replaceChildren(); $('token').value = ''; $('admin-result').textContent = '';
  $('loading').textContent = ''; $('session-status').textContent = 'Session cleared.'; $('send').disabled = false;
}
async function api(path, options = {}) {
  if (!token) throw new Error('Connect with an access token first.');
  const response = await fetch(path, {...options, signal: controller.signal,
    headers: {...options.headers, Authorization: `Bearer ${token}`}});
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || data.answer || 'Request failed.');
  return data;
}
function decodePayload(jwt) {
  try {
    const base64Url = jwt.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(decodeURIComponent(escape(atob(base64))));
  } catch (e) {
    return null;
  }
}
function setToken(nextToken, label = 'Token loaded') {
  clearSession(); token = nextToken; $('token').value = nextToken;
  try { localStorage.setItem('commutepolicy_token', nextToken); } catch (e) {}
  $('session-status').textContent = `${label}. Verified on every request.`;
  const payload = decodePayload(nextToken);
  const badge = $('tenant-badge');
  if (badge) {
    if (payload && payload.company_id) {
      const companies = {
        'COMPANY_A': '🏢 Apex Technologies',
        'COMPANY_B': '🏢 Nova Digital',
        'COMPANY_C': '🏢 Vertex Systems'
      };
      const roleName = payload.role === 'policy_admin' ? '⚙️ Admin' : '👤 Employee';
      badge.textContent = `${companies[payload.company_id] || payload.company_id} · ${roleName}`;
      badge.style.display = 'inline-flex';
    } else {
      badge.style.display = 'none';
    }
  }
}
$('session').addEventListener('submit', event => {
  event.preventDefault(); const next = $('token').value.trim();
  if (next) setToken(next);
});
$('logout').addEventListener('click', () => {
  clearSession();
  const badge = $('tenant-badge');
  if (badge) badge.style.display = 'none';
});

let demoTokens = {};
async function initPresets() {
  try {
    const res = await fetch('/api/v1/demo/tokens');
    if (res.ok) demoTokens = await res.json();
  } catch (e) {}
  document.querySelectorAll('.preset-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const key = btn.dataset.key;
      const tok = demoTokens[key];
      if (tok) {
        setToken(tok, `Connected: ${btn.textContent.trim()}`);
      }
    });
  });
  document.querySelectorAll('.prompt-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      $('question').value = chip.dataset.q;
      $('question-form').dispatchEvent(new Event('submit', {cancelable: true, bubbles: true}));
    });
  });
  try {
    const saved = localStorage.getItem('commutepolicy_token');
    if (saved) setToken(saved, 'Restored saved session');
  } catch (e) {}
}
window.addEventListener('DOMContentLoaded', initPresets);
function renderAnswer(data) {
  const article = node('article');
  article.append(node('div', data.status.replaceAll('_', ' '), 'status'), node('div', data.answer, 'answer'));
  for (const c of data.citations) {
    const ref = node('div', undefined, 'citation');
    ref.append(node('strong', `${c.document} · Section ${c.section || 'unnumbered'} — ${c.section_title}${c.page ? ` · Page ${c.page}` : ''}`), node('blockquote', c.quote));
    article.append(ref);
  }
  if (data.timings_ms && data.timings_ms.total) {
    const t = data.timings_ms;
    const timeSpan = node('div', undefined, 'timing-badge');
    timeSpan.textContent = `⚡ Latency: ${t.total.toFixed(1)}ms (Embedding: ${(t.embedding||0).toFixed(1)}ms · Hybrid Retrieval: ${(t.retrieval||0).toFixed(1)}ms)`;
    article.append(timeSpan);
  }
  article.append(node('p', data.fallback, 'small'), node('p', `Policy version: ${data.policy_version || 'unavailable'} · Reference: ${data.request_id}`, 'small'));
  const actions = node('div', undefined, 'actions');
  for (const [label, helpful] of [['Helpful', true], ['Not helpful', false]]) {
    const button = node('button', label, 'secondary');
    button.addEventListener('click', async () => {
      const current = epoch;
      try {
        await api('/api/v1/feedback', {method:'POST', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({request_id:data.request_id, helpful, reason:''})});
        if (current === epoch) actions.replaceChildren(node('span', 'Feedback recorded.'));
      } catch (error) { if (current === epoch) $('loading').textContent = error.message; }
    }); actions.append(button);
  }
  article.append(actions); $('messages').append(article); article.scrollIntoView({block:'nearest'});
}
$('question-form').addEventListener('submit', async event => {
  event.preventDefault(); const question = $('question').value.trim(); if (!question || !token) return;
  const current = epoch; $('send').disabled = true; $('loading').textContent = 'Checking your current policy…';
  $('messages').append(node('article', question, 'user')); $('question').value = '';
  try {
    const data = await api('/api/v1/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question})});
    if (current === epoch) { renderAnswer(data); $('loading').textContent = ''; }
  } catch (error) { if (current === epoch) $('loading').textContent = error.message; }
  finally { if (current === epoch) $('send').disabled = false; }
});
$('upload').addEventListener('submit', async event => {
  event.preventDefault(); const current = epoch; const file = $('policy').files[0]; if (!file) return;
  if (file.size > 10000000) { $('admin-result').textContent = 'File exceeds the 10 MB demo limit.'; return; }
  const form = new FormData(); form.append('file', file); $('admin-result').textContent = 'Processing policy…';
  const button = event.target.querySelector('button'); button.disabled = true;
  try {
    const data = await api('/api/v1/admin/policies/upload', {method:'POST', body:form});
    if (current === epoch) { $('admin-result').textContent = JSON.stringify(data, null, 2); $('messages').replaceChildren(node('article', 'New policy activated. Ask again to use the current version.')); }
  } catch (error) { if (current === epoch) $('admin-result').textContent = error.message; }
  finally { button.disabled = false; }
});
for (const [id, path] of [['versions', '/api/v1/admin/policies/versions'], ['audit', '/api/v1/admin/audit']]) {
  $(id).addEventListener('click', async () => {
    const current = epoch;
    try { const data = await api(path); if (current === epoch) $('admin-result').textContent = JSON.stringify(data, null, 2); }
    catch (error) { if (current === epoch) $('admin-result').textContent = error.message; }
  });
}
