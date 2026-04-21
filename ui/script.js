const $ = id => document.getElementById(id);
const [joinP, chatP, userIn, joinBtn, statEl, chatLog, msgForm, msgIn, qBtns, uploadBtn, imageInput, audioUploadBtn, audioInput] = 
  ['joinPanel','chatPanel','usernameInput','joinButton','status','chatLog','messageForm','messageInput','predefinedQuestions','uploadBtn','imageInput','audioUploadBtn','audioInput'].map($);

let ws = null, username = '', pendingMsg = null;

const setStatus = (txt, cls = 'neutral') => {
  statEl.textContent = txt;
  statEl.className = `status ${cls}`;
};

const fmtBytes = (bytes) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(2)} MB`;
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

// ─── Audio message rendering ─────────────────────────────────────────────────

const appendAudio = (sender, url, originalUrl, filename, audioInfo) => {
  const row = document.createElement('div');
  row.className = `chat-row ${sender === username ? 'self' : 'message'} audio-message`;

  // Header
  const caption = document.createElement('div');
  caption.className = 'audio-caption';
  const who = sender === username ? 'You' : sender;
  caption.innerHTML = `<span class="audio-icon">&#9835;</span> <strong>${who}</strong> shared audio: <em>${filename}</em>`;
  row.appendChild(caption);

  // Audio player
  const player = document.createElement('audio');
  player.controls = true;
  player.preload = 'metadata';
  player.src = url;
  player.className = 'audio-player';
  row.appendChild(player);

  // Quick stats bar
  if (audioInfo) {
    const quickStats = document.createElement('div');
    quickStats.className = 'audio-quick-stats';
    quickStats.innerHTML = `
      <span class="stat-chip compression">${audioInfo.compression_ratio}x</span>
      <span class="stat-chip size">${fmtBytes(audioInfo.original_bytes)} → ${fmtBytes(audioInfo.compressed_bytes)}</span>
      <span class="stat-chip loss">Loss ${ (100 * Math.pow(10, -audioInfo.psnr / 10)).toFixed(2) }% reduced</span>
      <span class="stat-chip psnr">PSNR ${audioInfo.psnr} dB</span>
    `;
    row.appendChild(quickStats);

    // Expandable details
    const toggle = document.createElement('button');
    toggle.className = 'audio-stats-toggle';
    toggle.textContent = '▸ Show detailed stats';
    const details = document.createElement('div');
    details.className = 'audio-stats-details hidden';
    details.innerHTML = buildAudioStatsHTML(audioInfo);

    toggle.onclick = () => {
      const open = !details.classList.contains('hidden');
      details.classList.toggle('hidden');
      toggle.textContent = open ? '▸ Show detailed stats' : '▾ Hide detailed stats';
    };
    row.appendChild(toggle);
    row.appendChild(details);
  }

  chatLog.appendChild(row);
  chatLog.scrollTop = chatLog.scrollHeight;
};

