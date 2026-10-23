const chatPanel = document.getElementById('chat-panel');
const chatUnavailable = document.getElementById('chat-unavailable');
const chatLog = document.getElementById('chat-log');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const chatSend = document.getElementById('chat-send');

let history = [];

function addMessage(role, text) {
  const div = document.createElement('div');
  div.className = `chat-msg ${role}`;
  div.textContent = (role === 'user' ? 'You: ' : role === 'error' ? 'Error: ' : '') + text;
  chatLog.appendChild(div);
  chatLog.scrollTop = chatLog.scrollHeight;
}

export async function initChat(onPlanReady) {
  let available = false;
  try {
    const status = await fetch('/api/agent/status').then((r) => r.json());
    available = Boolean(status.available);
  } catch {
    available = false;
  }

  if (!available) {
    chatPanel.style.display = 'none';
    chatUnavailable.style.display = 'block';
    return;
  }
  chatPanel.style.display = 'flex';
  chatUnavailable.style.display = 'none';

  chatForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const text = chatInput.value.trim();
    if (!text) return;

    addMessage('user', text);
    history.push({ role: 'user', content: text });
    chatInput.value = '';
    chatSend.disabled = true;

    try {
      const resp = await fetch('/api/agent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: history }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || `Server error: ${resp.status}`);

      addMessage('assistant', data.reply);
      history.push({ role: 'assistant', content: data.reply });
      if (data.plan) onPlanReady(data.plan);
    } catch (err) {
      addMessage('error', err.message);
    } finally {
      chatSend.disabled = false;
      chatInput.focus();
    }
  });
}
