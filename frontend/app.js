const $ = id => document.getElementById(id);
let token = '', epoch = 0, controller = new AbortController();
let demoTokens = {};

function node(tag, text, cls) {
  const el = document.createElement(tag);
  if (text !== undefined && text !== null) el.textContent = text;
  if (cls) el.className = cls;
  return el;
}

function clearSession() {
  epoch += 1;
  controller.abort();
  controller = new AbortController();
  token = '';
  try { localStorage.removeItem('commutepolicy_token'); } catch (e) {}
  $('messages').replaceChildren();
  $('token').value = '';
  $('admin-result').textContent = '';
  $('loading').textContent = '';
  $('session-status').textContent = 'Session cleared.';
  $('send').disabled = false;
  document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
}

async function api(path, options = {}) {
  if (!token) throw new Error('No active session. Please select a corporate persona.');
  const response = await fetch(path, {
    ...options,
    signal: controller.signal,
    headers: {
      ...options.headers,
      Authorization: `Bearer ${token}`
    }
  });
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

function setToken(nextToken, label = 'Connected') {
  controller.abort();
  controller = new AbortController();
  token = nextToken;
  $('token').value = nextToken;
  try { localStorage.setItem('commutepolicy_token', nextToken); } catch (e) {}

  const payload = decodePayload(nextToken);
  const badge = $('tenant-badge');

  if (payload && payload.company_id) {
    const companies = {
      'COMPANY_A': 'Apex Technologies',
      'COMPANY_B': 'Nova Digital',
      'COMPANY_C': 'Vertex Systems'
    };
    const cName = companies[payload.company_id] || payload.company_id;
    const roleName = payload.role === 'policy_admin' ? 'Sarah (Admin)' : (
      payload.company_id === 'COMPANY_A' ? 'Alex (Employee)' :
      payload.company_id === 'COMPANY_B' ? 'Priya (Employee)' : 'Rahul (Employee)'
    );
    badge.textContent = `${cName} · ${roleName}`;
    badge.style.display = 'inline-flex';
    $('session-status').textContent = `${label} as ${payload.company_id} (${payload.role}).`;

    // Highlight active preset button
    document.querySelectorAll('.preset-btn').forEach(btn => {
      const isMatch = demoTokens[btn.dataset.key] === nextToken;
      btn.classList.toggle('active', isMatch);
    });

    // Auto-open admin panel if admin role
    const adminPanel = $('admin-panel');
    if (adminPanel) {
      if (payload.role === 'policy_admin') {
        adminPanel.open = true;
      }
    }

    const authStatus = $('admin-auth-status');
    if (authStatus) {
      if (payload.role === 'policy_admin') {
        authStatus.className = 'role-badge success';
        authStatus.innerHTML = '<strong>Administrator Authorized:</strong> Policy upload, version staging, and audit controls are unlocked.';
      } else {
        authStatus.className = 'role-badge warning';
        authStatus.innerHTML = '<strong>Employee Session Active:</strong> Policy uploads and lifecycle controls are restricted to administrators. Switch to <strong>Apex Administration (Sarah)</strong> above to manage policies.';
      }
    }
  } else {
    badge.textContent = 'Unknown Session';
    $('session-status').textContent = 'Custom token connected.';
  }
}

function renderAnswer(data) {
  const container = node('div', undefined, 'msg-assistant');

  // Header status pill
  const header = node('div', undefined, 'msg-header');
  const statusLabels = {
    'answered': 'POLICY COVERED',
    'not_covered': 'POLICY SILENT (ABSTAINED)',
    'needs_clarification': 'CLARIFICATION REQUIRED',
    'temporary_error': 'SYSTEM ERROR'
  };
  const pill = node('span', statusLabels[data.status] || data.status.replaceAll('_', ' ').toUpperCase(), `status-pill ${data.status}`);
  header.append(pill);
  container.append(header);

  // Direct AI Answer
  const answerText = data.clarifying_question
    ? `${data.answer}\n\nClarification Required: ${data.clarifying_question}`
    : data.answer;
  const answer = node('div', answerText, 'msg-answer');
  container.append(answer);

  // Verified Source Citations
  if (data.citations && data.citations.length > 0) {
    for (const c of data.citations) {
      const card = node('div', undefined, 'citation-card');
      const cardHeader = node('div', undefined, 'citation-header');
      const titleSpan = node('span', `SOURCE: ${c.document} · Section ${c.section || 'N/A'} — ${c.section_title}${c.page ? ` · Page ${c.page}` : ''}`);

      const copyBtn = node('button', 'Copy Ref', 'btn-copy');
      copyBtn.type = 'button';
      copyBtn.addEventListener('click', () => {
        navigator.clipboard.writeText(c.quote || '').then(() => {
          copyBtn.textContent = 'Copied';
          setTimeout(() => { copyBtn.textContent = 'Copy Ref'; }, 1500);
        });
      });

      cardHeader.append(titleSpan, copyBtn);
      const quote = node('blockquote', c.quote, 'citation-quote');
      card.append(cardHeader, quote);
      container.append(card);
    }
  }

  // Latency & Metadata Bar
  const meta = node('div', undefined, 'meta-bar');
  if (data.timings_ms && data.timings_ms.total) {
    const t = data.timings_ms;
    const parts = [`Latency: ${t.total.toFixed(1)}ms`];
    if (t.llm !== undefined) parts.push(`LLM: ${t.llm.toFixed(1)}ms`);
    if (t.dense !== undefined) parts.push(`Chroma: ${t.dense.toFixed(1)}ms`);
    if (t.hybrid !== undefined) parts.push(`RRF: ${t.hybrid.toFixed(1)}ms`);
    if (data.policy_version) parts.push(`Version: ${data.policy_version.substring(0, 8)}`);
    meta.append(node('span', parts.join(' · '), 'timing-badge'));
  }
  container.append(meta);

  return container;
}

async function askQuestion(text) {
  const q = text.trim();
  if (!q) return;

  const messages = $('messages');
  // Render user question
  const userMsg = node('div', q, 'msg-user');
  messages.append(userMsg);

  $('question').value = '';
  $('send').disabled = true;
  $('loading').textContent = 'Searching policy documents and validating citations...';
  messages.scrollTop = messages.scrollHeight;

  try {
    const data = await api('/api/v1/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q })
    });
    $('loading').textContent = '';
    const answerCard = renderAnswer(data);
    messages.append(answerCard);
  } catch (err) {
    $('loading').textContent = '';
    const errorCard = node('div', undefined, 'msg-assistant');
    errorCard.append(
      node('div', 'REQUEST ERROR', 'status-pill temporary_error'),
      node('div', err.message, 'msg-answer')
    );
    messages.append(errorCard);
  } finally {
    $('send').disabled = false;
    messages.scrollTop = messages.scrollHeight;
  }
}