function buildAudioStatsHTML(info) {
  const orig = info.original_features || {};
  const comp = info.compressed_features || {};
  const freq = info.frequency_analysis || {};
  const bands = freq.bands || {};

  let html = `<div class="stats-grid">`;

  // Compression summary
  html += `
    <div class="stats-section">
      <h4>Compression Summary</h4>
      <table class="stats-table">
        <tr><td>Original Size</td><td>${fmtBytes(info.original_bytes)}</td></tr>
        <tr><td>Compressed Size</td><td>${fmtBytes(info.compressed_bytes)}</td></tr>
        <tr><td>Compression Ratio</td><td>${info.compression_ratio}x</td></tr>
        <tr><td>Size Reduction</td><td>${info.loss_percent}%</td></tr>
        <tr><td>PSNR</td><td>${info.psnr} dB</td></tr>
        <tr><td>Target</td><td>${info.target_codec} · ${info.target_bitrate} · ${info.target_sample_rate} · ${info.target_channels}</td></tr>
      </table>
    </div>`;

  // Original vs compressed features
  html += `
    <div class="stats-section">
      <h4>Audio Features Comparison</h4>
      <table class="stats-table comparison">
        <thead><tr><th>Feature</th><th>Original</th><th>Compressed</th></tr></thead>
        <tbody>
          <tr><td>Codec</td><td>${orig.codec || '—'}</td><td>${comp.codec || '—'}</td></tr>
          <tr><td>Sample Rate</td><td>${orig.sample_rate ? orig.sample_rate + ' Hz' : '—'}</td><td>${comp.sample_rate ? comp.sample_rate + ' Hz' : '—'}</td></tr>
          <tr><td>Channels</td><td>${orig.channels || '—'}</td><td>${comp.channels || '—'}</td></tr>
          <tr><td>Layout</td><td>${orig.channel_layout || '—'}</td><td>${comp.channel_layout || '—'}</td></tr>
          <tr><td>Bitrate</td><td>${orig.bitrate_kbps ? orig.bitrate_kbps + ' kbps' : '—'}</td><td>${comp.bitrate_kbps ? comp.bitrate_kbps + ' kbps' : '—'}</td></tr>
          <tr><td>Duration</td><td>${orig.duration_sec ? orig.duration_sec + ' s' : '—'}</td><td>${comp.duration_sec ? comp.duration_sec + ' s' : '—'}</td></tr>
          <tr><td>Format</td><td>${orig.format_name || '—'}</td><td>${comp.format_name || '—'}</td></tr>
        </tbody>
      </table>
    </div>`;

  // Frequency band analysis
  if (Object.keys(bands).length > 0) {
    html += `
      <div class="stats-section full-width">
        <h4>Frequency Band Retention</h4>
        <div class="freq-bands">`;

    const bandLabels = {
      sub_bass: 'Sub Bass', bass: 'Bass', low_mid: 'Low Mid',
      mid: 'Mid', upper_mid: 'Upper Mid', high: 'High'
    };

    for (const [key, data] of Object.entries(bands)) {
      const pct = data.retention_percent;
      const barColor = pct >= 90 ? 'var(--success)' : pct >= 70 ? 'var(--warning)' : 'var(--danger)';
      const clampedPct = Math.min(pct, 100);
      html += `
        <div class="freq-band-row">
          <span class="band-label">${bandLabels[key] || key} <span class="band-range">(${data.range_hz} Hz)</span></span>
          <div class="band-bar-track">
            <div class="band-bar-fill" style="width:${clampedPct}%;background:${barColor}"></div>
          </div>
          <span class="band-value">${pct}%</span>
        </div>`;
    }

    if (freq.spectral_correlation != null) {
      html += `<div class="spectral-corr">Spectral Correlation: <strong>${freq.spectral_correlation}</strong></div>`;
    }
    html += `</div></div>`;
  }

  html += `</div>`;
  return html;
}

// ─── WebSocket ───────────────────────────────────────────────────────────────

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
      const { type, text, username: sender, content, url, filename, compression, original_url, audio_info } = JSON.parse(e.data);
      if (type === 'system') return appendMsg(text, 'system');
      
      if (type === 'message') {
        if (sender === username && content === pendingMsg) return (pendingMsg = null);
        
        const msgClass = (sender === username) ? 'self' : 'message';
        const displayName = (sender === username) ? 'You' : sender;
        appendMsg(`${displayName}: ${content}`, msgClass);
      } else if (type === 'image') {
        appendImage(sender, url, filename, compression);
      } else if (type === 'audio') {
        appendAudio(sender, url, original_url, filename, audio_info);
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

const uploadAudio = async () => {
  const file = audioInput.files?.[0];
  if (!file) return;
  if (!file.type.startsWith('audio/')) return appendMsg('Only audio uploads are allowed.', 'system');
  
  const MAX_SIZE = 5 * 1024 * 1024; // 5MB
  if (file.size > MAX_SIZE) {
    return appendMsg('Audio file is too large! Maximum allowed size is 5MB.', 'system');
  }

  if (!ws || ws.readyState !== WebSocket.OPEN) return appendMsg('Connect first to upload audio.', 'system');

  const form = new FormData();
  form.append('file', file);
  form.append('username', username);

  setStatus('Compressing audio...', 'connecting');
  appendMsg('Uploading & compressing audio — this may take a moment...', 'system');
  try {
    const response = await fetch('/upload-audio', { method: 'POST', body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || data.message || 'Upload failed.');
    appendMsg('Audio uploaded & compressed successfully.', 'system');
  } catch (error) {
    appendMsg(`Audio upload error: ${error.message}`, 'system');
  } finally {
    setStatus('Connected', 'connected');
    audioInput.value = '';
  }
};

msgForm.onsubmit = (e) => {
  e.preventDefault();
  sendMsg(msgIn.value);
};

uploadBtn.onclick = () => imageInput.click();
imageInput.onchange = uploadImage;

audioUploadBtn.onclick = () => audioInput.click();
audioInput.onchange = uploadAudio;

document.querySelectorAll('.question-btn').forEach(btn => {
  btn.onclick = () => sendMsg(`/chat ${btn.dataset.question}`);
});

window.onbeforeunload = () => ws?.close();
