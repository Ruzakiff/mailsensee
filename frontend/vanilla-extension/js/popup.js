// MailSense popup.js - Redesigned for intuitive experience

// Constants
const API_URL = 'http://localhost:5000/api';

// Current state with default userId
let userState = {
  userId: 'user_' + Date.now(),
  authenticated: false,
  emailsFetched: false,
  voiceAnalyzed: false,
  setupComplete: false,
  lastError: null
};

// Track authentication status
let authStatus = {
  inProgress: false,
  startTime: null,
  timeElapsed: 0
};

// Debug logging
function log(message, data = null) {
  console.log(`MailSense: ${message}`, data || '');
  updateDebugInfo(message, data);
}

// Update debug panel
function updateDebugInfo(message, data = null) {
  const debugInfo = document.getElementById('debug-info');
  if (debugInfo) {
    const timestamp = new Date().toLocaleTimeString();
    const logMessage = `[${timestamp}] ${message}`;
    const existingContent = debugInfo.textContent === 'Loading...' ? '' : debugInfo.textContent + '\n';
    debugInfo.textContent = existingContent + logMessage + (data ? ': ' + JSON.stringify(data) : '');
    
    // Auto-scroll to bottom
    debugInfo.scrollTop = debugInfo.scrollHeight;
  }
}

// ==== STATE MANAGEMENT ====

// Save state to Chrome storage
async function saveState() {
  return new Promise((resolve, reject) => {
    try {
      log('Saving state', userState);
      chrome.storage.local.set({ userState }, () => {
        if (chrome.runtime.lastError) {
          reject(chrome.runtime.lastError);
        } else {
          resolve();
        }
      });
    } catch (error) {
      reject(error);
    }
  });
}

// Load state from Chrome storage
async function loadState() {
  return new Promise((resolve, reject) => {
    try {
      chrome.storage.local.get('userState', (result) => {
        if (chrome.runtime.lastError) {
          reject(chrome.runtime.lastError);
        } else {
          if (result.userState) {
            // Make sure we never have a null userId
            if (!result.userState.userId) {
              result.userState.userId = 'user_' + Date.now();
            }
            userState = result.userState;
            log('State loaded', userState);
          } else {
            // Initialize with a userId if none exists
            userState.userId = 'user_' + Date.now();
            saveState();
            log('New state initialized', userState);
          }
          resolve();
        }
      });
    } catch (error) {
      reject(error);
    }
  });
}

// Check if authentication is in progress
async function checkAuthProgress() {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ action: 'getAuthState' }, (response) => {
      if (response) {
        authStatus.inProgress = response.authInProgress;
        authStatus.startTime = response.authStartTime;
        
        if (authStatus.inProgress && authStatus.startTime) {
          authStatus.timeElapsed = Math.floor((Date.now() - authStatus.startTime) / 1000);
        }
        
        log('Auth progress check', authStatus);
        resolve(authStatus.inProgress);
      } else {
        resolve(false);
      }
    });
  });
}

// ==== UI MANAGEMENT ====

// Updates the entire UI based on current state
function updateUI() {
  log('Updating UI with state', userState);
  
  // Check if auth is in progress
  checkAuthProgress().then(inProgress => {
    if (inProgress) {
      showAuthInProgress();
    } else {
      // Update auth section
      updateAuthSection();
      
      // Update progress indicators
      updateProgressIndicator();
      
      // Show/hide sections based on progress
      updateSectionVisibility();
      
      // Update button states
      updateButtonStates();
    }
    
    // Show any errors
    if (userState.lastError) {
      showError(userState.lastError);
    }
  });
}

// Show auth in progress UI
function showAuthInProgress() {
  const authStatus = document.getElementById('auth-status');
  const authButton = document.getElementById('auth-button');
  
  // Update status text with animated dots
  authStatus.innerHTML = `
    <div class="auth-progress">
      <span>Authentication in progress</span>
      <span class="loading-dots"><span>.</span><span>.</span><span>.</span></span>
    </div>
    <div class="auth-time">Please complete the Google auth in the opened tab</div>
  `;
  
  // Add pulse animation to status
  authStatus.classList.add('pulsing');
  
  // Change button to cancel button
  authButton.textContent = 'Cancel Authentication';
  authButton.classList.add('cancel-auth');
  authButton.disabled = false;
}

