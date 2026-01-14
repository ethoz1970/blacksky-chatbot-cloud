// Authentication functions - Medium login, user verification

// DOM element references (set by app.js)
let avatarBtn, avatarDropdown, avatarGreeting;
let mediumSignInBtn, softSignInBtn, dashboardBtn, signOutBtn;
let mediumLoginOverlay, mediumLoginClose, mediumLoginForm;
let mediumLoginTitle, mediumLoginSubmit, mediumLoginAlt, mediumLoginError;

function initAuthElements() {
  avatarBtn = document.getElementById('avatarBtn');
  avatarDropdown = document.getElementById('avatarDropdown');
  avatarGreeting = document.getElementById('avatarGreeting');
  mediumSignInBtn = document.getElementById('mediumSignIn');
  softSignInBtn = document.getElementById('softSignIn');
  dashboardBtn = document.getElementById('dashboardBtn');
  signOutBtn = document.getElementById('signOut');
  mediumLoginOverlay = document.getElementById('mediumLoginOverlay');
  mediumLoginClose = document.getElementById('mediumLoginClose');
  mediumLoginForm = document.getElementById('mediumLoginForm');
  mediumLoginTitle = document.getElementById('mediumLoginTitle');
  mediumLoginSubmit = document.getElementById('mediumLoginSubmit');
  mediumLoginAlt = document.getElementById('mediumLoginAlt');
  mediumLoginError = document.getElementById('mediumLoginError');
}

// Update avatar display based on current user
function updateAvatarUI() {
  if (currentUserName && !currentUserName.startsWith('ANON')) {
    // Known user (soft login or hard login)
    avatarBtn.textContent = currentUserName.charAt(0).toUpperCase();
    avatarBtn.classList.add('known');

    // Add verified badge for hard login
    if (currentAuthMethod === 'hard') {
      avatarBtn.innerHTML = currentUserName.charAt(0).toUpperCase() + '<span class="verified-badge">&#10003;</span>';
      avatarBtn.classList.add('verified');
    } else {
      avatarBtn.innerHTML = currentUserName.charAt(0).toUpperCase();
      avatarBtn.classList.remove('verified');
    }

    let html = '<span class="user-name">' + currentUserName;
    if (currentAuthMethod === 'hard') {
      html += ' <span class="verified-text">&#10003; Verified</span>';
    }
    html += '</span>';

    if (currentUserCompany) {
      html += '<span class="user-detail"><span class="user-detail-label">Company:</span>' + currentUserCompany + '</span>';
    }
    if (currentUserEmail) {
      html += '<span class="user-detail"><span class="user-detail-label">Email:</span>' + currentUserEmail + '</span>';
    }
    if (currentUserPhone) {
      html += '<span class="user-detail"><span class="user-detail-label">Phone:</span>' + currentUserPhone + '</span>';
    }

    // Show "Secure your account" for soft login users
    if (currentAuthMethod !== 'hard') {
      html += '<span class="auth-upgrade-prompt">Secure your account</span>';
    }

    avatarGreeting.innerHTML = html;

    // Show dashboard and sign out, hide sign in options for known users
    softSignInBtn.style.display = 'none';
    // Show "Create Account" for soft users, hide for hard users
    mediumSignInBtn.style.display = currentAuthMethod === 'hard' ? 'none' : 'block';
    mediumSignInBtn.textContent = 'Create Account';
    dashboardBtn.style.display = 'block';
    signOutBtn.style.display = 'block';
  } else {
    // Anonymous user (no name or ANON timestamp name)
    avatarBtn.textContent = '?';
    avatarBtn.innerHTML = '?';
    avatarBtn.classList.remove('known');
    avatarBtn.classList.remove('verified');

    let html = '<span class="user-name">Guest</span>';
    html += '<span class="auth-upgrade-prompt">Create account to save progress</span>';
    avatarGreeting.innerHTML = html;

    // Show sign in options, hide dashboard and sign out
    softSignInBtn.style.display = 'block';
    mediumSignInBtn.style.display = 'block';
    mediumSignInBtn.textContent = 'Create Account';
    dashboardBtn.style.display = 'none';
    signOutBtn.style.display = 'none';
  }
}

