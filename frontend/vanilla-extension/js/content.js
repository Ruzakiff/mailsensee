// MailSense content script - Simplified for copy-paste approach

console.log('MailSense content script loaded');

// Store user context
let userContext = null;

// Basic initialization
function initMailSense() {
  console.log('MailSense initialized');
  
  // Check authentication and load user profile
  chrome.storage.local.get('userState', (result) => {
    const userState = result.userState || {};
    console.log('User state loaded:', userState);
    
    // Store user context for generation calls
    if (userState.profile) {
      userContext = {
        name: userState.profile.name || undefined,
        role: userState.profile.role || undefined,
        company: userState.profile.company || undefined,
        industry: userState.profile.industry || undefined,
        additionalContext: userState.profile.additionalContext || undefined,
        emailStyle: userState.voiceAnalyzed ? "Analyzed from your previous emails" : "Default style"
      };
      console.log('User context loaded:', userContext);
    }
  });
}

// Wait for page to load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initMailSense);
} else {
  initMailSense();
}

// Add CSS for MailSense controls
const style = document.createElement('style');
style.textContent = `
  .mailsense-controls {
    display: flex;
    gap: 5px;
    margin-left: auto;
  }
  
  .mailsense-button {
    background: #4285f4;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 5px 10px;
    font-size: 12px;
    cursor: pointer;
    transition: background-color 0.2s;
  }
  
  .mailsense-button:hover {
    background: #3367d6;
  }
  
  .mailsense-suggestion-popup {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 80%;
    max-width: 600px;
    background: white;
    border-radius: 8px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.2);
    z-index: 10000;
  }
  
  .mailsense-suggestion-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 15px;
    border-bottom: 1px solid #eee;
  }
  
  .mailsense-suggestion-content {
    padding: 15px;
    max-height: 300px;
    overflow-y: auto;
  }
  
  .mailsense-suggestion-actions {
    padding: 10px 15px;
    text-align: right;
    border-top: 1px solid #eee;
  }
  
  .mailsense-apply-button {
    background: #4285f4;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 8px 15px;
    font-size: 14px;
    cursor: pointer;
  }
`;

document.head.appendChild(style);