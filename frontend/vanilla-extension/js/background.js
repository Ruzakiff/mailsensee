// background.js - Handles authentication, API calls, and notifications

// Configuration
const API_BASE_URL = 'http://localhost:5000/api';
const CLIENT_ID = 'YOUR_CLIENT_ID'; // From Google Cloud Console
const REDIRECT_URI = chrome.identity.getRedirectURL();
const SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.send'];

// State management
let authToken = null;
let userProfile = null;

// Initialize extension
chrome.runtime.onInstalled.addListener(async () => {
  console.log('MailSense extension installed');
  
  // Check if we have a stored token
  const storedAuth = await chrome.storage.local.get(['authToken', 'userProfile']);
  if (storedAuth.authToken) {
    authToken = storedAuth.authToken;
    userProfile = storedAuth.userProfile;
    console.log('Loaded existing authentication');
  }
  
  // Set up alarm for periodic checks (e.g., for new emails)
  chrome.alarms.create('checkMailPeriodically', { periodInMinutes: 15 });
});

// Handle authentication
async function authenticate() {
  try {
    // OAuth flow using chrome.identity
    const authUrl = new URL('https://accounts.google.com/o/oauth2/auth');
    authUrl.searchParams.set('client_id', CLIENT_ID);
    authUrl.searchParams.set('response_type', 'token');
    authUrl.searchParams.set('redirect_uri', REDIRECT_URI);
    authUrl.searchParams.set('scope', SCOPES.join(' '));
    
    const responseUrl = await chrome.identity.launchWebAuthFlow({
      url: authUrl.toString(),
      interactive: true
    });
    
    // Parse the access token from the response
    const url = new URL(responseUrl);
    const params = new URLSearchParams(url.hash.substring(1));
    authToken = params.get('access_token');
    
    // Store the token
    await chrome.storage.local.set({ authToken });
    
    // Get user profile
    const userInfo = await fetchUserProfile(authToken);
    userProfile = userInfo;
    await chrome.storage.local.set({ userProfile });
    
    // Tell our backend server we're authenticated
    await sendAuthToBackend();
    
    return { success: true };
  } catch (error) {
    console.error('Authentication error:', error);
    return { success: false, error };
  }
}

// Fetch user profile information
async function fetchUserProfile(token) {
  const response = await fetch('https://www.googleapis.com/gmail/v1/users/me/profile', {
    headers: { Authorization: `Bearer ${token}` }
  });
  
  if (!response.ok) {
    throw new Error('Failed to fetch user profile');
  }
  
  return response.json();
}

// Send auth token to our backend service
async function sendAuthToBackend() {
  try {
    const response = await fetch(`${API_BASE_URL}/authenticate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        token: authToken,
        user_id: userProfile?.emailAddress
      })
    });
    
    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error sending auth to backend:', error);
    throw error;
  }
}

// Fetch email history
async function fetchEmailHistory() {
  if (!authToken || !userProfile) {
    throw new Error('Not authenticated');
  }
  
  try {
    const response = await fetch(`${API_BASE_URL}/fetch-history`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        user_id: userProfile.emailAddress
      })
    });
    
    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error fetching email history:', error);
    throw error;
  }
}

// Analyze writing voice
async function analyzeVoice() {
  if (!authToken || !userProfile) {
    throw new Error('Not authenticated');
  }
  
  try {
    const response = await fetch(`${API_BASE_URL}/analyze-voice`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        user_id: userProfile.emailAddress
      })
    });
    
    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error analyzing voice:', error);
    throw error;
  }
}

// Generate content
async function generateContent(options) {
  if (!authToken || !userProfile) {
    throw new Error('Not authenticated');
  }
  
  try {
    const response = await fetch(`${API_BASE_URL}/generate-content`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        user_id: userProfile.emailAddress,
        ...options
      })
    });
    
    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error generating content:', error);
    throw error;
  }
}

// Handle periodic mail checks
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'checkMailPeriodically') {
    // Check for new emails, etc.
    console.log('Checking mail periodically');
  }
});

// Listen for messages from content script and popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    try {
      if (message.action === 'authenticate') {
        const result = await authenticate();
        sendResponse(result);
      } 
      else if (message.action === 'fetchHistory') {
        const result = await fetchEmailHistory();
        sendResponse(result);
      }
      else if (message.action === 'analyzeVoice') {
        const result = await analyzeVoice();
        sendResponse(result);
      }
      else if (message.action === 'generateContent') {
        const result = await generateContent(message.options);
        sendResponse(result);
      }
      else if (message.action === 'getAuthStatus') {
        sendResponse({
          isAuthenticated: !!authToken,
          userProfile
        });
      }
    } catch (error) {
      console.error('Error handling message:', error);
      sendResponse({ success: false, error: error.message });
    }
  })();
  
  // Return true to indicate we'll respond asynchronously
  return true;
}); 