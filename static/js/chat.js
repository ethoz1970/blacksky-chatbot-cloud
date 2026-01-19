// Chat functions - messages, formatting, streaming

// Typewriter effect for welcome message
function typeWriter(text, elementId, speed = 80, onComplete = null) {
  const element = document.getElementById(elementId);
  if (!element) return;

  let i = 0;
  element.textContent = '';

  function type() {
    if (i < text.length) {
      element.textContent += text.charAt(i);
      i++;
      setTimeout(type, speed);
    } else if (onComplete) {
      onComplete();
    }
  }
  type();
}

// Start follow-up message after delay
function startFollowUpTimer() {
  followUpTimer = setTimeout(() => {
    const followUpLine = document.getElementById('followUpLine');
    const cursor = document.getElementById('typewriterCursor');
    if (followUpLine && cursor) {
      // Move cursor to follow-up line
      cursor.remove();
      followUpLine.innerHTML = '<span id="followUpText"></span><span id="typewriterCursor" style="animation: blink 1s infinite;">|</span>';
      followUpLine.style.display = 'block';
      typeWriter('I am Maurice, the Blacksky AI. How can I help.', 'followUpText', 50);
    }
  }, 7000); // 7 seconds
}

// Cancel follow-up timer
function cancelFollowUpTimer() {
  if (followUpTimer) {
    clearTimeout(followUpTimer);
    followUpTimer = null;
  }
}

// Show welcome message with typewriter effect
function showWelcomeMessage() {
  const messages = document.getElementById('messages');
  messages.innerHTML = `
    <div class="message bot" id="welcomeMessage" style="flex:1;display:flex;align-items:center;justify-content:center;">
      <div class="message-text" style="background:none;border:none;padding:0;text-align:center;">
        <p style="font-size:1.5rem;color:#666;margin:0;"><span id="typewriterText"></span><span id="typewriterCursor" style="animation: blink 1s infinite;">|</span></p>
        <p id="followUpLine" style="font-size:1rem;color:#555;margin:0.5rem 0 0 0;display:none;"></p>
      </div>
    </div>
  `;
  typeWriter('... hello world ...', 'typewriterText', 80, startFollowUpTimer);
}

// Detect if user message contains a name (after Maurice asked)
function extractNameFromMessage(text) {
  // Words that commonly follow "I'm" or "I am" but aren't names
  const notNames = new Set([
    'not', 'just', 'very', 'so', 'really', 'quite', 'pretty', 'too',
    'looking', 'interested', 'curious', 'wondering', 'trying', 'hoping',
    'here', 'back', 'new', 'happy', 'glad', 'sorry', 'sure', 'fine',
    'good', 'great', 'okay', 'ok', 'well', 'busy', 'free', 'available',
    'calling', 'writing', 'reaching', 'contacting', 'asking', 'inquiring',
    'a', 'an', 'the', 'your', 'their', 'his', 'her', 'our', 'my',
    'working', 'using', 'building', 'developing', 'creating', 'running'
  ]);

  const patterns = [
    /(?:my name is|i'm|i am|call me|this is)\s+([a-z]+(?:\s+[a-z]+){0,2})/i,
    /^([a-z]+)(?:\s+here)?[.!]?$/i
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match && match[1].length >= 2 && match[1].length <= 30) {
      const words = match[1].trim().split(/\s+/);
      // Skip if first word is a common non-name word
      if (notNames.has(words[0].toLowerCase())) {
        continue;
      }
      // Capitalize first letter of each word
      const name = match[1].trim().replace(/\b\w/g, c => c.toUpperCase());
      return name;
    }
  }
  return null;
}

// Check if user is confirming their identity
function isConfirmation(text) {
  const confirmations = ['yes', 'yeah', 'yep', 'yup', 'that\'s me', 'thats me', 'correct', 'right', 'exactly', 'sure'];
  return confirmations.some(c => text.toLowerCase().includes(c));
}

