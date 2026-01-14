// Main application entry point - initialization and event binding

// Initialize all DOM element references
function initApp() {
  initAuthElements();
  initUIElements();

  // Set up event listeners
  setupAvatarEvents();
  setupMediumLoginEvents();
  setupPanelEvents();
  setupMenuEvents();
  setupChatEvents();
  setupKeyboardEvents();
  setupImageClickEvents();
  setupConversationSaving();

  // Start welcome typewriter effect
  typeWriter('... hello world ...', 'typewriterText', 80, startFollowUpTimer);

  // Initialize authentication
  initializeAuth();
}

// Avatar dropdown events
function setupAvatarEvents() {
  const avatarBtn = document.getElementById('avatarBtn');
  const avatarDropdown = document.getElementById('avatarDropdown');
  const mediumSignInBtn = document.getElementById('mediumSignIn');
  const softSignInBtn = document.getElementById('softSignIn');
  const dashboardBtn = document.getElementById('dashboardBtn');
  const signOutBtn = document.getElementById('signOut');

  // Toggle dropdown
  avatarBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    avatarDropdown.classList.toggle('active');
  });

  // Close dropdown when clicking outside
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.user-avatar')) {
      avatarDropdown.classList.remove('active');
    }
  });

  // Handle soft sign in - open modal in login mode
  softSignInBtn.addEventListener('click', () => {
    avatarDropdown.classList.remove('active');
    openMediumLoginModal(false);
  });

  // Handle medium sign in - open modal
  mediumSignInBtn.addEventListener('click', () => {
    avatarDropdown.classList.remove('active');
    openMediumLoginModal(true);
  });

  // Handle dashboard
  dashboardBtn.addEventListener('click', () => {
    avatarDropdown.classList.remove('active');
    openDashboard();
  });

  // Handle sign out
  signOutBtn.addEventListener('click', () => {
    avatarDropdown.classList.remove('active');
    signOut();
  });
}

// Medium login modal events
function setupMediumLoginEvents() {
  const mediumLoginOverlay = document.getElementById('mediumLoginOverlay');
  const mediumLoginClose = document.getElementById('mediumLoginClose');
  const mediumLoginForm = document.getElementById('mediumLoginForm');
  const mediumLoginAlt = document.getElementById('mediumLoginAlt');
  const mediumLoginSubmit = document.getElementById('mediumLoginSubmit');
  const mediumLoginError = document.getElementById('mediumLoginError');

  mediumLoginClose.addEventListener('click', closeMediumLoginModal);
  mediumLoginOverlay.addEventListener('click', (e) => {
    if (e.target === mediumLoginOverlay) closeMediumLoginModal();
  });

  // Toggle between register and login mode
  mediumLoginAlt.addEventListener('click', () => {
    openMediumLoginModal(!isMediumRegisterMode);
  });

  // Handle medium login form submission
  mediumLoginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    mediumLoginError.textContent = '';
    mediumLoginSubmit.disabled = true;
    mediumLoginSubmit.textContent = isMediumRegisterMode ? 'Creating...' : 'Signing in...';

    const name = document.getElementById('mediumName').value.trim();
    const password = document.getElementById('mediumPassword').value;
    const interest = document.getElementById('mediumInterest').value;

    try {
      const endpoint = isMediumRegisterMode ? '/auth/hard/register' : '/auth/hard/login';
      const res = await fetch(`${API_HOST}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name,
          password: password,
          interest_level: interest || null,
          user_id: userId
        })
      });

      const data = await res.json();

      if (res.ok && data.success) {
        // Store token and update state
        localStorage.setItem('blacksky_auth_token', data.token);
        userId = data.user_id;
        localStorage.setItem('blacksky_user_id', userId);
        currentUserName = data.name;
        currentAuthMethod = 'hard';  // Now a registered user

        closeMediumLoginModal();
        updateAvatarUI();
        addMessage(`Welcome${isMediumRegisterMode ? '' : ' back'}, ${currentUserName}!`, 'assistant');
      } else {
        mediumLoginError.textContent = data.detail || 'Authentication failed';
      }
    } catch (err) {
      console.error('Medium login error:', err);
      mediumLoginError.textContent = 'Connection error. Please try again.';
    } finally {
      mediumLoginSubmit.disabled = false;
      mediumLoginSubmit.textContent = isMediumRegisterMode ? 'Create Account' : 'Sign In';
    }
  });
}

// Slideout panel events
function setupPanelEvents() {
  const slideoutClose = document.getElementById('slideoutClose');
  const slideoutOverlay = document.getElementById('slideoutOverlay');

  slideoutClose.addEventListener('click', closePanel);
  slideoutOverlay.addEventListener('click', closePanel);
}

// Left menu events
function setupMenuEvents() {
  const menuToggleTitle = document.getElementById('menuToggleTitle');
  const menuClose = document.getElementById('menuClose');
  const menuOverlay = document.getElementById('menuOverlay');
  const menuItems = document.querySelectorAll('.menu-item');

  menuToggleTitle.addEventListener('click', openMenu);
  menuClose.addEventListener('click', closeMenu);
  menuOverlay.addEventListener('click', closeMenu);

  menuItems.forEach(item => {
    item.addEventListener('click', () => {
      const key = item.dataset.panelKey;
      const menuPanels = getPanels();
      if (menuPanels[key]) {
        closeMenu();
        setTimeout(() => openPanel(menuPanels[key]), 150);
      }
    });
  });
}

// Chat input and send events
function setupChatEvents() {
  const input = document.getElementById('input');
  const sendBtn = document.getElementById('send');

  sendBtn.addEventListener('click', sendMessage);
  input.addEventListener('input', autoResize);

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  input.focus();
}

// Keyboard shortcuts
function setupKeyboardEvents() {
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closePanel();
  });
}

// Click handlers for images and inline links
function setupImageClickEvents() {
  document.addEventListener('click', (e) => {
    // Handle clicks on images with panels
    const wrapper = e.target.closest('.message-image-wrapper.clickable');
    if (wrapper && wrapper.dataset.panel) {
      const panelData = JSON.parse(decodeURIComponent(wrapper.dataset.panel));
      openPanel(panelData);
    }

    // Handle inline text links
    const inlineLink = e.target.closest('.inline-link');
    if (inlineLink && inlineLink.dataset.panelKey) {
      const key = inlineLink.dataset.panelKey;
      const panel = getPanel(key);
      if (panel) {
        openPanel(panel);
      }
    }
  });
}

// Conversation saving (on unload and inactivity)
function setupConversationSaving() {
  window.addEventListener('beforeunload', saveConversation);

  // Check for inactivity every minute
  setInterval(() => {
    if (conversationMessages.length > 0 && Date.now() - lastActivityTime > INACTIVITY_TIMEOUT) {
      saveConversation();
      conversationMessages = [];
    }
  }, 60000);
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', initApp);