// Update authentication section
function updateAuthSection() {
  const authStatus = document.getElementById('auth-status');
  const authButton = document.getElementById('auth-button');
  
  // Remove any previously added classes
  authStatus.classList.remove('pulsing');
  authButton.classList.remove('cancel-auth');
  
  if (userState.authenticated) {
    authStatus.innerHTML = '✅ <span>Authenticated with Google</span>';
    authButton.textContent = 'Re-authenticate';
  } else {
    authStatus.innerHTML = 'Authentication required';
    authButton.textContent = 'Sign in with Google';
  }
  
  // Always enable the auth button
  authButton.disabled = false;
}

// Update progress indicator
function updateProgressIndicator() {
  // Reset all steps
  document.querySelectorAll('.progress-step').forEach(step => {
    step.classList.remove('active', 'completed');
  });
  
  // Mark steps as active or completed
  if (!userState.authenticated) {
    document.querySelector('.progress-step[data-step="auth"]').classList.add('active');
  } else {
    document.querySelector('.progress-step[data-step="auth"]').classList.add('completed');
    
    if (!userState.emailsFetched) {
      document.querySelector('.progress-step[data-step="emails"]').classList.add('active');
    } else {
      document.querySelector('.progress-step[data-step="emails"]').classList.add('completed');
      
      if (!userState.voiceAnalyzed) {
        document.querySelector('.progress-step[data-step="voice"]').classList.add('active');
      } else {
        document.querySelector('.progress-step[data-step="voice"]').classList.add('completed');
        document.querySelector('.progress-step[data-step="complete"]').classList.add('active');
      }
    }
  }
}

// Update section visibility based on current state
function updateSectionVisibility() {
  // Get all sections
  const sections = [
    'auth-section',
    'status-section',
    'actions-section',
    'complete-section'
  ];
  
  // First hide all sections
  sections.forEach(id => {
    const section = document.getElementById(id);
    if (section) section.classList.add('hidden');
  });
  
  // Show only the most relevant section based on current state
  if (!userState.authenticated) {
    // Not authenticated - show auth section only
    document.getElementById('auth-section')?.classList.remove('hidden');
  } 
  else if (userState.authenticated && !userState.emailsFetched) {
    // Authenticated but no email history - show actions section
    document.getElementById('actions-section')?.classList.remove('hidden');
    
    // We can show status as an additional context, but it's optional
    // document.getElementById('status-section')?.classList.remove('hidden');
  }
  else if (userState.authenticated && userState.emailsFetched && !userState.voiceAnalyzed) {
    // Email history fetched but voice not analyzed - show actions section
    document.getElementById('actions-section')?.classList.remove('hidden');
  }
  else if (userState.authenticated && userState.emailsFetched && userState.voiceAnalyzed) {
    // Everything is set up - show complete section
    document.getElementById('complete-section')?.classList.remove('hidden');
  }
  
  // Animate the visible section
  sections.forEach(id => {
    const section = document.getElementById(id);
    if (section && !section.classList.contains('hidden')) {
      section.classList.add('section-fade-in');
      setTimeout(() => section.classList.remove('section-fade-in'), 500);
    }
  });
}

// Update button states
function updateButtonStates() {
  const buttonStates = {
    'fetch-history-button': userState.authenticated,
    'analyze-voice-button': userState.emailsFetched,
    'setup-complete-button': userState.voiceAnalyzed
  };
  
  for (const [id, enabled] of Object.entries(buttonStates)) {
    const button = document.getElementById(id);
    if (button) {
      button.disabled = !enabled;
    }
  }
}

// Show error message
function showError(message) {
  const errorBanner = document.createElement('div');
  errorBanner.className = 'error-banner';
  errorBanner.textContent = message;
  
  // Add close button
  const closeBtn = document.createElement('span');
  closeBtn.textContent = '×';
  closeBtn.className = 'close-btn';
  closeBtn.onclick = () => errorBanner.remove();
  errorBanner.appendChild(closeBtn);
  
  // Add to dom
  document.querySelector('.mailsense-popup').prepend(errorBanner);
  
  // Auto-remove after 8 seconds
  setTimeout(() => errorBanner.remove(), 8000);
}

// Show loading state for a button
function setButtonLoading(buttonId, isLoading, text = null) {
  const button = document.getElementById(buttonId);
  if (!button) return;
  
  if (isLoading) {
    button.disabled = true;
    button.dataset.originalText = button.textContent;
    button.textContent = text || 'Loading...';
  } else {
    button.disabled = false;
    button.textContent = button.dataset.originalText || text;
  }
}

