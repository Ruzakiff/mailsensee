// Simplified content script
console.log('MailSense content script loaded');

// Basic initialization
function initMailSense() {
  console.log('MailSense initialized in Gmail');
  
  // Check authentication
  chrome.storage.local.get('userState', (result) => {
    const userState = result.userState || {};
    console.log('User state in Gmail:', userState);
    
    if (userState.setupComplete) {
      console.log('Setup complete, adding Gmail integration');
      // Here we would add buttons to Gmail compose windows
    } else {
      console.log('Setup not complete');
    }
  });
}

// Wait for page to load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initMailSense);
} else {
  initMailSense();
}