(function() {
  // Auto-detect API host from script src, or use current host
  const scriptTag = document.currentScript;
  let API_HOST = '';
  
  if (scriptTag && scriptTag.src) {
    const url = new URL(scriptTag.src);
    API_HOST = `${url.protocol}//${url.host}`;
  } else {
    API_HOST = window.location.origin;
  }

  // Configuration
  const CONFIG = {
    apiHost: API_HOST,
    title: 'Blacksky Assistant',
    subtitle: 'Ask me anything about our services',
    placeholder: 'Type your message...',
    welcomeMessage: "Hi! I'm the Blacksky assistant. How can I help you today?",
    position: 'bottom-right', // bottom-right or bottom-left
    primaryColor: '#2563eb',
    bubbleSize: 60
  };

  // Inject styles
  const styles = `
    #blacksky-chat-widget {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
      font-size: 14px;
      line-height: 1.5;
    }

    #blacksky-chat-bubble {
      position: fixed;
      ${CONFIG.position.includes('right') ? 'right: 20px;' : 'left: 20px;'}
      bottom: 20px;
      width: ${CONFIG.bubbleSize}px;
      height: ${CONFIG.bubbleSize}px;
      background: ${CONFIG.primaryColor};
      border-radius: 50%;
      cursor: pointer;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
      display: flex;
      align-items: center;
      justify-content: center;
      transition: transform 0.2s, box-shadow 0.2s;
      z-index: 9999;
    }

    #blacksky-chat-bubble:hover {
      transform: scale(1.05);
      box-shadow: 0 6px 16px rgba(0, 0, 0, 0.2);
    }

    #blacksky-chat-bubble svg {
      width: 28px;
      height: 28px;
      fill: white;
    }

    #blacksky-chat-window {
      position: fixed;
      ${CONFIG.position.includes('right') ? 'right: 20px;' : 'left: 20px;'}
      bottom: 90px;
      width: 380px;
      height: 520px;
      background: white;
      border-radius: 12px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
      display: none;
      flex-direction: column;
      overflow: hidden;
      z-index: 9998;
    }

    #blacksky-chat-window.open {
      display: flex;
    }

    #blacksky-chat-header {
      background: ${CONFIG.primaryColor};
      color: white;
      padding: 16px;
      flex-shrink: 0;
    }

    #blacksky-chat-header h3 {
      margin: 0 0 4px 0;
      font-size: 16px;
      font-weight: 600;
    }

    #blacksky-chat-header p {
      margin: 0;
      font-size: 12px;
      opacity: 0.9;
    }

    #blacksky-chat-messages {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      background: #f9fafb;
    }

    .blacksky-message {
      margin-bottom: 12px;
      display: flex;
      flex-direction: column;
    }

    .blacksky-message.user {
      align-items: flex-end;
    }

    .blacksky-message.bot {
      align-items: flex-start;
    }

    .blacksky-message-bubble {
      max-width: 80%;
      padding: 10px 14px;
      border-radius: 16px;
      word-wrap: break-word;
    }

    .blacksky-message.user .blacksky-message-bubble {
      background: ${CONFIG.primaryColor};
      color: white;
      border-bottom-right-radius: 4px;
    }

    .blacksky-message.bot .blacksky-message-bubble {
      background: white;
      color: #1f2937;
      border-bottom-left-radius: 4px;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
    }

    .blacksky-message-time {
      font-size: 10px;
      color: #9ca3af;
      margin-top: 4px;
      padding: 0 4px;
    }

    .blacksky-typing {
      display: flex;
      align-items: center;
      gap: 4px;
      padding: 10px 14px;
      background: white;
      border-radius: 16px;
      border-bottom-left-radius: 4px;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
    }

    .blacksky-typing-dot {
      width: 8px;
      height: 8px;
      background: #9ca3af;
      border-radius: 50%;
      animation: blacksky-typing 1.4s infinite;
    }

    .blacksky-typing-dot:nth-child(2) { animation-delay: 0.2s; }
    .blacksky-typing-dot:nth-child(3) { animation-delay: 0.4s; }

    @keyframes blacksky-typing {
      0%, 60%, 100% { transform: translateY(0); }
      30% { transform: translateY(-4px); }
    }

    #blacksky-chat-input-area {
      padding: 12px;
      background: white;
      border-top: 1px solid #e5e7eb;
      display: flex;
      gap: 8px;
      flex-shrink: 0;
    }

    #blacksky-chat-input {
      flex: 1;
      padding: 10px 14px;
      border: 1px solid #e5e7eb;
      border-radius: 20px;
      outline: none;
      font-size: 14px;
      transition: border-color 0.2s;
    }

    #blacksky-chat-input:focus {
      border-color: ${CONFIG.primaryColor};
    }

    #blacksky-chat-send {
      width: 40px;
      height: 40px;
      background: ${CONFIG.primaryColor};
      border: none;
      border-radius: 50%;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.2s;
    }

    #blacksky-chat-send:hover {
      background: ${CONFIG.primaryColor}dd;
    }

    #blacksky-chat-send:disabled {
      background: #9ca3af;
      cursor: not-allowed;
    }

    #blacksky-chat-send svg {
      width: 18px;
      height: 18px;
      fill: white;
    }

    @media (max-width: 480px) {
      #blacksky-chat-window {
        width: calc(100% - 40px);
        height: calc(100% - 120px);
        max-height: 500px;
      }
    }
  `;

  const styleSheet = document.createElement('style');
  styleSheet.textContent = styles;
  document.head.appendChild(styleSheet);

  // Create widget HTML
  const widgetHTML = `
    <div id="blacksky-chat-widget">
      <div id="blacksky-chat-bubble">
        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
          <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/>
        </svg>
      </div>
      <div id="blacksky-chat-window">
        <div id="blacksky-chat-header">
          <h3>${CONFIG.title}</h3>
          <p>${CONFIG.subtitle}</p>
        </div>
        <div id="blacksky-chat-messages"></div>
        <div id="blacksky-chat-input-area">
          <input type="text" id="blacksky-chat-input" placeholder="${CONFIG.placeholder}">
          <button id="blacksky-chat-send">
            <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
            </svg>
          </button>
        </div>
      </div>
    </div>
  `;

  // Find container or append to body
  let container = document.getElementById('blacksky-chat');
  if (!container) {
    container = document.body;
  }
  container.insertAdjacentHTML('beforeend', widgetHTML);

  // Get elements
  const bubble = document.getElementById('blacksky-chat-bubble');
  const chatWindow = document.getElementById('blacksky-chat-window');
  const messagesContainer = document.getElementById('blacksky-chat-messages');
  const input = document.getElementById('blacksky-chat-input');
  const sendButton = document.getElementById('blacksky-chat-send');

  let isOpen = false;
  let isLoading = false;

  // Toggle chat window
  function toggleChat() {
    isOpen = !isOpen;
    chatWindow.classList.toggle('open', isOpen);
    if (isOpen) {
      input.focus();
      // Add welcome message if empty
      if (messagesContainer.children.length === 0) {
        addMessage(CONFIG.welcomeMessage, 'bot');
      }
    }
  }

  // Format bot messages with line breaks and lists
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

  // Add message to chat
  function addMessage(text, sender) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `blacksky-message ${sender}`;
    
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    const bubbleContent = sender === 'bot' ? formatMessage(text) : escapeHtml(text);
    
    messageDiv.innerHTML = `
      <div class="blacksky-message-bubble">${bubbleContent}</div>
      <span class="blacksky-message-time">${time}</span>
    `;
    
    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  // Show typing indicator
  function showTyping() {
    const typingDiv = document.createElement('div');
    typingDiv.className = 'blacksky-message bot';
    typingDiv.id = 'blacksky-typing';
    typingDiv.innerHTML = `
      <div class="blacksky-typing">
        <div class="blacksky-typing-dot"></div>
        <div class="blacksky-typing-dot"></div>
        <div class="blacksky-typing-dot"></div>
      </div>
    `;
    messagesContainer.appendChild(typingDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  // Hide typing indicator
  function hideTyping() {
    const typing = document.getElementById('blacksky-typing');
    if (typing) typing.remove();
  }

  // Escape HTML to prevent XSS
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // Send message to API
  async function sendMessage() {
    const message = input.value.trim();
    if (!message || isLoading) return;

    // Add user message
    addMessage(message, 'user');
    input.value = '';
    
    // Show loading state
    isLoading = true;
    sendButton.disabled = true;
    showTyping();

    try {
      const response = await fetch(`${CONFIG.apiHost}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message }),
      });

      if (!response.ok) {
        throw new Error('Failed to get response');
      }

      const data = await response.json();
      hideTyping();
      addMessage(data.response, 'bot');

    } catch (error) {
      console.error('Chat error:', error);
      hideTyping();
      addMessage('Sorry, I had trouble connecting. Please try again.', 'bot');
    } finally {
      isLoading = false;
      sendButton.disabled = false;
    }
  }

  // Event listeners
  bubble.addEventListener('click', toggleChat);
  
  sendButton.addEventListener('click', sendMessage);
  
  input.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      sendMessage();
    }
  });

  // Close on escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && isOpen) {
      toggleChat();
    }
  });

})();
