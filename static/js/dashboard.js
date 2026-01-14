// Dashboard functions - user profile panel

function buildDashboardContent(data) {
  const profile = data.profile;
  const activity = data.activity;
  const conversations = data.conversations || [];
  const interests = data.interests || [];

  // Avatar
  let avatarHtml;
  if (profile.google_picture) {
    avatarHtml = `<div class="dashboard-avatar google-auth"><img src="${profile.google_picture}" alt="Profile"></div>`;
  } else if (profile.name) {
    avatarHtml = `<div class="dashboard-avatar">${profile.name.charAt(0).toUpperCase()}</div>`;
  } else {
    avatarHtml = `<div class="dashboard-avatar">?</div>`;
  }

  // Name with verified badge
  let nameHtml = profile.name || 'Anonymous';
  if (profile.auth_method === 'google') {
    nameHtml += '<span class="verified-badge">✓</span>';
  }

  // Profile details
  let detailsHtml = '';
  if (profile.email) detailsHtml += `<div class="dashboard-detail">${profile.email}</div>`;
  if (profile.company) detailsHtml += `<div class="dashboard-detail">${profile.company}</div>`;
  if (profile.phone) detailsHtml += `<div class="dashboard-detail">${profile.phone}</div>`;

  // Activity stats
  const memberSince = formatDashboardDate(activity.member_since);
  const lastActive = formatRelativeTime(activity.last_active);

  // Conversation history
  let conversationsHtml = '';
  if (conversations.length === 0) {
    conversationsHtml = '<div class="dashboard-empty">No conversations yet</div>';
  } else {
    conversations.slice(0, 10).forEach(conv => {
      const date = formatDashboardDate(conv.date);
      const summary = conv.summary || 'No summary';
      conversationsHtml += `
        <div class="dashboard-conversation">
          <div class="dashboard-conversation-date">${date}</div>
          <div class="dashboard-conversation-summary">${summary}</div>
        </div>
      `;
    });
  }

  // Interests
  let interestsHtml = '';
  if (interests.length === 0) {
    interestsHtml = '<div class="dashboard-empty">No interests tracked yet</div>';
  } else {
    interests.forEach(interest => {
      interestsHtml += `<span class="dashboard-interest-tag">${interest}</span>`;
    });
  }

  return `
    <div class="dashboard-profile">
      ${avatarHtml}
      <div class="dashboard-info">
        <div class="dashboard-name">${nameHtml}</div>
        ${detailsHtml || '<div class="dashboard-detail" style="color:#555">No details yet</div>'}
        <button class="dashboard-edit-btn" onclick="showEditProfile()">Edit Profile</button>
      </div>
    </div>

    <div class="dashboard-stats">
      <div class="dashboard-stat">
        <div class="dashboard-stat-value">${activity.conversation_count}</div>
        <div class="dashboard-stat-label">Conversations</div>
      </div>
      <div class="dashboard-stat">
        <div class="dashboard-stat-value">${memberSince}</div>
        <div class="dashboard-stat-label">Joined</div>
      </div>
      <div class="dashboard-stat">
        <div class="dashboard-stat-value">${lastActive}</div>
        <div class="dashboard-stat-label">Last Active</div>
      </div>
    </div>

    <div class="dashboard-section-title">Conversation History</div>
    ${conversationsHtml}

    <div class="dashboard-section-title">Interests</div>
    <div class="dashboard-interests">
      ${interestsHtml}
    </div>
  `;
}

// Build edit form HTML
function buildEditFormContent(data) {
  const profile = data.profile;
  return `
    <div class="dashboard-edit-form">
      <div class="dashboard-form-group">
        <label>Name</label>
        <input type="text" id="editName" value="${profile.name || ''}" placeholder="Your name">
      </div>
      <div class="dashboard-form-group">
        <label>Email</label>
        <input type="email" id="editEmail" value="${profile.email || ''}" placeholder="your@email.com">
      </div>
      <div class="dashboard-form-group">
        <label>Phone</label>
        <input type="tel" id="editPhone" value="${profile.phone || ''}" placeholder="(555) 123-4567">
      </div>
      <div class="dashboard-form-group">
        <label>Company</label>
        <input type="text" id="editCompany" value="${profile.company || ''}" placeholder="Your company">
      </div>
      <div class="dashboard-form-actions">
        <button class="dashboard-btn-cancel" onclick="cancelEditProfile()">Cancel</button>
        <button class="dashboard-btn-save" onclick="saveProfileChanges()">Save Changes</button>
      </div>
    </div>
  `;
}

// Show edit profile form
window.showEditProfile = function() {
  if (dashboardData) {
    isEditingProfile = true;
    slideoutTitle.textContent = 'Edit Profile';
    slideoutContent.innerHTML = buildEditFormContent(dashboardData);
  }
};

// Cancel edit profile
window.cancelEditProfile = function() {
  if (dashboardData) {
    isEditingProfile = false;
    slideoutTitle.textContent = 'My Dashboard';
    slideoutContent.innerHTML = buildDashboardContent(dashboardData);
  }
};

// Save profile changes
window.saveProfileChanges = async function() {
  const name = document.getElementById('editName').value.trim();
  const email = document.getElementById('editEmail').value.trim();
  const phone = document.getElementById('editPhone').value.trim();
  const company = document.getElementById('editCompany').value.trim();

  try {
    const res = await fetch(`${API_HOST}/user/update`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        name: name || null,
        email: email || null,
        phone: phone || null,
        company: company || null
      })
    });

    if (res.ok) {
      currentUserName = name || null;
      updateAvatarUI();
      dashboardData = await fetchDashboardData();
      if (dashboardData) {
        isEditingProfile = false;
        slideoutTitle.textContent = 'My Dashboard';
        slideoutContent.innerHTML = buildDashboardContent(dashboardData);
      }
    } else {
      alert('Failed to save changes');
    }
  } catch (e) {
    console.error('Error saving profile:', e);
    alert('Error saving changes');
  }
};

// Fetch dashboard data
async function fetchDashboardData() {
  try {
    const res = await fetch(`${API_HOST}/user/${userId}/dashboard`);
    if (res.ok) return await res.json();
  } catch (e) {
    console.error('Dashboard fetch error:', e);
  }
  return null;
}

async function openDashboard() {
  // Show loading state
  openPanel({
    title: 'My Dashboard',
    content: '<div style="color:#666; text-align:center; padding:40px;">Loading...</div>'
  });

  // Fetch and store dashboard data
  dashboardData = await fetchDashboardData();
  if (dashboardData) {
    slideoutContent.innerHTML = buildDashboardContent(dashboardData);
  } else {
    slideoutContent.innerHTML = '<div style="color:#666; text-align:center; padding:40px;">Could not load dashboard</div>';
  }
}
