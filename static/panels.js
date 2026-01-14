// Panel data management
let panelsData = {};

// Load panels from JSON file
async function loadPanels() {
  try {
    const response = await fetch('/static/panels.json');
    panelsData = await response.json();
    console.log('Panels loaded:', Object.keys(panelsData).length);
  } catch (err) {
    console.error('Failed to load panels:', err);
  }
}

// Convert JSON panel to HTML
function renderPanelContent(panel) {
  let html = '';
  
  if (panel.image) {
    html += `<img src="${panel.image}" alt="${panel.title}" class="slideout-image" onerror="this.style.display='none'">`;
  }
  
  for (const section of panel.content) {
    html += `<div class="section-title">› ${section.section}</div>`;
    for (const text of section.text) {
      html += `<p>${text.replace(/\n/g, '<br>')}</p>`;
    }
  }
  
  return html;
}

// Get panel by key (returns object with title and content)
function getPanel(key) {
  const panel = panelsData[key];
  if (!panel) return null;
  return {
    title: panel.title,
    content: renderPanelContent(panel)
  };
}

// For backwards compatibility
function getPanels() {
  const result = {};
  for (const key of Object.keys(panelsData)) {
    result[key] = getPanel(key);
  }
  return result;
}

// Load panels on script load
loadPanels();
