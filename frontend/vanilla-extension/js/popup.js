// MailSense popup.js - Using actual API calls with improved auth flow

// Constants
const API_URL = 'http://localhost:5000/api';

// Current state - default userId so we never have null
let userState = {
  userId: 'user_' + Date.now(), // Initialize with a default
  authenticated: false,
  emailsFetched: false,
  voiceAnalyzed: false,
  setupComplete: false,
  lastError: null
};

// Debug logging
function log(message, data = null) {
  console.log(`MailSense: ${message}`, data || '');
  
  // Update debug panel if available
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

// Reset state to defaults
async function resetState() {
  try {
    userState = {
      userId: 'user_' + Date.now(),
      authenticated: false,
      emailsFetched: false,
      voiceAnalyzed: false,
      setupComplete: false,
      lastError: null
    };
    
    await saveState();
    log('State reset', userState);
    
    // Reload the UI
    updateUI();
    
    // Show confirmation
    showMessage('State has been reset');
  } catch (error) {
    console.error('Failed to reset state:', error);
    showError('Failed to reset state: ' + error.message);
  }
}

// ==== UI MANAGEMENT ====

// Updates the entire UI based on current state
function updateUI() {
  log('Updating UI with state', userState);
  
  // Update auth section
  updateAuthSection();
  
  // Update progress indicators
  updateProgressIndicators();
  
  // Show/hide sections based on progress
  updateSectionVisibility();
  
  // Update button states
  updateButtonStates();
  
  // Show any errors
  if (userState.lastError) {
    showError(userState.lastError);
  }
}

// Update authentication section
function updateAuthSection() {
  const authStatus = document.getElementById('auth-status');
  const authButton = document.getElementById('auth-button');
  
  if (userState.authenticated) {
    authStatus.textContent = '✅ Authenticated with Google';
    authButton.textContent = 'Re-authenticate';
  } else {
    authStatus.textContent = 'Authentication required';
    authButton.textContent = 'Sign in with Google';
  }
  
  // Always enable the auth button
  authButton.disabled = false;
}

// Update progress indicators
function updateProgressIndicators() {
  const indicators = {
    'auth-indicator': userState.authenticated,
    'history-indicator': userState.emailsFetched,
    'voice-indicator': userState.voiceAnalyzed
  };
  
  for (const [id, completed] of Object.entries(indicators)) {
    const indicator = document.getElementById(id);
    if (indicator) {
      indicator.textContent = completed ? 'Complete' : 'Pending';
      indicator.className = 'status-value ' + (completed ? 'status-success' : 'status-pending');
    }
  }
}

// Update section visibility
function updateSectionVisibility() {
  const sections = {
    'status-section': userState.authenticated,
    'actions-section': userState.authenticated && !userState.setupComplete,
    'complete-section': userState.setupComplete
  };
  
  for (const [id, visible] of Object.entries(sections)) {
    const section = document.getElementById(id);
    if (section) {
      section.classList.toggle('hidden', !visible);
    }
  }
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

// Handle authentication - IMPROVED VERSION
async function handleAuthenticate() {
  try {
    setButtonLoading('auth-button', true, 'Starting auth...');
    
    // Tell background script to start auth and monitor process
    chrome.runtime.sendMessage(
      { action: 'startAuth', userId: userState.userId },
      async (response) => {
        if (!response || !response.authUrl) {
          showError('Failed to start authentication process');
          setButtonLoading('auth-button', false);
          return;
        }
        
        // Open auth URL in a new tab
        chrome.tabs.create({ url: response.authUrl });
        
        // Set up a listener for auth completion
        const onStorageChanged = (changes, area) => {
          if (area === 'local' && changes.userState) {
            const newState = changes.userState.newValue;
            
            // Update our state if authentication completed
            if (newState && newState.authenticated) {
              userState = newState;
              updateUI();
              
              // Remove listener once authenticated
              chrome.storage.onChanged.removeListener(onStorageChanged);
            }
          }
        };
        
        // Add listener for storage changes
        chrome.storage.onChanged.addListener(onStorageChanged);
        
        setButtonLoading('auth-button', false);
      }
    );
  } catch (error) {
    showError(`Authentication failed: ${error.message}`);
    setButtonLoading('auth-button', false);
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
}

// Initialize the extension
async function initialize() {
  log('Initializing extension');
  
  try {
    // Load saved state
    await loadState();
    
    // Check if we need to refresh auth status
    if (!userState.authenticated) {
      // Check with the background script if auth has completed
      chrome.runtime.sendMessage({ action: 'checkAuth' }, (response) => {
        if (response && response.authenticated) {
          userState.authenticated = true;
          saveState().then(() => updateUI());
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