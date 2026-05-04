// AI Companion Chat App
const API_BASE = 'http://127.0.0.1:8000';
const VOICE_BASE = 'http://127.0.0.1:8003';

// Session
function genId() {
  return 'sess_' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

let sessionId = localStorage.getItem('companion_session_id') || genId();
localStorage.setItem('companion_session_id', sessionId);

let userId = localStorage.getItem('companion_user_id') || 'user_001';
let userName = localStorage.getItem('companion_user_name') || '用户';
let voiceEnabled = localStorage.getItem('companion_voice_enabled') !== 'false';
let messages = JSON.parse(localStorage.getItem('companion_messages') || '[]');

// DOM refs
const chatMessages = document.getElementById('chatMessages');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const voiceBtn = document.getElementById('voiceBtn');
const typingIndicator = document.getElementById('typingIndicator');
const emotionBadge = document.getElementById('emotionBadge');
const avatarImage = document.getElementById('avatarImage');
const avatarGlow = document.getElementById('avatarGlow');
const avatarStatus = document.querySelector('.status-text');
const statusDot = document.querySelector('.status-dot');
const actionHint = document.getElementById('actionHint');
const voiceToggle = document.getElementById('voiceToggle');
const settingsBtn = document.getElementById('settingsBtn');
const settingsDrawer = document.getElementById('settingsDrawer');
const drawerOverlay = document.getElementById('drawerOverlay');
const closeDrawer = document.getElementById('closeDrawer');
const toastContainer = document.getElementById('toastContainer');

// Audio
let audioCtx = null;
let currentAudio = null;
let mediaRecorder = null;
let recordedChunks = [];
let isRecording = false;

function initAudio() {
  if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
}

function playAudio(url) {
  if (!voiceEnabled) return;
  initAudio();
  if (currentAudio) { currentAudio.pause(); currentAudio = null; }
  currentAudio = new Audio(url);
  currentAudio.play().catch(() => {});
  avatarImage.classList.add('speaking');
  avatarGlow.classList.add('active');
  currentAudio.onended = () => {
    avatarImage.classList.remove('speaking');
    avatarGlow.classList.remove('active');
    currentAudio = null;
  };
}

// Toast
function showToast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  toastContainer.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

// Render messages
function renderMessages() {
  chatMessages.innerHTML = '';
  messages.forEach(m => appendMessageBubble(m.role, m.content, m.time, false));
  scrollToBottom();
}

function appendMessageBubble(role, content, time, animate = true) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  if (animate) div.style.animation = 'fadeInUp 0.3s ease';

  const avatar = role === 'ai'
    ? '<div class="message-avatar"><img src="https://placehold.co/32x32/e94560/FFF?text=AI" alt="AI"></div>'
    : '<div class="message-avatar"><img src="https://placehold.co/32x32/2d3561/FFF?text=U" alt="User"></div>';

  const t = time || new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

  div.innerHTML = `
    ${avatar}
    <div class="message-content">
      <div class="message-bubble">${escapeHtml(content).replace(/\n/g, '<br>')}</div>
      <div class="message-time">${t}</div>
    </div>
  `;
  chatMessages.appendChild(div);
  scrollToBottom();
}

function escapeHtml(text) {
  const d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}

function scrollToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Typing indicator
function setTyping(show) {
  typingIndicator.style.display = show ? 'flex' : 'none';
  if (show) {
    statusDot.classList.add('thinking');
    avatarStatus.querySelector('.status-text').textContent = '思考中...';
  } else {
    statusDot.classList.remove('thinking');
    avatarStatus.querySelector('.status-text').textContent = '在线';
  }
}

