// MailSense background script - Redesigned for intuitive experience

// API base URL
const API_URL = 'http://localhost:5000/api';

// Global tracking of auth check intervals
const authCheckIntervalIds = {};

// Extension state management
let extensionState = {
  authInProgress: false,
  lastAuthTab: null,
  authStartTime: null
};

// Log for extension events
function log(message, data = null) {
  console.log(`MailSense BG: ${message}`, data || '');
}

// Check API auth status
async function checkAuthStatus(userId) {
  try {
    const url = `${API_URL}/auth-status?user_id=${userId}`;
    const response = await fetch(url);
    const data = await response.json();
    return data;
  } catch (error) {
    log('Auth check error:', error);
    return { authenticated: false };
  }
}

// Initialize on install
chrome.runtime.onInstalled.addListener(() => {
  log('Extension installed or updated');
  
  // Initialize state if needed
  chrome.storage.local.get('userState', (result) => {
    if (!result.userState) {
      const userState = {
        userId: 'user_' + Date.now(),
        authenticated: false,
        emailsFetched: false,
        voiceAnalyzed: false,
        setupComplete: false
      };
      
      chrome.storage.local.set({ userState });
      log('Initial state created', userState);
    }
  });
});

// Notify all extension views of state change
function notifyStateChange(state) {
  chrome.runtime.sendMessage({ 
    action: 'stateChanged', 
    state: state 
  });
}