// ==== API OPERATIONS ====

// Call the API with proper error handling
async function callApi(endpoint, payload, buttonId = null) {
  if (buttonId) {
    setButtonLoading(buttonId, true);
  }
  
  try {
    log(`Calling API: ${endpoint}`, payload);
    
    // Make the actual API call
    const response = await fetch(`${API_URL}/${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    
    // Parse response
    const data = await response.json();
    
    if (!data.success) {
      throw new Error(data.message || `Failed to call ${endpoint}`);
    }
    
    return data;
  } catch (error) {
    log(`API Error (${endpoint}):`, error);
    
    // Update state with error
    userState.lastError = error.message;
    await saveState();
    
    // Re-throw for the caller
    throw error;
  } finally {
    if (buttonId) {
      setButtonLoading(buttonId, false);
    }
  }
}

// ==== CORE FUNCTIONALITY ====

// ==== ACTION HANDLERS ====

// Handle authentication button click
async function handleAuthenticate() {
  try {
    // If auth is in progress and user clicks button, try to focus the auth tab
    if (authStatus.inProgress) {
      log('Attempting to cancel ongoing authentication');
      // Signal background to cancel auth
      chrome.runtime.sendMessage({ action: 'cancelAuth' });
      
      // Reset local auth status
      authStatus.inProgress = false;
      updateUI();
      return;
    }
    
    // Normal auth flow
    log('Starting authentication for user', userState.userId);
    
    // Clear any previous errors
    userState.lastError = null;
    
    // Update UI to show auth in progress
    authStatus.inProgress = true;
    showAuthInProgress();
    
    // Start authentication process via background script
    chrome.runtime.sendMessage(
      { action: 'startAuth', userId: userState.userId },
      (response) => {
        if (chrome.runtime.lastError) {
          log('Error starting auth:', chrome.runtime.lastError);
          userState.lastError = chrome.runtime.lastError.message;
          authStatus.inProgress = false;
          updateUI();
          return;
        }
        
        if (response.error) {
          log('Auth error:', response.error);
          userState.lastError = response.error;
          authStatus.inProgress = false;
          updateUI();
        } else {
          log('Auth started', response);
          
          // Auth is now handled by background script
          // UI updates will come from state change events
        }
      }
    );
  } catch (error) {
    log('Auth error:', error);
    userState.lastError = error.message;
    authStatus.inProgress = false;
    updateUI();
  }
}

// Handle fetching email history
async function handleFetchHistory() {
  try {
    const afterDate = document.getElementById('after-date').value;
    const beforeDate = document.getElementById('before-date').value;
    const emailLimit = document.getElementById('email-limit').value;
    
    const result = await callApi('fetch-history', {
      user_id: userState.userId,
      after_date: afterDate,
      before_date: beforeDate,
      email_limit: parseInt(emailLimit)
    }, 'fetch-history-button');
    
    userState.emailsFetched = true;
    userState.lastError = null;
    await saveState();
    
    updateUI();
  } catch (error) {
    showError(`Failed to fetch emails: ${error.message}`);
    updateUI();
  }
}

// Handle voice analysis
async function handleAnalyzeVoice() {
  try {
    const result = await callApi('analyze-voice', {
      user_id: userState.userId
    }, 'analyze-voice-button');
    
    userState.voiceAnalyzed = true;
    userState.lastError = null;
    await saveState();
    
    updateUI();
  } catch (error) {
    showError(`Voice analysis failed: ${error.message}`);
    updateUI();
  }
}

// Handle setup completion
async function handleCompleteSetup() {
  try {
    userState.setupComplete = true;
    userState.lastError = null;
    await saveState();
    
    updateUI();
  } catch (error) {
    showError(`Failed to complete setup: ${error.message}`);
    updateUI();
  }
}

// Handle content generation
async function handleGenerateContent() {
  try {
    const promptInput = document.getElementById('prompt-input');
    const prompt = promptInput.value.trim();
    
    if (!prompt) {
      showError('Please enter a prompt');
      return;
    }
    
    const result = await callApi('generate-content', {
      user_id: userState.userId,
      prompt: prompt
    }, 'generate-test-button');
    
    // Show result
    const generatedText = document.getElementById('generated-text');
    generatedText.textContent = result.generated_text;
    
    document.getElementById('generation-result').classList.remove('hidden');
  } catch (error) {
    showError(`Generation failed: ${error.message}`);
  }
}

// Handle content refinement
async function handleRefineContent() {
  try {
    const generatedText = document.getElementById('generated-text');
    const refinementInput = document.getElementById('refinement-input');
    
    const originalText = generatedText.textContent;
    const refinement = refinementInput.value.trim();
    
    if (!refinement) {
      showError('Please enter refinement instructions');
      return;
    }
    
    const result = await callApi('refine-content', {
      user_id: userState.userId,
      original_text: originalText,
      refinement: refinement
    }, 'refine-button');
    
    // Update text
    generatedText.textContent = result.refined_text;
    
    // Clear refinement input
    refinementInput.value = '';
  } catch (error) {
    showError(`Refinement failed: ${error.message}`);
  }
}

// ==== INITIALIZATION ====

// Set up all event listeners
function setupEventListeners() {
  // Setup buttons
  document.getElementById('auth-button').addEventListener('click', handleAuthenticate);
  document.getElementById('fetch-history-button').addEventListener('click', handleFetchHistory);
  document.getElementById('analyze-voice-button').addEventListener('click', handleAnalyzeVoice);
  document.getElementById('setup-complete-button').addEventListener('click', handleCompleteSetup);
  
  // Generation & refinement
  document.getElementById('generate-test-button').addEventListener('click', handleGenerateContent);
  document.getElementById('refine-button').addEventListener('click', handleRefineContent);
  
  // Help & settings
  document.getElementById('help-link').addEventListener('click', () => {
    chrome.tabs.create({ url: 'https://mailsense.app/help' });
  });
  
  document.getElementById('settings-link').addEventListener('click', () => {
    if (confirm('Reset extension state?')) {
      resetState();
    }
  });
  
  // Debug reset button
  document.getElementById('debug-reset').addEventListener('click', () => {
    resetState();
  });
  
  // Listen for state changes from background script
  chrome.runtime.onMessage.addListener((message) => {
    if (message.action === 'stateChanged') {
      log('Received state change notification', message.state);
      
      // Update auth status
      if (message.state.hasOwnProperty('authInProgress')) {
        authStatus.inProgress = message.state.authInProgress;
        
        if (message.state.authenticated) {
          userState.authenticated = true;
          saveState().then(() => updateUI());
        }
        
        if (message.state.error) {
          userState.lastError = message.state.error;
        }
        
        updateUI();
      }
    }
  });
}

// Initialize the extension
async function initialize() {
  log('Initializing extension');
  
  try {
    // Add stylesheet for animations
    const style = document.createElement('style');
    style.textContent = `
      @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.5; }
        100% { opacity: 1; }
      }
      
      .pulsing {
        animation: pulse 2s infinite;
      }
      
      .auth-progress {
        display: flex;
        align-items: center;
      }
      
      .loading-dots span {
        animation: loadingDots 1.4s infinite both;
        display: inline-block;
      }
      
      .loading-dots span:nth-child(2) {
        animation-delay: 0.2s;
      }
      
      .loading-dots span:nth-child(3) {
        animation-delay: 0.4s;
      }
      
      @keyframes loadingDots {
        0% { opacity: 0; }
        50% { opacity: 1; }
        100% { opacity: 0; }
      }
      
      .auth-time {
        font-size: 12px;
        color: #666;
        margin-top: 5px;
      }
      
      .cancel-auth {
        background-color: #d32f2f !important;
      }
      
      .cancel-auth:hover {
        background-color: #b71c1c !important;
      }
    `;
    document.head.appendChild(style);
    
    // Load saved state
    await loadState();
    
    // Check if auth is in progress
    await checkAuthProgress();
    
    // Check if we need to refresh auth status
    if (!userState.authenticated) {
      // Check with the background script if auth has completed
      chrome.runtime.sendMessage({ action: 'checkAuth' }, (response) => {
        if (response && response.authenticated) {
          userState.authenticated = true;
          authStatus.inProgress = response.authInProgress || false;
          saveState().then(() => updateUI());
        } else if (response && response.authInProgress) {
          authStatus.inProgress = true;
          updateUI();
        }
      });
    }
    
    // Set up event listeners
    setupEventListeners();
    
    // Update UI with current state
    updateUI();
    
    // Set flag for initialization check
    window.mailSenseInitialized = true;
    
    log('Initialization complete');
  } catch (error) {
    console.error('Initialization failed:', error);
    showError('Failed to initialize extension');
  }
}

// Start the extension when DOM is ready
document.addEventListener('DOMContentLoaded', initialize);