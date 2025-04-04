// popup.js - Handles the extension popup UI

document.addEventListener('DOMContentLoaded', initPopup);

// Initialize popup UI
async function initPopup() {
  // Setup UI event listeners
  document.getElementById('auth-button').addEventListener('click', handleAuth);
  document.getElementById('fetch-history-button').addEventListener('click', handleFetchHistory);
  document.getElementById('analyze-voice-button').addEventListener('click', handleAnalyzeVoice);
  document.getElementById('help-link').addEventListener('click', showHelp);
  document.getElementById('settings-link').addEventListener('click', showSettings);
  
  // Check authentication status
  await checkAuthStatus();
}

// Check if user is authenticated
async function checkAuthStatus() {
  try {
    const response = await chrome.runtime.sendMessage({action: 'getAuthStatus'});
    
    if (response.isAuthenticated) {
      // User is authenticated
      updateAuthUI(true, response.userProfile);
      
      // Show status section
      document.getElementById('status-section').classList.remove('hidden');
      document.getElementById('actions-section').classList.remove('hidden');
      
      // Update status indicators
      document.getElementById('auth-indicator').className = 'status-value status-success';
      document.getElementById('auth-indicator').textContent = 'Authenticated';
      
      // Enable action buttons
      document.getElementById('fetch-history-button').disabled = false;
    } else {
      // User is not authenticated
      updateAuthUI(false);
    }
  } catch (error) {
    console.error('Error checking auth status:', error);
    updateAuthUI(false, null, error.message);
  }
}

// Update authentication UI
function updateAuthUI(isAuthenticated, userProfile = null, errorMessage = null) {
  const authStatus = document.getElementById('auth-status');
  const authButton = document.getElementById('auth-button');
  
  if (isAuthenticated) {
    authStatus.textContent = `Signed in as ${userProfile.emailAddress}`;
    authButton.textContent = 'Sign out';
    authButton.disabled = false;
  } else {
    authStatus.textContent = errorMessage || 'Not signed in';
    authButton.textContent = 'Sign in with Google';
    authButton.disabled = false;
  }
}

// Handle authentication button click
async function handleAuth() {
  const authButton = document.getElementById('auth-button');
  authButton.disabled = true;
  authButton.textContent = 'Please wait...';
  
  try {
    const response = await chrome.runtime.sendMessage({action: 'authenticate'});
    
    if (response.success) {
      // Update UI after successful authentication
      await checkAuthStatus();
    } else {
      // Show error
      updateAuthUI(false, null, response.error || 'Authentication failed');
    }
  } catch (error) {
    console.error('Auth error:', error);
    updateAuthUI(false, null, error.message);
  }
}

// Handle fetch history button click
async function handleFetchHistory() {
  // Update UI
  const historyButton = document.getElementById('fetch-history-button');
  const historyIndicator = document.getElementById('history-indicator');
  
  historyButton.disabled = true;
  historyButton.textContent = 'Fetching...';
  historyIndicator.className = 'status-value status-inprogress';
  historyIndicator.textContent = 'In progress...';
  
  try {
    const response = await chrome.runtime.sendMessage({action: 'fetchHistory'});
    
    if (response.success) {
      // Update status indicator
      historyIndicator.className = 'status-value status-success';
      historyIndicator.textContent = 'Complete';
      
      // Enable next step
      document.getElementById('analyze-voice-button').disabled = false;
    } else {
      // Show error
      historyIndicator.className = 'status-value status-error';
      historyIndicator.textContent = 'Error: ' + response.message;
    }
  } catch (error) {
    console.error('Fetch history error:', error);
    historyIndicator.className = 'status-value status-error';
    historyIndicator.textContent = 'Error: ' + error.message;
  } finally {
    // Re-enable button
    historyButton.disabled = false;
    historyButton.textContent = 'Fetch Email History';
  }
}

// Handle analyze voice button click
async function handleAnalyzeVoice() {
  // Update UI
  const analyzeButton = document.getElementById('analyze-voice-button');
  const voiceIndicator = document.getElementById('voice-indicator');
  
  analyzeButton.disabled = true;
  analyzeButton.textContent = 'Analyzing...';
  voiceIndicator.className = 'status-value status-inprogress';
  voiceIndicator.textContent = 'In progress...';
  
  try {
    const response = await chrome.runtime.sendMessage({action: 'analyzeVoice'});
    
    if (response.success) {
      // Update status indicator
      voiceIndicator.className = 'status-value status-success';
      voiceIndicator.textContent = 'Complete';
      
      // Enable completion button
      document.getElementById('setup-complete-button').disabled = false;
      document.getElementById('setup-complete-button').addEventListener('click', showCompletionSection);
    } else {
      // Show error
      voiceIndicator.className = 'status-value status-error';
      voiceIndicator.textContent = 'Error: ' + response.message;
    }
  } catch (error) {
    console.error('Analyze voice error:', error);
    voiceIndicator.className = 'status-value status-error';
    voiceIndicator.textContent = 'Error: ' + error.message;
  } finally {
    // Re-enable button
    analyzeButton.disabled = false;
    analyzeButton.textContent = 'Analyze Writing Style';
  }
}

// Show completion section
function showCompletionSection() {
  document.getElementById('actions-section').classList.add('hidden');
  document.getElementById('complete-section').classList.remove('hidden');
}

// Show help
function showHelp() {
  chrome.tabs.create({
    url: 'https://mailsense-app.com/help'
  });
}

// Show settings
function showSettings() {
  chrome.tabs.create({
    url: 'settings.html'
  });
}