// Send message
async function sendMessage(text) {
  if (!text.trim()) return;

  const userMsg = { role: 'user', content: text.trim(), time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) };
  messages.push(userMsg);
  appendMessageBubble('user', userMsg.content, userMsg.time);
  saveMessages();

  messageInput.value = '';
  messageInput.style.height = 'auto';
  setTyping(true);

  try {
    const resp = await fetch(`${API_BASE}/orchestrator/turn`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        user: { user_id: userId, display_name: userName },
        user_message: text.trim(),
        platform: 'app'
      })
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }

    const data = await resp.json();

    const aiMsg = {
      role: 'ai',
      content: data.assistant_message || '...',
      time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    };
    messages.push(aiMsg);
    appendMessageBubble('ai', aiMsg.content, aiMsg.time);
    saveMessages();

    // Update emotion
    if (data.emotion && data.emotion.primary) {
      const map = { neutral: '平静', happy: '开心', sad: '难过', angry: '生气', surprised: '惊讶', fearful: '害怕', disgusted: '厌恶', affectionate: '温柔', concerned: '担心', excited: '兴奋', calm: '安宁' };
      emotionBadge.textContent = map[data.emotion.primary] || data.emotion.primary;
    }

    // Action
    if (data.action_sequence && data.action_sequence.frames && data.action_sequence.frames.length > 0) {
      const actionMap = { idle: ' idle', talk: '说话中', listen: '倾听中', react_happy: '开心地笑了', react_sad: '有些难过', react_surprised: '很惊讶', react_thinking: '在思考', gesture_wave: '在挥手', gesture_nod: '点了点头', gesture_head_tilt: '歪头好奇' };
      const firstAction = data.action_sequence.frames[0].action_type;
      actionHint.textContent = actionMap[firstAction] || '';
      actionHint.classList.add('visible');
      setTimeout(() => actionHint.classList.remove('visible'), 3000);
    }

    // Voice
    if (data.voice_url) {
      playAudio(data.voice_url.startsWith('http') ? data.voice_url : `${VOICE_BASE}${data.voice_url}`);
    }

  } catch (err) {
    showToast('发送失败: ' + err.message, 'error');
    appendMessageBubble('ai', '抱歉，我暂时无法连接，请检查后端服务是否已启动。', new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }));
  } finally {
    setTyping(false);
  }
}

function saveMessages() {
  localStorage.setItem('companion_messages', JSON.stringify(messages.slice(-100)));
}

// Voice recording
async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    recordedChunks = [];

    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) recordedChunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      const blob = new Blob(recordedChunks, { type: 'audio/webm' });
      await transcribeAndSend(blob);
      stream.getTracks().forEach(t => t.stop());
    };

    mediaRecorder.start();
    isRecording = true;
    voiceBtn.classList.add('recording');
    voiceBtn.querySelector('.mic-icon').style.display = 'none';
    voiceBtn.querySelector('.recording-wave').style.display = 'flex';
    showToast('正在录音，松开发送', 'info');
  } catch (err) {
    showToast('无法访问麦克风: ' + err.message, 'error');
  }
}

function stopRecording() {
  if (!isRecording || !mediaRecorder) return;
  mediaRecorder.stop();
  isRecording = false;
  voiceBtn.classList.remove('recording');
  voiceBtn.querySelector('.mic-icon').style.display = 'block';
  voiceBtn.querySelector('.recording-wave').style.display = 'none';
}

async function transcribeAndSend(blob) {
  setTyping(true);
  try {
    const formData = new FormData();
    formData.append('audio', blob, 'recording.webm');
    formData.append('language', 'zh-CN');

    const resp = await fetch(`${VOICE_BASE}/voice/transcribe`, {
      method: 'POST',
      body: formData
    });

    if (!resp.ok) throw new Error('Transcription failed');
    const data = await resp.json();
    if (data.text) {
      await sendMessage(data.text);
    } else {
      showToast('未能识别语音', 'error');
    }
  } catch (err) {
    showToast('语音转文字失败: ' + err.message, 'error');
  } finally {
    setTyping(false);
  }
}

// Event listeners
sendBtn.addEventListener('click', () => sendMessage(messageInput.value));

messageInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage(messageInput.value);
  }
});

messageInput.addEventListener('input', () => {
  messageInput.style.height = 'auto';
  messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + 'px';
});

// Voice button (press and hold)
voiceBtn.addEventListener('mousedown', startRecording);
voiceBtn.addEventListener('mouseup', stopRecording);
voiceBtn.addEventListener('mouseleave', stopRecording);
voiceBtn.addEventListener('touchstart', e => { e.preventDefault(); startRecording(); });
voiceBtn.addEventListener('touchend', e => { e.preventDefault(); stopRecording(); });

