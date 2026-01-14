// Application state - shared across modules

// Get or create user ID
let userId = getCookie('blacksky_user_id');
if (!userId) {
  userId = generateUUID();
  setCookie('blacksky_user_id', userId, 30); // 30 day expiry
}

// Chat state
let isLoading = false;
let hasMessages = true;
let conversationMessages = [];
let currentConversationId = null;
let lastActivityTime = Date.now();
let followUpTimer = null;

// User verification state
let pendingMatches = null;
let awaitingVerification = false;

// User identity state
let currentUserName = null;
let currentUserEmail = null;
let currentUserPhone = null;
let currentUserCompany = null;
let currentAuthMethod = 'soft';  // 'soft' (anonymous/soft) or 'hard' (registered)

// Hard login state
let isMediumRegisterMode = true;

// Dashboard state
let dashboardData = null;
let isEditingProfile = false;
