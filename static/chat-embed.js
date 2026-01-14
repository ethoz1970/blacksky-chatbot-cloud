(function() {
  // Get API host from global var or script src
  let API_HOST = window.CHAT_API || '';
  
  if (!API_HOST) {
    const scriptTag = document.currentScript;
    if (scriptTag && scriptTag.src) {
      const url = new URL(scriptTag.src);
      API_HOST = `${url.protocol}//${url.host}`;
    } else {
      API_HOST = window.location.origin;
    }
  }

  // Find container
  const container = document.getElementById('blacksky-chat-embed');
  if (!container) {
    console.error('Blacksky Chat: No element with id="blacksky-chat-embed" found');
    return;
  }

  // Inject styles
  const styles = `
    .bsc-container {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #000;
      color: #fff;
      padding: 40px;
      min-height: 500px;
      display: flex;
      flex-direction: column;
    }

    .bsc-messages {
      flex: 1;
      min-height: 250px;
      max-height: 400px;
      overflow-y: auto;
      margin-bottom: 40px;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }

    .bsc-message {
      line-height: 1.6;
      font-size: 1rem;
    }

    .bsc-message.bot {
      color: #888;
    }

    .bsc-message.user {
      color: #fff;
    }

    .bsc-message.user::before {
      content: '→ ';
      color: #444;
    }

    .bsc-typing {
      color: #444;
    }

    .bsc-typing::after {
      content: '...';
      animation: bsc-dots 1.5s infinite;
    }

    @keyframes bsc-dots {
      0%, 20% { content: '.'; }
      40% { content: '..'; }
      60%, 100% { content: '...'; }
    }

    .bsc-input-area {
      border-top: 1px solid #222;
      padding-top: 40px;
    }

    .bsc-textarea {
      width: 100%;
      background: transparent;
      border: none;
      color: #fff;
      font-family: inherit;
      font-size: 1rem;
      line-height: 1.6;
      resize: none;
      outline: none;
      margin-bottom: 20px;
    }

    .bsc-textarea::placeholder {
      color: #444;
    }

    .bsc-button {
      background: transparent;
      border: 1px solid #333;
      color: #888;
      padding: 12px 32px;
      font-family: inherit;
      font-size: 0.875rem;
      letter-spacing: 0.05em;
      cursor: pointer;
      transition: all 0.2s;
    }

    .bsc-button:hover {
      border-color: #fff;
      color: #fff;
    }

    .bsc-button:disabled {
      border-color: #222;
      color: #333;
      cursor: not-allowed;
    }

    .bsc-container ::-webkit-scrollbar {
      width: 4px;
    }

    .bsc-container ::-webkit-scrollbar-track {
      background: transparent;
    }

    .bsc-container ::-webkit-scrollbar-thumb {
      background: #333;
    }
  `;

  const styleSheet = document.createElement('style');
  styleSheet.textContent = styles;
  document.head.appendChild(styleSheet);

  // Create HTML
  container.innerHTML = `
    <div class="bsc-container">
      <div class="bsc-messages" id="bsc-messages">
        <div class="bsc-message bot">How can I help you today?</div>
      </div>
      <div class="bsc-input-area">
        <textarea 
          class="bsc-textarea"
          id="bsc-input" 
          rows="5" 
          placeholder="Type your message..."
        ></textarea>
        <button class="bsc-button" id="bsc-send">Send</button>
      </div>
    </div>
  `;

  // Get elements
  const messages = document.getElementById('bsc-messages');
  const input = document.getElementById('bsc-input');
  const sendBtn = document.getElementById('bsc-send');
  
  let isLoading = false;

  function formatMessage(text) {
    // Convert line breaks to <br>
    let formatted = text.replace(/\n/g, '<br>');
    
    // Convert bullet points (- item) to proper list styling
    formatted = formatted.replace(/^- (.+)$/gm, '• $1');
    formatted = formatted.replace(/(<br>)- /g, '$1• ');
    
    // Convert numbered lists (1. item)
    formatted = formatted.replace(/(<br>)(\d+)\. /g, '$1$2. ');
    
    return formatted;
  }

  function addMessage(text, sender) {
    const div = document.createElement('div');
    div.className = `bsc-message ${sender}`;
    
    if (sender === 'bot') {
      div.innerHTML = formatMessage(text);
    } else {
      div.textContent = text;
    }
    
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
  }

  function showTyping() {
    const div = document.createElement('div');
    div.className = 'bsc-message bot bsc-typing';
    div.id = 'bsc-typing';
    div.textContent = 'thinking';
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
  }

  function hideTyping() {
    const typing = document.getElementById('bsc-typing');
    if (typing) typing.remove();
  }

  async function sendMessage() {
    const text = input.value.trim();
    if (!text || isLoading) return;

    addMessage(text, 'user');
    input.value = '';
    
    isLoading = true;
    sendBtn.disabled = true;
    showTyping();

    try {
      const res = await fetch(`${API_HOST}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text })
      });
      
      const data = await res.json();
      hideTyping();
      addMessage(data.response, 'bot');
    } catch (err) {
      hideTyping();
      addMessage('Connection lost. Try again.', 'bot');
    } finally {
      isLoading = false;
      sendBtn.disabled = false;
      input.focus();
    }
  }

  sendBtn.addEventListener('click', sendMessage);
  
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

})();
