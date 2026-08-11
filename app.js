/**
 * HanumanAI — Intelligent Agent Platform (Frontend)
 * Complete client-side application: WebSocket, chat, voice, screen capture, settings.
 */

class HanumanAI {
  constructor() {
    // WebSocket
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 10;
    this.reconnectDelay = 1000;

    // State
    this.currentMode = 'chat';
    this.conversations = {};
    this.currentConversationId = null;
    this.isStreaming = false;
    this.currentAssistantEl = null;
    this.currentAssistantText = '';
    this.screenAnalysisMode = false;
    this.screenAnalysisText = '';

    // Settings
    this.settings = {
      model: 'gemini-3.6-flash',
      temperature: 0.7,
      voiceId: '',
    };

    // Voice
    this.recognition = null;
    this.synthesis = window.speechSynthesis;
    this.isVoiceMode = false;
    this.isListening = false;

    // Mode config
    this.modes = {
      chat:      { icon: 'message-circle', name: 'Chat Agent' },
      task:      { icon: 'zap',            name: 'Task Agent' },
      code:      { icon: 'code-2',         name: 'Code Agent' },
      knowledge: { icon: 'book-open',      name: 'Knowledge Agent' },
    };
  }

  /* ====================================================================
     Initialization
     ==================================================================== */

  init() {
    this.loadSettings();
    this.loadConversations();
    this.setupMarked();
    this.setupEventListeners();
    this.initVoice();
    this.populateVoiceSelect();

    // Show onboarding on first visit
    if (!localStorage.getItem('nexus_visited')) {
      document.getElementById('onboarding').classList.remove('hidden');
    } else {
      document.getElementById('onboarding').classList.add('hidden');
      this.connect();
    }

    // Ensure at least one conversation
    if (Object.keys(this.conversations).length === 0) {
      this.createConversation(false);
    } else {
      const lastId = localStorage.getItem('hanuman_current_conversation');
      if (lastId && this.conversations[lastId]) {
        this.switchConversation(lastId);
      } else {
        this.switchConversation(Object.keys(this.conversations)[0]);
      }
    }

    this.updateConversationList();
    lucide.createIcons();
  }

  setupMarked() {
    marked.setOptions({
      breaks: true,
      gfm: true,
      highlight: (code, lang) => {
        if (lang && hljs.getLanguage(lang)) {
          return hljs.highlight(code, { language: lang }).value;
        }
        return hljs.highlightAuto(code).value;
      },
    });
  }

  /* ====================================================================
     Event Listeners
     ==================================================================== */