// Preset persona buttons
async function initApp() {
  try {
    const res = await fetch('/api/v1/demo/tokens');
    if (res.ok) {
      demoTokens = await res.json();
    }
  } catch (e) {
    console.error('Failed to load demo tokens', e);
  }

  document.querySelectorAll('.preset-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const key = btn.dataset.key;
      const tok = demoTokens[key];
      if (tok) {
        setToken(tok, `Switched persona`);
        // Add notification in chat
        const notice = node('div', undefined, 'welcome-card');
        notice.append(
          node('div', `Session switched to ${btn.querySelector('.persona-name').textContent.trim()} (${btn.querySelector('.persona-role').textContent.trim()}). Authenticated via signed corporate JWT claims.`)
        );
        $('messages').append(notice);
        $('messages').scrollTop = $('messages').scrollHeight;
      }
    });
  });

  // Suggested prompt chips
  document.querySelectorAll('.prompt-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      $('question').value = chip.dataset.q;
      askQuestion(chip.dataset.q);
    });
  });

  // 1-Click Sample Upload button
  const sampleBtn = $('load-sample-v2');
  if (sampleBtn) {
    sampleBtn.addEventListener('click', async () => {
      sampleBtn.disabled = true;
      sampleBtn.textContent = 'Ingesting & activating Version 2...';
      try {
        const res = await api('/api/v1/admin/demo-load-sample/2', { method: 'POST' });
        $('admin-result').textContent = `[SUCCESS] Version 2 activated.\n\nVersion ID: ${res.id}\nStatus: ${res.status}\nDocument: ${res.document_name}\nCreated: ${res.created_at}\n\nNote: Escort cutoff is now 9:00 PM (was 8:00 PM in v1).`;
        const alertMsg = node('div', undefined, 'msg-assistant');
        alertMsg.append(
          node('div', 'POLICY UPDATE ACTIVATED', 'status-pill answered'),
          node('div', 'Version 2 has been activated for Apex Technologies. The female security escort requirement cutoff is now 9:00 PM (previously 8:00 PM). Ask "When is a security escort mandatory?" to verify the live update!')
        );
        $('messages').append(alertMsg);
        $('messages').scrollTop = $('messages').scrollHeight;
      } catch (err) {
        if (err.message && err.message.includes('Policy administrator role required')) {
          $('admin-result').textContent = `[ACCESS DENIED] Policy administrator role required.\n\nYou are currently authenticated as an Employee. Uploading, activating policies, and viewing audit trails require the "policy_admin" role.\n\nQuick Fix: Click "Apex Administration (Sarah · Policy Admin)" under Corporate Client Session above, then try again.`;
        } else {
          $('admin-result').textContent = `[ERROR] Activation failed: ${err.message}`;
        }
      } finally {
        sampleBtn.disabled = false;
        sampleBtn.textContent = 'Activate Policy Version 2 (Apex 9 PM Escort)';
      }
    });
  }

  // Restore saved session or auto-connect default Apex Employee
  try {
    const saved = localStorage.getItem('commutepolicy_token');
    if (saved) {
      setToken(saved, 'Restored saved session');
    } else if (demoTokens['COMPANY_A_employee']) {
      setToken(demoTokens['COMPANY_A_employee'], 'Auto-connected default');
    }
  } catch (e) {
    if (demoTokens['COMPANY_A_employee']) {
      setToken(demoTokens['COMPANY_A_employee'], 'Auto-connected default');
    }
  }
}

