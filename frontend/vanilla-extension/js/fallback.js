// Fallback script to debug issues (separated from inline to avoid CSP violations)

// Check if main script loaded
setTimeout(() => {
  const debugInfo = document.getElementById('debug-info');
  
  if (!window.mailSenseInitialized) {
    debugInfo.textContent = "Error: popup.js did not initialize properly. Check the console for errors.";
    
    // Enable auth button for testing
    const authButton = document.getElementById('auth-button');
    if (authButton) {
      authButton.disabled = false;
      authButton.addEventListener('click', () => {
        debugInfo.textContent = "Auth button clicked at " + new Date().toLocaleTimeString();
      });
    }
    
    // Force debug panel open
    document.getElementById('debug-panel').setAttribute('open', 'true');
  }
  
  // Add reset handler
  document.getElementById('debug-reset').addEventListener('click', () => {
    chrome.storage.local.clear(() => {
      debugInfo.textContent = "Extension state reset at " + new Date().toLocaleTimeString();
      setTimeout(() => location.reload(), 1000);
    });
  });
}, 1000); 