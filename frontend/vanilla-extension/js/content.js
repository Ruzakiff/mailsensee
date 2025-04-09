// MailSense content script - Enhanced with context support

console.log('MailSense content script loaded');

// Store user context
let userContext = null;

// Basic initialization
function initMailSense() {
  console.log('MailSense initialized in Gmail');
  
  // Check authentication and load user profile
  chrome.storage.local.get('userState', (result) => {
    const userState = result.userState || {};
    console.log('User state in Gmail:', userState);
    
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
    
    if (userState.setupComplete) {
      console.log('Setup complete, adding Gmail integration');
      setupGmailIntegration();
    } else {
      console.log('Setup not complete');
    }
  });
}

// Set up Gmail integration
function setupGmailIntegration() {
  // Observer to detect compose windows
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      if (mutation.addedNodes) {
        mutation.addedNodes.forEach((node) => {
          if (node.nodeType === 1) {
            const composeBoxes = node.querySelectorAll('.compose-container');
            composeBoxes.forEach(addMailSenseControls);
          }
        });
      }
    });
  });
  
  // Start observing
  observer.observe(document.body, { childList: true, subtree: true });
  
  // Check existing compose boxes
  document.querySelectorAll('.compose-container').forEach(addMailSenseControls);
}

// Add MailSense controls to compose box
function addMailSenseControls(composeBox) {
  // Check if already processed
  if (composeBox.querySelector('.mailsense-controls')) return;
  
  const toolbar = composeBox.querySelector('.compose-header');
  if (!toolbar) return;
  
  // Create controls
  const controls = document.createElement('div');
  controls.className = 'mailsense-controls';
  controls.innerHTML = `
    <button class="mailsense-button" data-action="complete">Complete</button>
    <button class="mailsense-button" data-action="rephrase">Rephrase</button>
    <button class="mailsense-button" data-action="suggest">Suggest</button>
  `;
  
  // Add to toolbar
  toolbar.appendChild(controls);
  
  // Add event listeners
  controls.querySelectorAll('.mailsense-button').forEach(button => {
    button.addEventListener('click', (e) => {
      e.preventDefault();
      const action = button.dataset.action;
      handleMailSenseAction(action, composeBox);
    });
  });
}

// Handle MailSense actions
async function handleMailSenseAction(action, composeBox) {
  try {
    const emailBody = composeBox.querySelector('.editable');
    if (!emailBody) return;
    
    const selectedText = window.getSelection().toString();
    const currentText = emailBody.innerText;
    
    console.log(`MailSense action: ${action}`);
    
    // Get prompt based on action
    let prompt, payload;
    switch (action) {
      case 'complete':
        prompt = 'Complete this email: ' + currentText;
        break;
      case 'rephrase':
        prompt = 'Rephrase this text: ' + (selectedText || currentText);
        break;
      case 'suggest':
        prompt = 'Suggest improvements for this email: ' + currentText;
        break;
    }
    
    // Build payload with context
    payload = {
      user_id: await getUserId(),
      prompt: prompt,
      context: userContext  // Include user profile context
    };
    
    // Call the API
    const response = await chrome.runtime.sendMessage({
      action: 'callApi',
      endpoint: 'generate-content',
      payload: payload
    });
    
    if (response.error) {
      console.error('Generation failed:', response.error);
      return;
    }
    
    // Apply the generated content
    applyGeneratedContent(action, response.generated_text, emailBody, selectedText);
    
  } catch (error) {
    console.error('Error in MailSense action:', error);
  }
}

// Apply generated content to compose box
function applyGeneratedContent(action, generatedText, emailBody, selectedText) {
  if (action === 'complete') {
    emailBody.innerText = generatedText;
  } else if (action === 'rephrase' && selectedText) {
    document.execCommand('insertText', false, generatedText);
  } else if (action === 'suggest') {
    // Create suggestion popup
    const popup = document.createElement('div');
    popup.className = 'mailsense-suggestion-popup';
    popup.innerHTML = `
      <div class="mailsense-suggestion-header">
        <h3>MailSense Suggestion</h3>
        <button class="mailsense-close-button">×</button>
      </div>
      <div class="mailsense-suggestion-content">${generatedText}</div>
      <div class="mailsense-suggestion-actions">
        <button class="mailsense-apply-button">Apply</button>
      </div>
    `;
    
    // Add to page
    document.body.appendChild(popup);
    
    // Add event listeners
    popup.querySelector('.mailsense-close-button').addEventListener('click', () => {
      popup.remove();
    });
    
    popup.querySelector('.mailsense-apply-button').addEventListener('click', () => {
      emailBody.innerText = generatedText;
      popup.remove();
    });
  }
}

// Get user ID from storage
async function getUserId() {
  return new Promise((resolve) => {
    chrome.storage.local.get('userState', (result) => {
      const userState = result.userState || {};
      resolve(userState.userId || 'unknown_user');
    });
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