const $ = id => document.getElementById(id);
const [joinP, chatP, userIn, joinBtn, statEl, chatLog, msgForm, msgIn, qBtns, uploadBtn, imageInput] = 
  ['joinPanel','chatPanel','usernameInput','joinButton','status','chatLog','messageForm','messageInput','predefinedQuestions','uploadBtn','imageInput'].map($);

let ws = null, username = '', pendingMsg = null;

const setStatus = (txt, cls = 'neutral') => {
  statEl.textContent = txt;
  statEl.className = `status ${cls}`;
};

const appendMsg = (txt, type = 'message') => {
  const d = document.createElement('div');
  d.className = `chat-row ${type}`;
  d.textContent = txt;
  chatLog.appendChild(d);
  chatLog.scrollTop = chatLog.scrollHeight;
};

const appendImage = (sender, url, filename, compression) => {
  const row = document.createElement('div');
  row.className = `chat-row ${sender === username ? 'self' : 'message'}`;

  const caption = document.createElement('div');
  caption.className = 'chat-image-caption';
  const baseText = sender === username ? `You uploaded: ${filename}` : `${sender} uploaded: ${filename}`;
  const lossText = compression?.loss_percent != null ? ` — ${compression.loss_percent}% loss | PSNR: ${compression.psnr} dB` : '';
  caption.textContent = `${baseText}${lossText}`;

  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.target = '_blank';
  anchor.rel = 'noreferrer noopener';
  anchor.download = filename;

  const img = document.createElement('img');
  img.className = 'chat-image';
  img.src = url;
  img.alt = filename;

  anchor.appendChild(img);
  row.appendChild(caption);
  row.appendChild(anchor);
  chatLog.appendChild(row);
  chatLog.scrollTop = chatLog.scrollHeight;
};

const connectWS = () => {
  const host = window.location.host || '127.0.0.1:8000';
  ws = new WebSocket(`${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${host}/ws`);

  ws.onopen = () => {
    setStatus('Connected', 'connected');
    ws.send(JSON.stringify({ type: 'join', username }));
    appendMsg(`You joined as ${username}.`, 'system');
    msgIn.focus();
  };

  ws.onmessage = (e) => {
    try {
      const { type, text, username: sender, content, url, filename, compression } = JSON.parse(e.data);
      if (type === 'system') return appendMsg(text, 'system');
      
      if (type === 'message') {
        if (sender === username && content === pendingMsg) return (pendingMsg = null);
        
        const msgClass = (sender === username) ? 'self' : 'message';
        const displayName = (sender === username) ? 'You' : sender;
        appendMsg(`${displayName}: ${content}`, msgClass);
      } else if (type === 'image') {
        appendImage(sender, url, filename, compression);
      } else {
        appendMsg(e.data, 'system');
      }
    } catch {
      appendMsg(e.data, 'system');
    }
  };


  ws.onclose = () => {
    setStatus('Disconnected', 'disconnected');
    appendMsg('Connection closed. Reload to reconnect.', 'system');
  };

  ws.onerror = () => {
    setStatus('Error', 'error');
    appendMsg('Unable to connect.', 'system');
  };
};

joinBtn.onclick = () => {
  if (!(username = userIn.value.trim())) return userIn.focus();
  joinP.classList.add('hidden');
  chatP.classList.remove('hidden');
  setStatus('Connecting', 'connecting');
  connectWS();
};

const sendMsg = (content) => {
  if (!ws || ws.readyState !== WebSocket.OPEN) return appendMsg('Offline.', 'system');
  const txt = content.trim();
  if (!txt) return;

  const isBot = txt.startsWith('/bot ');
  const isChat = txt.startsWith('/chat ');
  const prefixLen = isBot ? 5 : (isChat ? 6 : 0);
  const display = (isBot || isChat) ? txt.substring(prefixLen).trim() : txt;
  pendingMsg = display;
  appendMsg(`You: ${display}`, 'self');
  ws.send(JSON.stringify({ type: 'message', content: txt }));
  msgIn.value = '';
};

const uploadImage = async () => {
  const file = imageInput.files?.[0];
  if (!file) return;
  if (!file.type.startsWith('image/')) return appendMsg('Only image uploads are allowed.', 'system');
  if (!ws || ws.readyState !== WebSocket.OPEN) return appendMsg('Connect first to upload images.', 'system');

  const form = new FormData();
  form.append('file', file);
  form.append('username', username);

  setStatus('Uploading...', 'connecting');
  try {
    const response = await fetch('/upload', { method: 'POST', body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || data.message || 'Upload failed.');
    appendMsg('Image uploaded successfully.', 'system');
  } catch (error) {
    appendMsg(`Upload error: ${error.message}`, 'system');
  } finally {
    setStatus('Connected', 'connected');
    imageInput.value = '';
  }
};

msgForm.onsubmit = (e) => {
  e.preventDefault();
  sendMsg(msgIn.value);
};

uploadBtn.onclick = () => imageInput.click();
imageInput.onchange = uploadImage;

document.querySelectorAll('.question-btn').forEach(btn => {
  btn.onclick = () => sendMsg(`/chat ${btn.dataset.question}`);
});

window.onbeforeunload = () => ws?.close();
