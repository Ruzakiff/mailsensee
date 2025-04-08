// MailSense background script - handles authentication and background tasks

// API base URL
const API_URL = 'http://localhost:5000/api';

// Global tracking of auth check intervals
const authCheckIntervalIds = {};

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

// Start authentication process
async function startAuthProcess(userId) {
  try {
    log('Starting auth process for', userId);
    
    // Call authenticate endpoint to get auth URL
    const response = await fetch(`${API_URL}/authenticate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId })
    });
    
    const data = await response.json();
    
    if (!data.success || !data.auth_url) {
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
          });
        });
        
        // Clear the interval
        clearInterval(authCheckIntervalIds[userId]);
        delete authCheckIntervalIds[userId];
      }
    }, 3000);
    
    // Stop checking after 2 minutes
    setTimeout(() => {
      if (authCheckIntervalIds[userId]) {
        clearInterval(authCheckIntervalIds[userId]);
        delete authCheckIntervalIds[userId];
      }
    }, 120000);
    
    // Open the auth URL in a new tab
    chrome.tabs.create({ url: data.auth_url });
    
    return { authUrl: data.auth_url };
  } catch (error) {
    log('Auth process error:', error);
    return { error: error.message };
  }
}

// Listen for OAuth redirect
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url && tab.url.includes('auth-callback')) {
    log('Detected auth callback URL', tab.url);
    
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
          
          // Display success message
          chrome.scripting.executeScript({
            target: { tabId: tabId },
            function: showAuthSuccess
          });
        });
      } else {
        log('Authentication failed');
        // Show failure message
        chrome.scripting.executeScript({
          target: { tabId: tabId },
          function: showAuthFailure
        });
      }
    });
  }
});

// Auth success page
function showAuthSuccess() {
  document.body.innerHTML = `
    <div style="text-align: center; font-family: Arial; padding: 50px; background: #f9f9f9;">
      <div style="background: white; max-width: 500px; margin: 0 auto; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
        <h1 style="color: #4285f4;">Authentication Successful</h1>
        <p style="font-size: 16px; color: #555;">You may now close this tab and return to the MailSense extension.</p>
        <button onclick="window.close()" style="background: #4285f4; color: white; border: none; padding: 10px 20px; margin-top: 20px; border-radius: 4px; cursor: pointer;">Close Tab</button>
      </div>
    </div>
  `;
}

// Auth failure page
function showAuthFailure() {
  document.body.innerHTML = `
    <div style="text-align: center; font-family: Arial; padding: 50px; background: #f9f9f9;">
      <div style="background: white; max-width: 500px; margin: 0 auto; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
        <h1 style="color: #d32f2f;">Authentication Failed</h1>
        <p style="font-size: 16px; color: #555;">There was a problem authenticating with Google. Please try again.</p>
        <button onclick="window.close()" style="background: #4285f4; color: white; border: none; padding: 10px 20px; margin-top: 20px; border-radius: 4px; cursor: pointer;">Close Tab</button>
      </div>
    </div>
  `;
}

// Handle messages from content/popup scripts
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  log('Received message', request);
  
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
        setupComplete: userState.setupComplete || false
      });
    });
    return true; // Keep channel open for async response
  }
}); 