  setupEventListeners() {
    const $ = (id) => document.getElementById(id);

    // Onboarding
    $('onboarding-submit').onclick = () => this.handleOnboarding();

    // Send
    $('send-btn').onclick = () => this.sendCurrentInput();
    $('message-input').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.sendCurrentInput();
      }
    });
    $('message-input').addEventListener('input', () => this.autoResizeInput());

    // Mode buttons
    document.querySelectorAll('.mode-btn').forEach((btn) => {
      btn.onclick = () => this.switchMode(btn.dataset.mode);
    });

    // Welcome chips
    document.querySelectorAll('.chip').forEach((chip) => {
      chip.onclick = () => {
        const prompt = chip.dataset.prompt;
        if (prompt === 'Analyze my screen') {
          this.captureScreen();
        } else if (prompt === 'Tell me about my system') {
          this.requestSystemInfo();
        } else {
          $('message-input').value = prompt;
          this.sendCurrentInput();
        }
      };
    });

    // Sidebar
    $('sidebar-toggle').onclick = () => this.toggleSidebar();
    $('mobile-menu-btn').onclick = () => this.toggleSidebarMobile();
    $('new-chat-btn').onclick = () => this.createConversation(true);

    // Header actions
    $('voice-toggle').onclick = () => this.toggleVoiceMode();
    $('voice-btn').onclick = () => this.toggleVoiceMode();
    $('screen-btn').onclick = () => this.captureScreen();
    $('export-btn').onclick = () => this.exportConversation();

    // Settings
    $('settings-btn').onclick = () => this.openSettings();
    $('settings-close').onclick = () => this.closeSettings();
    $('settings-save').onclick = () => this.applySettings();
    $('temperature-slider').addEventListener('input', (e) => {
      $('temp-value').textContent = e.target.value;
    });

    // Settings modal backdrop click to close
    $('settings-modal').querySelector('.overlay-backdrop').onclick = () => this.closeSettings();

    // Screen viewer
    $('screen-close').onclick = () => this.closeScreenViewer();
    $('screen-viewer').querySelector('.overlay-backdrop').onclick = () => this.closeScreenViewer();

    // Theme toggle
    $('theme-toggle').onclick = () => this.toggleTheme();
  }

  /* ====================================================================
     WebSocket
     ==================================================================== */

  connect() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) return;

    const statusDot = document.getElementById('connection-status');
    statusDot.className = 'status-dot connecting';
    statusDot.title = 'Connecting...';

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = location.hostname || 'localhost';
    const port = location.port || '8000';
    this.ws = new WebSocket(`${protocol}//${host}:${port}/ws`);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      statusDot.className = 'status-dot connected';
      statusDot.title = 'Connected';

      // Send configuration
      this.send({
        type: 'configure',
        model: this.settings.model,
        temperature: this.settings.temperature,
      });
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.handleMessage(data);
      } catch (err) {
        console.error('Failed to parse WS message:', err);
      }
    };

    this.ws.onclose = () => {
      statusDot.className = 'status-dot disconnected';
      statusDot.title = 'Disconnected';
      this.reconnect();
    };

    this.ws.onerror = (err) => {
      console.error('WebSocket error:', err);
    };
  }

  send(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  reconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) return;
    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.min(this.reconnectAttempts, 5);
    setTimeout(() => this.connect(), delay);
  }

  handleMessage(data) {
    switch (data.type) {
      case 'configured':
        // Configuration acknowledged
        break;

      case 'chunk':
        if (this.screenAnalysisMode) {
          this.screenAnalysisText += data.content;
          const el = document.getElementById('screen-analysis');
          el.innerHTML = this.renderMarkdown(this.screenAnalysisText);
          this.addCodeCopyButtons(el);
        } else {
          this.appendChunk(data.content);
        }
        break;

      case 'done':
        if (this.screenAnalysisMode) {
          this.screenAnalysisMode = false;
          this.screenAnalysisText = '';
        } else {
          this.finishAssistantMessage();
        }
        this.isStreaming = false;
        break;

      case 'screen_captured':
        this.displayScreenCapture(data.image);
        break;

      case 'command_result':
        this.displayCommandResult(data.output, data.exitCode);
        break;

      case 'system_info_result':
        this.displaySystemInfo(data.info);
        break;

      case 'error':
        this.showNotification(data.message, 'error');
        if (this.isStreaming) {
          this.finishAssistantMessage();
          this.isStreaming = false;
        }
        if (this.screenAnalysisMode) {
          this.screenAnalysisMode = false;
        }
        break;
    }
  }

  /* ====================================================================
     Chat
     ==================================================================== */

  sendCurrentInput() {
    const input = document.getElementById('message-input');
    const text = input.value.trim();
    if (!text || this.isStreaming) return;

    input.value = '';
    this.autoResizeInput();

    // Handle special commands
    if (text.toLowerCase().startsWith('/exec ')) {
      const command = text.substring(6).trim();
      this.executeCommand(command);
      return;
    }

    this.sendMessage(text);
  }

  sendMessage(text) {
    // Hide welcome
    const welcome = document.getElementById('welcome-message');
    if (welcome) welcome.style.display = 'none';

    // Add user message to UI
    this.addMessage('user', text);

    // Save to conversation history
    const conv = this.getCurrentConversation();
    conv.messages.push({ role: 'user', content: text });
    if (conv.messages.length === 1) {
      conv.title = text.substring(0, 35) + (text.length > 35 ? '...' : '');
      this.updateConversationList();
    }
    this.saveConversations();

    // Build API history
    const history = conv.messages.slice(0, -1).map((m) => ({
      role: m.role === 'assistant' ? 'model' : 'user',
      parts: [m.content],
    }));

    // Send to server
    this.isStreaming = true;
    this.startAssistantMessage();
    this.send({
      type: 'chat',
      message: text,
      mode: this.currentMode,
      history: history,
    });
  }

  addMessage(role, content) {
    const messages = document.getElementById('messages');
    const msgEl = document.createElement('div');
    msgEl.className = `message ${role}`;

    const avatarIcon = role === 'user' ? 'user' : 'bot';

    msgEl.innerHTML = `
      <div class="message-avatar">
        <i data-lucide="${avatarIcon}"></i>
      </div>
      <div class="message-bubble">
        <div class="message-content">${
          role === 'user'
            ? this.escapeHtml(content)
            : this.renderMarkdown(content)
        }</div>
        ${
          role === 'assistant'
            ? `<div class="message-actions">
                <button class="message-action-btn copy-msg-btn" title="Copy"><i data-lucide="copy"></i></button>
                <button class="message-action-btn speak-msg-btn" title="Speak"><i data-lucide="volume-2"></i></button>
               </div>`
            : ''
        }
      </div>
    `;

    // Bind action buttons
    if (role === 'assistant') {
      const copyBtn = msgEl.querySelector('.copy-msg-btn');
      const speakBtn = msgEl.querySelector('.speak-msg-btn');
      if (copyBtn) copyBtn.onclick = () => this.copyToClipboard(content);
      if (speakBtn) speakBtn.onclick = () => this.speak(content);
      this.addCodeCopyButtons(msgEl);
    }

    messages.appendChild(msgEl);
    lucide.createIcons({ nodes: [msgEl] });
    this.scrollToBottom();
  }

  startAssistantMessage() {
    const messages = document.getElementById('messages');
    const msgEl = document.createElement('div');
    msgEl.className = 'message assistant';

    msgEl.innerHTML = `
      <div class="message-avatar">
        <i data-lucide="bot"></i>
      </div>
      <div class="message-bubble">
        <div class="message-content">
          <div class="typing-indicator">
            <div class="dot"></div><div class="dot"></div><div class="dot"></div>
          </div>
        </div>
        <div class="message-actions">
          <button class="message-action-btn copy-msg-btn" title="Copy"><i data-lucide="copy"></i></button>
          <button class="message-action-btn speak-msg-btn" title="Speak"><i data-lucide="volume-2"></i></button>
        </div>
      </div>
    `;

    messages.appendChild(msgEl);
    lucide.createIcons({ nodes: [msgEl] });
    this.scrollToBottom();

    this.currentAssistantEl = msgEl;
    this.currentAssistantText = '';
  }

  appendChunk(text) {
    this.currentAssistantText += text;
    if (this.currentAssistantEl) {
      const contentEl = this.currentAssistantEl.querySelector('.message-content');
      contentEl.innerHTML = this.renderMarkdown(this.currentAssistantText);
      this.addCodeCopyButtons(contentEl);
      this.scrollToBottom();
    }
  }

  finishAssistantMessage() {
    if (!this.currentAssistantEl) return;

    const finalText = this.currentAssistantText;
    const contentEl = this.currentAssistantEl.querySelector('.message-content');
    contentEl.innerHTML = this.renderMarkdown(finalText);
    this.addCodeCopyButtons(contentEl);

    // Bind action buttons
    const copyBtn = this.currentAssistantEl.querySelector('.copy-msg-btn');
    const speakBtn = this.currentAssistantEl.querySelector('.speak-msg-btn');
    if (copyBtn) copyBtn.onclick = () => this.copyToClipboard(finalText);
    if (speakBtn) speakBtn.onclick = () => this.speak(finalText);

    lucide.createIcons({ nodes: [this.currentAssistantEl] });

    // Save to conversation
    const conv = this.getCurrentConversation();
    conv.messages.push({ role: 'assistant', content: finalText });
    this.saveConversations();

    // Auto-speak if voice mode on
    if (this.isVoiceMode) {
      this.speak(finalText);
    }

    this.currentAssistantEl = null;
    this.currentAssistantText = '';
    this.scrollToBottom();
  }

  /* ====================================================================
     Markdown Rendering
     ==================================================================== */

  renderMarkdown(text) {
    try {
      return marked.parse(text);
    } catch {
      return this.escapeHtml(text);
    }
  }

  addCodeCopyButtons(container) {
    container.querySelectorAll('pre').forEach((pre) => {
      if (pre.querySelector('.code-copy-btn')) return;
      const btn = document.createElement('button');
      btn.className = 'code-copy-btn';
      btn.innerHTML = '<i data-lucide="copy"></i>';
      btn.title = 'Copy code';
      btn.onclick = (e) => {
        e.stopPropagation();
        const code = pre.querySelector('code');
        this.copyToClipboard(code ? code.textContent : pre.textContent);
      };
      pre.style.position = 'relative';
      pre.appendChild(btn);
    });
    lucide.createIcons({ nodes: [container] });
  }

  escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  /* ====================================================================
     Voice
     ==================================================================== */

  initVoice() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn('SpeechRecognition not supported');
      return;
    }

    this.recognition = new SpeechRecognition();
    this.recognition.continuous = true;
    this.recognition.interimResults = false;
    this.recognition.lang = 'en-US';

    this.recognition.onresult = (event) => {
      let transcript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          transcript += event.results[i][0].transcript;
        }
      }
      if (transcript.trim()) {
        document.getElementById('message-input').value = transcript.trim();
        this.sendCurrentInput();
      }
    };

    this.recognition.onend = () => {
      this.isListening = false;
      // Restart if voice mode still active and not streaming
      if (this.isVoiceMode && !this.isStreaming) {
        setTimeout(() => {
          if (this.isVoiceMode && !this.synthesis.speaking) {
            this.startListening();
          }
        }, 300);
      }
    };

    this.recognition.onerror = (e) => {
      if (e.error !== 'aborted' && e.error !== 'no-speech') {
        console.error('Speech recognition error:', e.error);
      }
    };
  }

  populateVoiceSelect() {
    const select = document.getElementById('voice-select');
    const loadVoices = () => {
      const voices = this.synthesis.getVoices();
      select.innerHTML = '';
      voices.forEach((voice, i) => {
        const opt = document.createElement('option');
        opt.value = i;
        opt.textContent = `${voice.name} (${voice.lang})`;
        if (voice.default) opt.selected = true;
        select.appendChild(opt);
      });
      // Select saved voice
      if (this.settings.voiceId) {
        select.value = this.settings.voiceId;
      }
    };

    if (this.synthesis.getVoices().length) loadVoices();
    this.synthesis.onvoiceschanged = loadVoices;
  }

  toggleVoiceMode() {
    this.isVoiceMode = !this.isVoiceMode;
    const voiceToggle = document.getElementById('voice-toggle');
    const voiceBtn = document.getElementById('voice-btn');
    const indicator = document.getElementById('voice-indicator');

    if (this.isVoiceMode) {
      voiceToggle.classList.add('active');
      voiceBtn.classList.add('active');
      indicator.classList.remove('hidden');
      this.startListening();
      this.showNotification('Voice mode activated', 'success');
    } else {
      voiceToggle.classList.remove('active');
      voiceBtn.classList.remove('active');
      indicator.classList.add('hidden');
      this.stopListening();
      this.showNotification('Voice mode deactivated');
    }
  }

  startListening() {
    if (!this.recognition || this.isListening) return;
    try {
      this.recognition.start();
      this.isListening = true;
    } catch {
      // Already started
    }
  }

  stopListening() {
    if (!this.recognition) return;
    try {
      this.recognition.stop();
    } catch {
      // Already stopped
    }
    this.isListening = false;
  }

  speak(text) {
    // Strip markdown for cleaner speech
    const cleanText = text
      .replace(/```[\s\S]*?```/g, 'code block omitted')
      .replace(/#{1,6}\s/g, '')
      .replace(/\*\*(.*?)\*\*/g, '$1')
      .replace(/\*(.*?)\*/g, '$1')
      .replace(/`(.*?)`/g, '$1')
      .replace(/\[(.*?)\]\(.*?\)/g, '$1')
      .replace(/[|]/g, ' ')
      .replace(/[-]{3,}/g, '')
      .trim();

    if (!cleanText) return;

    // Stop any ongoing listening while speaking
    this.stopListening();
    this.synthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(cleanText);
    const voices = this.synthesis.getVoices();
    const voiceIdx = parseInt(this.settings.voiceId) || 0;
    if (voices[voiceIdx]) utterance.voice = voices[voiceIdx];
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    utterance.onend = () => {
      if (this.isVoiceMode) {
        setTimeout(() => this.startListening(), 300);
      }
    };

    this.synthesis.speak(utterance);
  }

  /* ====================================================================
     Screen Capture
     ==================================================================== */

  async captureScreen() {
    if (this.isStreaming) return;

    try {
      // Capture screen via browser Web API (solves OS/GPU black screen issues)
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { cursor: "always" },
        audio: false
      });

      const video = document.createElement("video");
      video.srcObject = stream;
      await video.play();

      // Draw video frame to canvas
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      // Stop stream tracks
      stream.getTracks().forEach(track => track.stop());

      // Get base64 PNG data
      const imageData = canvas.toDataURL("image/png");

      this.screenAnalysisMode = true;
      this.screenAnalysisText = '';
      document.getElementById('screen-analysis').innerHTML = '<div class="typing-indicator"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>';
      
      const imgEl = document.getElementById('screen-image');
      imgEl.src = imageData;
      imgEl.classList.add('loaded');
      document.getElementById('screen-viewer').classList.remove('hidden');

      this.isStreaming = true;
      this.send({
        type: 'analyze_screen_image',
        image: imageData,
        prompt: 'Describe everything you see on this screen in detail. Identify applications, windows, text, and any notable content. Be specific and helpful.',
      });

    } catch (err) {
      console.warn("Browser screen capture cancelled or failed, falling back to server capture:", err);
      if (err.name === 'NotAllowedError') {
        // User cancelled picker
        return;
      }
      this.screenAnalysisMode = true;
      this.screenAnalysisText = '';
      document.getElementById('screen-analysis').innerHTML = '<div class="typing-indicator"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>';
      document.getElementById('screen-image').classList.remove('loaded');
      document.getElementById('screen-viewer').classList.remove('hidden');

      this.isStreaming = true;
      this.send({
        type: 'analyze_screen',
        prompt: 'Describe everything you see on this screen in detail. Identify applications, windows, text, and any notable content. Be specific and helpful.',
      });
    }
  }

  displayScreenCapture(imageData) {
    const img = document.getElementById('screen-image');
    img.src = imageData;
    img.classList.add('loaded');
  }

  closeScreenViewer() {
    document.getElementById('screen-viewer').classList.add('hidden');
  }

  /* ====================================================================
     System Commands
     ==================================================================== */

  executeCommand(command) {
    // Show the command in chat
    const welcome = document.getElementById('welcome-message');
    if (welcome) welcome.style.display = 'none';

    this.addMessage('user', `/exec ${command}`);
    const conv = this.getCurrentConversation();
    conv.messages.push({ role: 'user', content: `/exec ${command}` });
    this.saveConversations();

    this.send({ type: 'execute_command', command: command });
  }

  displayCommandResult(output, exitCode) {
    const messages = document.getElementById('messages');
    const msgEl = document.createElement('div');
    msgEl.className = 'message assistant';

    const statusClass = exitCode === 0 ? '' : ' error';
    const statusText = exitCode === 0 ? '✅ Command succeeded' : `❌ Exit code: ${exitCode}`;

    msgEl.innerHTML = `
      <div class="message-avatar">
        <i data-lucide="terminal"></i>
      </div>
      <div class="message-bubble">
        <div class="message-content">
          <p><strong>${statusText}</strong></p>
          <div class="command-result${statusClass}">${this.escapeHtml(output || '(no output)')}</div>
        </div>
        <div class="message-actions">
          <button class="message-action-btn copy-msg-btn" title="Copy"><i data-lucide="copy"></i></button>
        </div>
      </div>
    `;

    const copyBtn = msgEl.querySelector('.copy-msg-btn');
    if (copyBtn) copyBtn.onclick = () => this.copyToClipboard(output);

    messages.appendChild(msgEl);
    lucide.createIcons({ nodes: [msgEl] });
    this.scrollToBottom();

    // Save to conversation
    const conv = this.getCurrentConversation();
    conv.messages.push({ role: 'assistant', content: `${statusText}\n\`\`\`\n${output}\n\`\`\`` });
    this.saveConversations();
  }

  requestSystemInfo() {
    const welcome = document.getElementById('welcome-message');
    if (welcome) welcome.style.display = 'none';

    this.addMessage('user', 'Tell me about my system');
    const conv = this.getCurrentConversation();
    conv.messages.push({ role: 'user', content: 'Tell me about my system' });
    this.saveConversations();

    this.send({ type: 'system_info' });
  }

  displaySystemInfo(info) {
    let md = '### 💻 System Information\n\n';
    md += '| Property | Value |\n|----------|-------|\n';
    for (const [key, value] of Object.entries(info)) {
      const label = key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
      md += `| ${label} | ${value} |\n`;
    }

    this.addMessage('assistant', md);
    const conv = this.getCurrentConversation();
    conv.messages.push({ role: 'assistant', content: md });
    this.saveConversations();
  }

  /* ====================================================================
     Conversations
     ==================================================================== */

  createConversation(switchTo = true) {
    const id = 'conv_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);
    this.conversations[id] = {
      id,
      title: 'New Chat',
      mode: this.currentMode,
      messages: [],
    };
    this.saveConversations();
    this.updateConversationList();
    if (switchTo) this.switchConversation(id);
    return id;
  }

  switchConversation(id) {
    if (!this.conversations[id]) return;

    this.currentConversationId = id;
    localStorage.setItem('hanuman_current_conversation', id);
    this.updateConversationList();

    // Render messages
    const messagesEl = document.getElementById('messages');
    messagesEl.innerHTML = '';

    const conv = this.conversations[id];
    if (conv.messages.length === 0) {
      // Show welcome
      messagesEl.innerHTML = `
        <div id="welcome-message" class="welcome">
          <div class="welcome-icon"><i data-lucide="sparkles"></i></div>
          <h2>Hello! I'm HanumanAI</h2>
          <p>Your intelligent AI agent with screen reading, system control, and voice capabilities.</p>
          <div class="welcome-chips">
            <button class="chip" data-prompt="What can you do?">✨ What can you do?</button>
            <button class="chip" data-prompt="Analyze my screen">📸 Analyze my screen</button>
            <button class="chip" data-prompt="Tell me about my system">💻 System info</button>
            <button class="chip" data-prompt="Help me write code">👨‍💻 Write code</button>
          </div>
        </div>
      `;
      // Rebind chips
      messagesEl.querySelectorAll('.chip').forEach((chip) => {
        chip.onclick = () => {
          const prompt = chip.dataset.prompt;
          if (prompt === 'Analyze my screen') this.captureScreen();
          else if (prompt === 'Tell me about my system') this.requestSystemInfo();
          else {
            document.getElementById('message-input').value = prompt;
            this.sendCurrentInput();
          }
        };
      });
    } else {
      conv.messages.forEach((m) => this.addMessage(m.role, m.content));
    }

    lucide.createIcons();
  }

  deleteConversation(id) {
    delete this.conversations[id];
    this.saveConversations();

    if (this.currentConversationId === id) {
      const remaining = Object.keys(this.conversations);
      if (remaining.length > 0) {
        this.switchConversation(remaining[0]);
      } else {
        this.createConversation(true);
      }
    }
    this.updateConversationList();
  }

  getCurrentConversation() {
    if (!this.currentConversationId || !this.conversations[this.currentConversationId]) {
      const id = this.createConversation(false);
      this.currentConversationId = id;
    }
    return this.conversations[this.currentConversationId];
  }

  updateConversationList() {
    const list = document.getElementById('conversation-list');
    list.innerHTML = '';

    const sorted = Object.values(this.conversations).sort(
      (a, b) => parseInt(b.id.split('_')[1]) - parseInt(a.id.split('_')[1])
    );

    sorted.forEach((conv) => {
      const item = document.createElement('div');
      item.className = `conversation-item${conv.id === this.currentConversationId ? ' active' : ''}`;
      item.innerHTML = `
        <span class="conv-title">${this.escapeHtml(conv.title)}</span>
        <button class="conv-delete" title="Delete"><i data-lucide="trash-2"></i></button>
      `;
      item.querySelector('.conv-title').onclick = () => this.switchConversation(conv.id);
      item.querySelector('.conv-delete').onclick = (e) => {
        e.stopPropagation();
        this.deleteConversation(conv.id);
      };
      list.appendChild(item);
    });

    lucide.createIcons({ nodes: [list] });
  }

  /* ====================================================================
     Agent Modes
     ==================================================================== */

  switchMode(mode) {
    if (!this.modes[mode]) return;
    this.currentMode = mode;

    // Update sidebar buttons
    document.querySelectorAll('.mode-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.mode === mode);
    });

    // Update header
    const icon = document.getElementById('current-mode-icon');
    icon.setAttribute('data-lucide', this.modes[mode].icon);
    document.getElementById('current-mode-name').textContent = this.modes[mode].name;
    lucide.createIcons({ nodes: [icon.parentElement] });
  }

  /* ====================================================================
     Settings
     ==================================================================== */

  handleOnboarding() {
    localStorage.setItem('nexus_visited', 'true');
    document.getElementById('onboarding').classList.add('hidden');
    this.connect();
    this.showNotification('Welcome to HanumanAI! 🚀', 'success');
  }

  openSettings() {
    document.getElementById('model-select').value = this.settings.model;
    document.getElementById('temperature-slider').value = this.settings.temperature;
    document.getElementById('temp-value').textContent = this.settings.temperature;
    if (this.settings.voiceId) {
      document.getElementById('voice-select').value = this.settings.voiceId;
    }
    document.getElementById('settings-modal').classList.remove('hidden');
  }

  closeSettings() {
    document.getElementById('settings-modal').classList.add('hidden');
  }

  applySettings() {
    this.settings.model = document.getElementById('model-select').value;
    this.settings.temperature = parseFloat(document.getElementById('temperature-slider').value);
    this.settings.voiceId = document.getElementById('voice-select').value;
    this.saveSettings();

    // Update model indicator
    document.getElementById('model-indicator').textContent = this.settings.model;

    // Send new config to server
    this.send({
      type: 'configure',
      model: this.settings.model,
      temperature: this.settings.temperature,
    });

    this.closeSettings();
    this.showNotification('Settings saved', 'success');
  }

  loadSettings() {
    try {
      const stored = localStorage.getItem('hanuman_settings');
      if (stored) {
        this.settings = { ...this.settings, ...JSON.parse(stored) };
        document.getElementById('model-indicator').textContent = this.settings.model;
      }
    } catch {
      // Use defaults
    }
  }

  saveSettings() {
    localStorage.setItem('hanuman_settings', JSON.stringify(this.settings));
  }

  loadConversations() {
    try {
      const stored = localStorage.getItem('hanuman_conversations');
      if (stored) {
        this.conversations = JSON.parse(stored);
      }
    } catch {
      this.conversations = {};
    }
  }

  saveConversations() {
    localStorage.setItem('hanuman_conversations', JSON.stringify(this.conversations));
  }

  /* ====================================================================
     Theme
     ==================================================================== */

  toggleTheme() {
    // Simple dark/light toggle (extend as needed)
    document.body.classList.toggle('light-theme');
    this.showNotification('Theme toggled');
  }

  /* ====================================================================
     Sidebar
     ==================================================================== */

  toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('collapsed');
  }

  toggleSidebarMobile() {
    document.getElementById('sidebar').classList.toggle('open');
  }

  /* ====================================================================
     Export
     ==================================================================== */

  exportConversation() {
    const conv = this.getCurrentConversation();
    if (!conv || conv.messages.length === 0) {
      this.showNotification('Nothing to export', 'error');
      return;
    }

    let md = `# ${conv.title}\n\n`;
    md += `_Exported from HanumanAI — ${new Date().toLocaleString()}_\n\n---\n\n`;

    conv.messages.forEach((m) => {
      const label = m.role === 'user' ? '**You**' : '**HanumanAI**';
      md += `${label}:\n\n${m.content}\n\n---\n\n`;
    });

    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `hanumanai-${conv.title.replace(/[^a-z0-9]/gi, '_').toLowerCase()}.md`;
    a.click();
    URL.revokeObjectURL(url);

    this.showNotification('Conversation exported', 'success');
  }

  /* ====================================================================
     UI Utilities
     ==================================================================== */

  scrollToBottom() {
    const messages = document.getElementById('messages');
    requestAnimationFrame(() => {
      messages.scrollTop = messages.scrollHeight;
    });
  }

  autoResizeInput() {
    const input = document.getElementById('message-input');
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 150) + 'px';
  }

  copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
      this.showNotification('Copied to clipboard', 'success');
    }).catch(() => {
      // Fallback
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      this.showNotification('Copied to clipboard', 'success');
    });
  }

  showNotification(message, type = '') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
  }
}

/* ======================================================================
   Bootstrap
   ====================================================================== */
document.addEventListener('DOMContentLoaded', () => {
  const app = new HanumanAI();
  app.init();

  // Expose for debugging
  window.hanumanAI = app;
});