// Voice toggle
voiceToggle.addEventListener('click', () => {
  voiceEnabled = !voiceEnabled;
  voiceToggle.classList.toggle('muted', !voiceEnabled);
  localStorage.setItem('companion_voice_enabled', voiceEnabled);
  showToast(voiceEnabled ? '语音已开启' : '语音已关闭', 'info');
});

if (!voiceEnabled) voiceToggle.classList.add('muted');

// Settings drawer
function openDrawer() {
  settingsDrawer.classList.add('open');
  drawerOverlay.classList.add('open');
  document.getElementById('userName').value = userName;
  document.getElementById('sessionIdDisplay').value = sessionId;
  checkApiStatus();
  checkServices();
}

function closeDrawerFn() {
  settingsDrawer.classList.remove('open');
  drawerOverlay.classList.remove('open');
}

settingsBtn.addEventListener('click', openDrawer);
closeDrawer.addEventListener('click', closeDrawerFn);
drawerOverlay.addEventListener('click', closeDrawerFn);

document.getElementById('userName').addEventListener('change', e => {
  userName = e.target.value || '用户';
  localStorage.setItem('companion_user_name', userName);
});

document.getElementById('gotoConfig').addEventListener('click', () => {
  window.open('../frontend_web/index.html', '_blank');
});

document.getElementById('clearChat').addEventListener('click', () => {
  if (confirm('确定要清空所有对话吗？')) {
    messages = [];
    localStorage.removeItem('companion_messages');
    chatMessages.innerHTML = '';
    showToast('对话已清空', 'success');
    closeDrawerFn();
  }
});

// Service status check
async function checkServices() {
  const list = document.getElementById('serviceList');
  const services = [
    { name: 'Core Orchestrator', port: 8000 },
    { name: 'Persona Engine', port: 8001 },
    { name: 'Memory System', port: 8002 },
    { name: 'Voice Layer', port: 8003 },
    { name: 'Action Layer', port: 8004 },
  ];

  list.innerHTML = services.map(s => `
    <div class="service-item" data-port="${s.port}">
      <span>${s.name}</span>
      <span class="status">检测中...</span>
    </div>
  `).join('');

  for (const s of services) {
    const el = list.querySelector(`[data-port="${s.port}"] .status`);
    try {
      const ctrl = new AbortController();
      const timeout = setTimeout(() => ctrl.abort(), 3000);
      const resp = await fetch(`http://127.0.0.1:${s.port}/health`, { signal: ctrl.signal });
      clearTimeout(timeout);
      if (resp.ok) {
        el.textContent = '正常';
        el.className = 'status ok';
      } else {
        throw new Error('bad status');
      }
    } catch {
      el.textContent = '离线';
      el.className = 'status fail';
    }
  }
}

// Check API config status
function checkApiStatus() {
  const el = document.getElementById('apiStatus');
  let config = {};
  try {
    const stored = localStorage.getItem('companion_ai_config');
    if (stored) config = JSON.parse(stored);
  } catch { /* ignore */ }

  const hasKey = config.openai_api_key || config.anthropic_api_key;
  if (hasKey) {
    const providers = [];
    if (config.openai_api_key) providers.push('OpenAI');
    if (config.anthropic_api_key) providers.push('Anthropic');
    const baseInfo = [];
    if (config.openai_base_url) baseInfo.push(`OpenAI: ${config.openai_base_url}`);
    if (config.anthropic_base_url) baseInfo.push(`Anthropic: ${config.anthropic_base_url}`);
    el.innerHTML = `已配置 (${providers.join(' / ')})` + (baseInfo.length ? `<br><span style="font-size:11px;opacity:0.7">${baseInfo.join(', ')}</span>` : '');
    el.classList.add('ready');
  } else {
    el.textContent = '未配置（请打开配置页面设置 API Key）';
    el.classList.remove('ready');
  }
}

// Init
checkApiStatus();
renderMessages();
if (messages.length === 0) {
  appendMessageBubble('ai', '你好呀，我是你的 AI 伴侣。有什么想聊的吗？', new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }));
}