// Look up user by name
async function lookupUserByName(name) {
  try {
    const res = await fetch(`${API_HOST}/user/lookup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name })
    });
    if (!res.ok) return null;
    return await res.json();
  } catch (e) {
    console.error('User lookup failed:', e);
    return null;
  }
}

// Link current session to existing user
async function linkToUser(targetUserId) {
  try {
    const res = await fetch(`${API_HOST}/user/link`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        current_user_id: userId,
        target_user_id: targetUserId
      })
    });
    if (res.ok) {
      const data = await res.json();
      // Update our userId to the linked user
      userId = data.new_user_id;
      setCookie('blacksky_user_id', userId, 30);
      console.log('Session linked to existing user:', userId);
      return true;
    }
  } catch (e) {
    console.error('User link failed:', e);
  }
  return false;
}

// Convert entity names in text to clickable links
function addEntityLinks(text) {
  for (const { pattern, key } of ENTITY_PATTERNS) {
    text = text.replace(pattern, `<span class="inline-link" data-panel-key="${key}">$&</span>`);
  }
  return text;
}

// Format quotes from Bruce Lee and Frank Ocean with styled blocks
function formatQuotes(text) {
  // Pattern: "quote text" — Source (em-dash, en-dash, or hyphen)
  text = text.replace(
    /"([^"]+)"\s*[—–-]\s*(Bruce Lee|Frank Ocean)/gi,
    '<div class="quote-block">"$1"<div class="quote-source">— $2</div></div>'
  );

  // Pattern: As X said, "quote" or X once said, "quote"
  text = text.replace(
    /(?:As\s+)?(Bruce Lee|Frank Ocean)\s+(?:once\s+)?said,?\s*"([^"]+)"/gi,
    '<div class="quote-block">"$2"<div class="quote-source">— $1</div></div>'
  );

  return text;
}

function getImageForTopic(text) {
  const lower = text.toLowerCase();

  // Federal agencies
  if (lower.includes('treasury')) return { src: '/static/images/treasury.png', alt: 'U.S. Department of Treasury', category: 'Federal Agency', panel: getPanel('treasury') };
  if (lower.includes('nih') || lower.includes('national institute of health')) return { src: '/static/images/nih.png', alt: 'National Institutes of Health', category: 'Federal Agency', panel: getPanel('nih') };
  if (lower.includes('fda')) return { src: '/static/images/fda.png', alt: 'Food & Drug Administration', category: 'Federal Agency', panel: getPanel('fda') };
  if (lower.includes('usda') || lower.includes('fsis') || lower.includes('food safety')) return { src: '/static/images/usda.png', alt: 'USDA Food Safety', category: 'Federal Agency', panel: getPanel('usda') };
  if (lower.includes('dot') || lower.includes('transportation')) return { src: '/static/images/transportation2.png.webp', alt: 'Department of Transportation', category: 'Federal Agency', panel: getPanel('dot') };
  if (lower.includes('sec') || lower.includes('securities')) return { src: '/static/images/sec.png', alt: 'Securities & Exchange Commission', category: 'Federal Agency', panel: getPanel('sec') };
  if (lower.includes('hhs') || lower.includes('health and human')) return { src: '/static/images/hhs.png', alt: 'Health & Human Services', category: 'Federal Agency', panel: getPanel('hhs') };
  if (lower.includes('usaid')) return { src: '/static/images/usaid.png', alt: 'USAID', category: 'Federal Agency', panel: getPanel('usaid') };

  // Companies
  if (lower.includes('vanguard')) return { src: '/static/images/vanguard.png', alt: 'Vanguard', category: 'Enterprise Client', panel: getPanel('vanguard') };
  if (lower.includes('mastercard')) return { src: '/static/images/mastercard.png', alt: 'Mastercard', category: 'Enterprise Client', panel: getPanel('mastercard') };
  if (lower.includes('blue cross') || lower.includes('bcbs')) return { src: '/static/images/bcbs.png', alt: 'Blue Cross Blue Shield', category: 'Enterprise Client', panel: getPanel('bcbs') };
  if (lower.includes('world bank')) return { src: '/static/images/worldbank.png', alt: 'World Bank', category: 'International', panel: getPanel('worldbank') };
  if (lower.includes('billboard')) return { src: '/static/images/billboard.png', alt: 'Billboard', category: 'Media', panel: getPanel('billboard') };
  if (lower.includes('national gallery') || lower.includes('art gallery')) return { src: '/static/images/nga.png.webp', alt: 'National Gallery of Art', category: 'Cultural Institution', panel: getPanel('nga') };

  // Technologies
  if (lower.includes('drupal')) return { src: '/static/images/drupal.png', alt: 'Drupal', category: 'Technology', panel: getPanel('drupal') };
  if (lower.includes('kubernetes') || lower.includes('k8s')) return { src: '/static/images/kubernetes.png', alt: 'Kubernetes', category: 'Technology', panel: getPanel('kubernetes') };
  if (lower.includes('azure')) return { src: '/static/images/azure.png', alt: 'Microsoft Azure', category: 'Cloud Platform', panel: getPanel('azure') };
  if (lower.includes('aws') || lower.includes('amazon web')) return { src: '/static/images/aws.png', alt: 'Amazon Web Services', category: 'Cloud Platform', panel: getPanel('aws') };

  return null;
}

function formatMessage(text) {
  // Strip markdown bold **text** and __text__
  text = text.replace(/\*\*(.+?)\*\*/g, '$1');
  text = text.replace(/__(.+?)__/g, '$1');

  // Strip markdown italic *text* and _text_
  text = text.replace(/\*(.+?)\*/g, '$1');
  text = text.replace(/_(.+?)_/g, '$1');

  // Split into lines
  let lines = text.split('\n');
  let formatted = [];
  let inList = false;
  let listItems = [];

  for (let line of lines) {
    // Check if line is a list item
    if (line.trim().match(/^[-•›]\s+/) || line.trim().match(/^\d+\.\s+/)) {
      // Clean the bullet/number
      let content = line.trim().replace(/^[-•›]\s+/, '').replace(/^\d+\.\s+/, '');
      listItems.push(content);
      inList = true;
    } else {
      // If we were in a list, close it
      if (inList && listItems.length > 0) {
        let listHtml = listItems.map(item => `<span class="list-item">› ${item}</span>`).join('');
        formatted.push(listHtml);
        listItems = [];
        inList = false;
      }
      // Add regular line
      if (line.trim()) {
        formatted.push(line);
      }
    }
  }

  // Handle any remaining list items
  if (listItems.length > 0) {
    let listHtml = listItems.map(item => `<span class="list-item">› ${item}</span>`).join('');
    formatted.push(listHtml);
  }

  return formatted.join('<br><br>');
}

function addMessage(text, sender) {
  const messages = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = `message ${sender}`;

  const label = sender === 'bot' ? 'Blacksky' : (currentUserName || 'You');
  const content = sender === 'bot'
    ? formatMessage(text)
    : text.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>');

  // Check for relevant image
  let imageHtml = '';
  if (sender === 'bot') {
    const image = getImageForTopic(text);
    if (image) {
      // Use encodeURIComponent for unicode-safe encoding
      const clickable = image.panel ? 'data-panel="' + encodeURIComponent(JSON.stringify(image.panel)) + '"' : '';
      const clickClass = image.panel ? 'clickable' : '';
      imageHtml = `
        <div class="message-image-wrapper ${clickClass}" ${clickable}>
          <img src="${image.src}" alt="${image.alt}" class="message-image" onerror="this.parentElement.style.display='none'">
          <div class="message-image-meta">
            <span class="message-image-category">${image.category}</span>
            <span class="message-image-caption">${image.alt}${image.panel ? ' ›' : ''}</span>
          </div>
        </div>
      `;
    }
  }

  div.innerHTML = `
    <div class="message-label">${label}</div>
    <div class="message-text">${imageHtml}${content}</div>
  `;

  messages.appendChild(div);
  div.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function showTyping() {
  const messages = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'message bot';
  div.id = 'typing';
  div.innerHTML = `
    <div class="message-label">Blacksky</div>
    <div class="message-text"><span class="typing-indicator"></span></div>
  `;
  messages.appendChild(div);
  div.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function hideTyping() {
  const typing = document.getElementById('typing');
  if (typing) typing.remove();
}

// Format response text (convert newlines, etc.)
function formatResponse(text) {
  // Format quotes first, then add entity links, then paragraph formatting
  return formatQuotes(addEntityLinks(text))
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>')
    .replace(/^/, '<p>')
    .replace(/$/, '</p>');
}

// Save conversation on page unload or inactivity
async function saveConversation() {
  if (conversationMessages.length === 0) return;

  try {
    const requestBody = {
      user_id: userId,
      messages: conversationMessages
    };

    // Include conversation_id if we have one (for updates)
    if (currentConversationId) {
      requestBody.conversation_id = currentConversationId;
    }

    const res = await fetch(`${API_HOST}/conversation/end`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
      keepalive: true // Ensure request completes even if page unloads
    });

    // Check if user info was extracted and update avatar
    if (res.ok) {
      const data = await res.json();

      // Store conversation ID for future updates
      if (data.conversation_id && !currentConversationId) {
        currentConversationId = data.conversation_id;
      }

      let updated = false;
      if (data.name_extracted && !currentUserName) {
        currentUserName = data.name_extracted;
        updated = true;
      }
      if (data.email_extracted && !currentUserEmail) {
        currentUserEmail = data.email_extracted;
        updated = true;
      }
      if (data.phone_extracted && !currentUserPhone) {
        currentUserPhone = data.phone_extracted;
        updated = true;
      }
      if (data.company_extracted && !currentUserCompany) {
        currentUserCompany = data.company_extracted;
        updated = true;
      }
      if (updated) {
        updateAvatarUI();
      }
    }
  } catch (e) {
    console.error('Failed to save conversation:', e);
  }
}

async function sendMessage() {
  const input = document.getElementById('input');
  const sendBtn = document.getElementById('send');
  const text = input.value.trim();
  if (!text || isLoading) return;

  // Hide welcome message cursor and remove welcome message on first prompt
  const welcomeMsg = document.getElementById('welcomeMessage');
  if (welcomeMsg) {
    cancelFollowUpTimer();
    welcomeMsg.remove();
  }

  addMessage(text, 'user');
  input.value = '';
  autoResize();

  // Track message and update activity
  conversationMessages.push({ role: 'user', content: text });
  lastActivityTime = Date.now();

  // Check if user is confirming their identity
  if (awaitingVerification && pendingMatches && pendingMatches.length > 0) {
    if (isConfirmation(text)) {
      // User confirmed - link to the first match
      const linked = await linkToUser(pendingMatches[0].user_id);
      if (linked) {
        // Update avatar with confirmed name
        currentUserName = pendingMatches[0].name;
        updateAvatarUI();
      }
    }
    // Reset verification state either way
    awaitingVerification = false;
    pendingMatches = null;
  }

  // Check if user just provided their name
  const extractedName = extractNameFromMessage(text);
  let matchesContext = null;

  if (extractedName) {
    const lookup = await lookupUserByName(extractedName);
    if (lookup && lookup.count > 0) {
      pendingMatches = lookup.matches;
      awaitingVerification = true;
      // Build context for Maurice to ask verification question
      matchesContext = lookup.matches.map(m => ({
        name: m.name,
        last_topic: m.last_topic || 'general questions'
      }));
    } else {
      // New user - update avatar with their name
      currentUserName = extractedName;
      updateAvatarUI();
    }
  }

  isLoading = true;
  sendBtn.disabled = true;
  showTyping();

  try {
    // Build request body
    const requestBody = {
      message: text,
      user_id: userId,
      is_admin: isAdminMode,
      panel_views: panelViewHistory.map(v => v.title)
    };

    // Add potential matches for Maurice to verify
    if (matchesContext) {
      requestBody.potential_matches = matchesContext;
    }

    const res = await fetch(`${API_HOST}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody)
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    hideTyping();

    // Create bot message container for streaming
    const messages = document.getElementById('messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message bot';
    messageDiv.innerHTML = `
      <div class="message-label">Maurice</div>
      <div class="message-text"></div>
    `;
    messages.appendChild(messageDiv);
    messageDiv.scrollIntoView({ behavior: 'smooth', block: 'end' });

    const textDiv = messageDiv.querySelector('.message-text');
    let fullResponse = '';
    let lastScrollTime = 0;

    // Read the stream
    const reader = res.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split('\n');

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') {
            break;
          }
          try {
            const parsed = JSON.parse(data);
            if (parsed.token) {
              fullResponse += parsed.token;
              textDiv.innerHTML = formatResponse(fullResponse);
              // Throttle scroll to every 300ms to avoid jank
              const now = Date.now();
              if (now - lastScrollTime > 300) {
                messageDiv.scrollIntoView({ behavior: 'smooth', block: 'end' });
                lastScrollTime = now;
              }
            }
            if (parsed.error) {
              throw new Error(parsed.error);
            }
          } catch (e) {
            // Skip malformed JSON
          }
        }
      }
    }
    // Final scroll after streaming completes
    messageDiv.scrollIntoView({ behavior: 'smooth', block: 'end' });

    // Track bot response
    if (fullResponse) {
      conversationMessages.push({ role: 'assistant', content: fullResponse });
      // Save conversation after each response
      saveConversation();
    }

    // Check for images after streaming completes
    const image = getImageForTopic(fullResponse);
    if (image) {
      const clickable = image.panel ? 'data-panel="' + encodeURIComponent(JSON.stringify(image.panel)) + '"' : '';
      const clickClass = image.panel ? 'clickable' : '';
      const imageHtml = `
        <div class="message-image-wrapper ${clickClass}" ${clickable}>
          <img src="${image.src}" alt="${image.alt}" class="message-image" onerror="this.parentElement.style.display='none'">
          <div class="message-image-meta">
            <span class="message-image-category">${image.category}</span>
            <span class="message-image-caption">${image.alt}${image.panel ? ' ›' : ''}</span>
          </div>
        </div>
      `;
      textDiv.insertAdjacentHTML('afterend', imageHtml);
    }

  } catch (err) {
    console.error('Stream error:', err);
    hideTyping();
    addMessage("Sorry, there are a lot of people talking in my ear at once. Try again in a moment?", 'bot');
  } finally {
    isLoading = false;
    sendBtn.disabled = false;
    input.focus();
  }
}

