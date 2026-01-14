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
function openPanel(panelData) {
  slideoutTitle.textContent = panelData.title;
  slideoutContent.innerHTML = panelData.content;
  slideoutOverlay.classList.add('active');
  slideoutPanel.classList.add('active');
  document.body.style.overflow = 'hidden';
}

function closePanel() {
  slideoutOverlay.classList.remove('active');
  slideoutPanel.classList.remove('active');
  document.body.style.overflow = '';
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
