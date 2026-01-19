// UI functions - panels, menus, slideouts

// DOM element references (set by app.js)
let slideoutOverlay, slideoutPanel, slideoutTitle, slideoutContent, slideoutClose;
let menuOverlay, menuPanel, menuClose, menuToggleTitle;

function initUIElements() {
  slideoutOverlay = document.getElementById('slideoutOverlay');
  slideoutPanel = document.getElementById('slideoutPanel');
  slideoutTitle = document.getElementById('slideoutTitle');
  slideoutContent = document.getElementById('slideoutContent');
  slideoutClose = document.getElementById('slideoutClose');
  menuOverlay = document.getElementById('menuOverlay');
  menuPanel = document.getElementById('menuPanel');
  menuClose = document.getElementById('menuClose');
  menuToggleTitle = document.getElementById('menuToggleTitle');
}

// Slideout panel functions
function openPanel(panelData, options = {}) {
  // Track panel view for Maurice context
  const lastView = panelViewHistory[panelViewHistory.length - 1];
  if (!lastView || lastView.title !== panelData.title) {
    panelViewHistory.push({
      title: panelData.title,
      key: options.panelKey || null,
      timestamp: Date.now()
    });
    // Keep only last 10 views
    if (panelViewHistory.length > 10) {
      panelViewHistory.shift();
    }
  }

  // If opening from within a panel, save current state to history
  if (options.fromPanel && slideoutPanel.classList.contains('active')) {
    panelHistory.push({
      title: slideoutTitle.textContent,
      content: slideoutContent.innerHTML
    });
    updateBackButton();
  }

  slideoutTitle.textContent = panelData.title;
  slideoutContent.innerHTML = panelData.content;
  slideoutOverlay.classList.add('active');
  slideoutPanel.classList.add('active');
  document.body.style.overflow = 'hidden';

  // Scroll to top of new panel
  slideoutContent.scrollTop = 0;
  updateBackButton();
}

function closePanel() {
  slideoutOverlay.classList.remove('active');
  slideoutPanel.classList.remove('active');
  document.body.style.overflow = '';
  // Clear history when closing
  panelHistory = [];
  updateBackButton();
}

function goBackPanel() {
  if (panelHistory.length === 0) return;

  const previous = panelHistory.pop();
  slideoutTitle.textContent = previous.title;
  slideoutContent.innerHTML = previous.content;
  slideoutContent.scrollTop = 0;
  updateBackButton();
}

function updateBackButton() {
  const backBtn = document.getElementById('slideoutBack');
  if (backBtn) {
    backBtn.style.display = panelHistory.length > 0 ? 'flex' : 'none';
  }
}

// Left menu functions
function openMenu() {
  menuOverlay.classList.add('active');
  menuPanel.classList.add('active');
  document.body.style.overflow = 'hidden';
}

function closeMenu() {
  menuOverlay.classList.remove('active');
  menuPanel.classList.remove('active');
  if (!slideoutPanel.classList.contains('active')) {
    document.body.style.overflow = '';
  }
}

// Auto-resize textarea
function autoResize() {
  const input = document.getElementById('input');
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 200) + 'px';
}