function signOut() {
  // Clear auth token
  localStorage.removeItem('blacksky_auth_token');

  // Clear user ID from all storage before generating new one
  localStorage.removeItem('blacksky_user_id');
  deleteCookie('blacksky_user_id');

  // Generate new anonymous user ID
  userId = generateUUID();
  setCookie('blacksky_user_id', userId, 30);

  // Clear all user info
  currentUserName = null;
  currentUserEmail = null;
  currentUserPhone = null;
  currentUserCompany = null;
  currentAuthMethod = 'soft';  // Reset to anonymous
  updateAvatarUI();

  // Reset conversation
  conversationMessages = [];
  currentConversationId = null;

  // Clear chat and show fresh welcome with typewriter effect
  showWelcomeMessage();

  // Reset verification state
  pendingMatches = null;
  awaitingVerification = false;
}

async function signIn() {
  // Trigger Maurice to introduce himself (no user message shown)
  if (isLoading) return;

  isLoading = true;
  const sendBtn = document.getElementById('send');
  sendBtn.disabled = true;
  showTyping();

  try {
    const res = await fetch(`${API_HOST}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, introduce: true })
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
          if (data === '[DONE]') break;
          try {
            const parsed = JSON.parse(data);
            if (parsed.token) {
              fullResponse += parsed.token;
              textDiv.innerHTML = formatResponse(fullResponse);
              const now = Date.now();
              if (now - lastScrollTime > 300) {
                messageDiv.scrollIntoView({ behavior: 'smooth', block: 'end' });
                lastScrollTime = now;
              }
            }
          } catch (e) {
            // Skip malformed JSON
          }
        }
      }
    }

    messageDiv.scrollIntoView({ behavior: 'smooth', block: 'end' });

    // Track Maurice's introduction in conversation
    if (fullResponse) {
      conversationMessages.push({ role: 'assistant', content: fullResponse });
    }

  } catch (err) {
    console.error('Sign in error:', err);
    hideTyping();
    addMessage("Sorry, I couldn't introduce myself right now. Please try again.", 'bot');
  } finally {
    isLoading = false;
    const sendBtn = document.getElementById('send');
    sendBtn.disabled = false;
    document.getElementById('input').focus();
  }
}

// Fetch user context on page load to check if Maurice knows them
async function fetchUserContext() {
  try {
    const res = await fetch(`${API_HOST}/user/${userId}/context`);
    if (res.ok) {
      const data = await res.json();
      currentAuthMethod = data.auth_method || 'soft';
      if (data.name) {
        currentUserName = data.name;
        currentUserEmail = data.email;
        currentUserPhone = data.phone;
        currentUserCompany = data.company;
      }
      updateAvatarUI();
    }
  } catch (e) {
    // Silently fail - user is just anonymous
    console.log('Could not fetch user context');
  }
}

function openMediumLoginModal(registerMode) {
  isMediumRegisterMode = registerMode;
  mediumLoginTitle.textContent = registerMode ? 'Create Account' : 'Sign In';
  mediumLoginSubmit.textContent = registerMode ? 'Create Account' : 'Sign In';
  mediumLoginAlt.textContent = registerMode
    ? 'Already have an account? Sign In'
    : 'Need an account? Create one';
  mediumLoginError.textContent = '';
  mediumLoginForm.reset();
  mediumLoginOverlay.classList.add('active');
  document.getElementById('mediumName').focus();
}

function closeMediumLoginModal() {
  mediumLoginOverlay.classList.remove('active');
  mediumLoginForm.reset();
  mediumLoginError.textContent = '';
}

// Verify stored auth token on page load
async function verifyStoredToken(token) {
  try {
    const res = await fetch(`${API_HOST}/auth/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token })
    });
    if (res.ok) {
      const data = await res.json();
      if (data.valid) {
        // Update user state
        userId = data.user_id;
        setCookie('blacksky_user_id', userId, 30);
        currentUserName = data.name;
        currentUserEmail = data.email;
        currentAuthMethod = 'hard';  // Verified token = hard login
        updateAvatarUI();
        return true;
      }
    }
  } catch (e) {
    console.error('Auth verification failed:', e);
  }
  // Invalid token - clear it
  localStorage.removeItem('blacksky_auth_token');
  return false;
}

async function initializeAuth() {
  // Check for stored token (medium login)
  const storedToken = localStorage.getItem('blacksky_auth_token');
  if (storedToken) {
    const verified = await verifyStoredToken(storedToken);
    if (verified) {
      return; // Token still valid
    }
  }

  // No stored auth - check regular user context
  await fetchUserContext();
}