// Session form
$('session').addEventListener('submit', event => {
  event.preventDefault();
  const next = $('token').value.trim();
  if (next) setToken(next, 'Custom token applied');
});

$('logout').addEventListener('click', () => {
  clearSession();
  const badge = $('tenant-badge');
  if (badge) badge.style.display = 'none';
});

// Chat submit form
$('question-form').addEventListener('submit', event => {
  event.preventDefault();
  askQuestion($('question').value);
});

// Submit on Enter without Shift
$('question').addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    $('question-form').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
  }
});

// Manual File Upload
$('upload').addEventListener('submit', async event => {
  event.preventDefault();
  const file = $('policy').files[0];
  if (!file) return;

  const form = new FormData();
  form.append('file', file);
  $('admin-result').textContent = 'Ingesting and vectorizing document...';

  try {
    const res = await api('/api/v1/admin/policies/upload', {
      method: 'POST',
      body: form
    });
    $('admin-result').textContent = `[SUCCESS] Policy document activated:\n${JSON.stringify(res, null, 2)}`;
  } catch (err) {
    if (err.message && err.message.includes('Policy administrator role required')) {
      $('admin-result').textContent = `[ACCESS DENIED] Policy administrator role required.\n\nYou are currently authenticated as an Employee. Uploading and activating policies requires the "policy_admin" role.\n\nQuick Fix: Click "Apex Administration (Sarah · Policy Admin)" under Corporate Client Session above to grant administrator access, then click Upload.`;
    } else {
      $('admin-result').textContent = `[ERROR] Upload failed: ${err.message}`;
    }
  }
});

// Admin buttons
$('versions').addEventListener('click', async () => {
  try {
    const list = await api('/api/v1/admin/policies/versions');
    $('admin-result').textContent = JSON.stringify(list, null, 2);
  } catch (err) {
    if (err.message && err.message.includes('Policy administrator role required')) {
      $('admin-result').textContent = `[ACCESS DENIED] Policy administrator role required.\n\nClick "Apex Administration (Sarah · Policy Admin)" above to view active policy versions.`;
    } else {
      $('admin-result').textContent = err.message;
    }
  }
});

$('audit').addEventListener('click', async () => {
  try {
    const events = await api('/api/v1/admin/audit?limit=20');
    $('admin-result').textContent = JSON.stringify(events, null, 2);
  } catch (err) {
    if (err.message && err.message.includes('Policy administrator role required')) {
      $('admin-result').textContent = `[ACCESS DENIED] Policy administrator role required.\n\nClick "Apex Administration (Sarah · Policy Admin)" above to view the security audit log.`;
    } else {
      $('admin-result').textContent = err.message;
    }
  }
});

window.addEventListener('DOMContentLoaded', initApp);