// Admin mode functions
async function loginAsAdmin() {
  const password = prompt("Enter admin password:");
  if (!password) return;

  try {
    const resp = await fetch(`${API_HOST}/admin/chat/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password })
    });

    if (resp.ok) {
      isAdminMode = true;
      showAdminIndicator(true);
      addSystemMessage("Admin mode activated. You'll see enhanced information in responses.");
    } else {
      alert("Invalid password");
    }
  } catch (e) {
    console.error("Admin login failed:", e);
    alert("Admin login failed. Please try again.");
  }
}

function logoutAdmin() {
  isAdminMode = false;
  showAdminIndicator(false);
  addSystemMessage("Admin mode deactivated.");
}

function showAdminIndicator(show) {
  let indicator = document.getElementById('adminIndicator');
  if (!indicator) {
    indicator = document.createElement('div');
    indicator.id = 'adminIndicator';
    indicator.innerHTML = 'ADMIN MODE <button onclick="logoutAdmin()">Exit</button>';
    const header = document.querySelector('.header');
    if (header) {
      header.appendChild(indicator);
    }
  }
  indicator.style.display = show ? 'flex' : 'none';
}

function addSystemMessage(text) {
  const messages = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'message system';
  div.innerHTML = `
    <div class="message-text system-message">${text}</div>
  `;
  messages.appendChild(div);
  div.scrollIntoView({ behavior: 'smooth', block: 'end' });
}