// Start authentication process
async function startAuthProcess(userId) {
  try {
    // Prevent multiple auth attempts
    if (extensionState.authInProgress) {
      log('Auth already in progress, focusing existing tab');
      if (extensionState.lastAuthTab) {
        chrome.tabs.update(extensionState.lastAuthTab, { active: true });
        return { status: 'in_progress', message: 'Authentication already in progress' };
      }
    }
    
    log('Starting auth process for', userId);
    extensionState.authInProgress = true;
    extensionState.authStartTime = Date.now();
    
    // Notify views that auth has started
    notifyStateChange({ authInProgress: true });
    
    // Call authenticate endpoint to get auth URL
    const response = await fetch(`${API_URL}/authenticate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId })
    });
    
    const data = await response.json();
    
    if (!data.success || !data.auth_url) {
      extensionState.authInProgress = false;
      notifyStateChange({ authInProgress: false, error: 'Failed to get authentication URL' });
      log('Failed to get auth URL');
      return { error: 'Failed to get authentication URL' };
    }
    
    // If there's already an interval for this user, clear it
    if (authCheckIntervalIds[userId]) {
      clearInterval(authCheckIntervalIds[userId]);
    }
    
    // Set up interval to check auth status
    authCheckIntervalIds[userId] = setInterval(async () => {
      const status = await checkAuthStatus(userId);
      
      if (status.authenticated) {
        log('User authenticated:', userId);
        
        // Update user state
        chrome.storage.local.get('userState', (result) => {
          const userState = result.userState || {};
          userState.authenticated = true;
          
          chrome.storage.local.set({ userState }, () => {
            log('Updated auth state for user');
            
            // Reset extension state
            extensionState.authInProgress = false;
            
            // Notify all extension views that auth is complete
            notifyStateChange({ 
              authInProgress: false, 
              authenticated: true,
              completedAt: Date.now()
            });
          });
        });
        
        // Clear the interval
        clearInterval(authCheckIntervalIds[userId]);
        delete authCheckIntervalIds[userId];
      }
    }, 2000); // Check every 2 seconds
    
    // Stop checking after 2 minutes
    setTimeout(() => {
      if (authCheckIntervalIds[userId]) {
        clearInterval(authCheckIntervalIds[userId]);
        delete authCheckIntervalIds[userId];
        
        if (extensionState.authInProgress) {
          extensionState.authInProgress = false;
          notifyStateChange({ 
            authInProgress: false, 
            error: 'Authentication timed out after 2 minutes' 
          });
        }
      }
    }, 120000); // 2 minute timeout
    
    // Open the auth URL in a new tab
    chrome.tabs.create({ url: data.auth_url }, (tab) => {
      extensionState.lastAuthTab = tab.id;
    });
    
    return { 
      status: 'started',
      authUrl: data.auth_url 
    };
  } catch (error) {
    extensionState.authInProgress = false;
    notifyStateChange({ authInProgress: false, error: error.message });
    log('Auth process error:', error);
    return { error: error.message };
  }
}

// Listen for OAuth redirect
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url && tab.url.includes('auth-callback')) {
    log('Detected auth callback URL', tab.url);
    
    // Track that this is the auth tab
    if (extensionState.authInProgress) {
      extensionState.lastAuthTab = tabId;
    }
    
    // Get userId from storage
    chrome.storage.local.get('userState', (result) => {
      const userState = result.userState || {};
      
      if (!userState.userId) {
        log('No userId found in storage');
        return;
      }
      
      // Parse URL to get auth result
      const url = new URL(tab.url);
      const authSuccess = url.searchParams.get('success') === 'true';
      
      if (authSuccess) {
        // Update user state
        userState.authenticated = true;
        chrome.storage.local.set({ userState }, () => {
          log('Authentication successful, state updated', userState);
          
          // Reset extension state
          extensionState.authInProgress = false;
          
          // Notify all extension views that auth is complete
          notifyStateChange({ 
            authInProgress: false, 
            authenticated: true,
            completedAt: Date.now()
          });
          
          // Display success message with auto-close
          chrome.scripting.executeScript({
            target: { tabId: tabId },
            function: showAuthSuccess
          });
          
          // Automatically open popup after success
          setTimeout(() => {
            chrome.action.openPopup();
          }, 1500);
        });
      } else {
        log('Authentication failed');
        
        // Reset extension state
        extensionState.authInProgress = false;
        
        // Notify all extension views that auth failed
        notifyStateChange({ 
          authInProgress: false, 
          error: 'Authentication failed'
        });
        
        // Show failure message
        chrome.scripting.executeScript({
          target: { tabId: tabId },
          function: showAuthFailure
        });
      }
    });
  }
});

// Automatically close tab when it's no longer needed
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (extensionState.lastAuthTab === tabId && 
      changeInfo.status === 'complete' && 
      tab.url && tab.url.includes('auth-callback')) {
    
    // Auto-close the tab after 5 seconds if auth succeeded
    const url = new URL(tab.url);
    const authSuccess = url.searchParams.get('success') === 'true';
    
    if (authSuccess) {
      setTimeout(() => {
        chrome.tabs.remove(tabId);
      }, 5000);
    }
  }
});

// Auth success page with auto-close countdown
function showAuthSuccess() {
  document.head.innerHTML = `
    <style>
      body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 0; padding: 0; background: #f9f9f9; }
      .container { max-width: 500px; margin: 50px auto; background: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); padding: 30px; text-align: center; }
      h1 { color: #4285f4; margin-top: 0; }
      p { color: #555; font-size: 16px; line-height: 1.5; }
      button { background: #4285f4; color: white; border: none; padding: 10px 20px; border-radius: 4px; font-weight: 500; cursor: pointer; }
      button:hover { background: #3367d6; }
      .countdown { font-weight: bold; color: #4285f4; }
      @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
      .container { animation: fadeIn 0.5s; }
    </style>
  `;
  
  document.body.innerHTML = `
    <div class="container">
      <svg width="60" height="60" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 2C6.48 2 2 6.48 2 12C2 17.52 6.48 22 12 22C17.52 22 22 17.52 22 12C22 6.48 17.52 2 12 2ZM10 17L5 12L6.41 10.59L10 14.17L17.59 6.58L19 8L10 17Z" fill="#4285f4"/>
      </svg>
      <h1>Authentication Successful</h1>
      <p>The MailSense extension is now authorized to access your Gmail data.</p>
      <p>This tab will automatically close in <span id="countdown" class="countdown">5</span> seconds.</p>
      <button onclick="window.close()">Close Now</button>
    </div>
    <script>
      let count = 5;
      const countdownElement = document.getElementById('countdown');
      const interval = setInterval(() => {
        count--;
        countdownElement.textContent = count;
        if (count <= 0) {
          clearInterval(interval);
          window.close();
        }
      }, 1000);
    </script>
  `;
}

// Auth failure page
function showAuthFailure() {
  document.head.innerHTML = `
    <style>
      body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 0; padding: 0; background: #f9f9f9; }
      .container { max-width: 500px; margin: 50px auto; background: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); padding: 30px; text-align: center; }
      h1 { color: #d32f2f; margin-top: 0; }
      p { color: #555; font-size: 16px; line-height: 1.5; }
      button { background: #4285f4; color: white; border: none; padding: 10px 20px; border-radius: 4px; font-weight: 500; cursor: pointer; }
      button:hover { background: #3367d6; }
      @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
      .container { animation: fadeIn 0.5s; }
    </style>
  `;
  
  document.body.innerHTML = `
    <div class="container">
      <svg width="60" height="60" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 2C6.48 2 2 6.48 2 12C2 17.52 6.48 22 12 22C17.52 22 22 17.52 22 12C22 6.48 17.52 2 12 2ZM13 17H11V15H13V17ZM13 13H11V7H13V13Z" fill="#d32f2f"/>
      </svg>
      <h1>Authentication Failed</h1>
      <p>There was a problem authenticating with Google. Please try again.</p>
      <button onclick="window.close()">Close</button>
      <button onclick="location.href='chrome-extension://' + chrome.runtime.id + '/popup.html'" style="margin-left: 10px; background: #34a853;">Try Again</button>
    </div>
  `;
}

// Handle messages from content/popup scripts
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  log('Received message', request);
  
  // Get current auth state
  if (request.action === 'getAuthState') {
    sendResponse({
      authInProgress: extensionState.authInProgress,
      lastAuthTab: extensionState.lastAuthTab,
      authStartTime: extensionState.authStartTime
    });
    return true;
  }
  
  // Start auth process
  if (request.action === 'startAuth' && request.userId) {
    log('Starting auth process for', request.userId);
    
    startAuthProcess(request.userId)
      .then(response => {
        sendResponse(response);
      })
      .catch(error => {
        sendResponse({ error: error.message });
      });
    
    return true; // Keep channel open for async response
  }
  
  // Check auth status
  if (request.action === 'checkAuth') {
    chrome.storage.local.get('userState', (result) => {
      const userState = result.userState || {};
      sendResponse({ 
        authenticated: userState.authenticated || false,
        setupComplete: userState.setupComplete || false,
        authInProgress: extensionState.authInProgress
      });
    });
    return true; // Keep channel open for async response
  }
}); 