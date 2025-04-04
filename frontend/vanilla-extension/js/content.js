// content.js - Integrates with Gmail UI

// Keep track of UI elements we've modified
let mailSenseElements = [];

// Initialize content script when DOM is ready
document.addEventListener('DOMContentLoaded', initMailSense);

function initMailSense() {
  console.log('MailSense content script initialized');
  
  // Check if user is authenticated
  checkAuthStatus();
  
  // Set up Gmail UI observers
  observeGmailUI();
}

// Check authentication status
async function checkAuthStatus() {
  try {
    const response = await chrome.runtime.sendMessage({action: 'getAuthStatus'});
    
    if (response.isAuthenticated) {
      console.log('User is authenticated:', response.userProfile);
      // Continue with UI setup
      setupMailSenseUI();
    } else {
      console.log('User is not authenticated');
      // Show auth prompt or notification
    }
  } catch (error) {
    console.error('Error checking auth status:', error);
  }
}

// Set up UI elements
function setupMailSenseUI() {
  // Add compose button enhancements
  enhanceComposeUI();
  
  // Add reply button enhancements
  enhanceReplyUI();
}

// Set up observers to watch for Gmail UI changes
function observeGmailUI() {
  // Gmail loads dynamically, so we need to observe DOM changes
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      if (mutation.addedNodes && mutation.addedNodes.length > 0) {
        // Check for compose windows
        const composeWindows = document.querySelectorAll('.compose-form');
        if (composeWindows.length > 0) {
          composeWindows.forEach(window => {
            if (!window.dataset.mailsenseProcessed) {
              enhanceComposeWindow(window);
              window.dataset.mailsenseProcessed = 'true';
            }
          });
        }
        
        // Check for reply areas
        const replyAreas = document.querySelectorAll('.reply-form');
        if (replyAreas.length > 0) {
          replyAreas.forEach(area => {
            if (!area.dataset.mailsenseProcessed) {
              enhanceReplyArea(area);
              area.dataset.mailsenseProcessed = 'true';
            }
          });
        }
      }
    });
  });
  
  // Start observing the document body for changes
  observer.observe(document.body, { childList: true, subtree: true });
}

// Enhance compose UI with MailSense features
function enhanceComposeUI() {
  // We'll implement this as the Gmail interface loads
  console.log('Setting up compose UI enhancements');
}

// Enhance reply UI with MailSense features
function enhanceReplyUI() {
  // We'll implement this as the Gmail interface loads
  console.log('Setting up reply UI enhancements');
}

// Enhance a specific compose window
function enhanceComposeWindow(composeWindow) {
  // Find the compose area
  const composeArea = composeWindow.querySelector('[role="textbox"]');
  if (!composeArea) return;
  
  // Create MailSense toolbar
  const toolbar = document.createElement('div');
  toolbar.className = 'mailsense-toolbar';
  toolbar.innerHTML = `
    <button class="mailsense-button mailsense-generate">Generate draft</button>
    <button class="mailsense-button mailsense-improve">Improve writing</button>
    <div class="mailsense-dropdown">
      <button class="mailsense-button">MailSense ▾</button>
      <div class="mailsense-dropdown-content">
        <a href="#" data-action="enhance">Enhance</a>
        <a href="#" data-action="shorten">Shorten</a>
        <a href="#" data-action="elaborate">Elaborate</a>
        <a href="#" data-action="formalize">More formal</a>
        <a href="#" data-action="casualize">More casual</a>
      </div>
    </div>
  `;
  
  // Insert toolbar before compose area
  composeArea.parentNode.insertBefore(toolbar, composeArea);
  
  // Store reference to our element
  mailSenseElements.push(toolbar);
  
  // Add event listeners
  toolbar.querySelector('.mailsense-generate').addEventListener('click', () => {
    handleGenerateDraft(composeArea);
  });
  
  toolbar.querySelector('.mailsense-improve').addEventListener('click', () => {
    handleImproveWriting(composeArea);
  });
  
  toolbar.querySelectorAll('.mailsense-dropdown-content a').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      handleDropdownAction(e.target.dataset.action, composeArea);
    });
  });
}

// Enhance a specific reply area
function enhanceReplyArea(replyArea) {
  // Similar to enhanceComposeWindow but for reply areas
  // Implementation would be adapted to Gmail's reply UI structure
}

// Generate a draft email based on user's style
async function handleGenerateDraft(composeArea) {
  // Get subject and recipient if available
  const subjectField = findSubjectField(composeArea);
  const recipientField = findRecipientField(composeArea);
  
  const subject = subjectField ? subjectField.value : '';
  const recipient = recipientField ? recipientField.value : '';
  
  // Show loading indicator
  showLoadingIndicator(composeArea);
  
  try {
    // Generate content based on recipient and subject
    const response = await chrome.runtime.sendMessage({
      action: 'generateContent',
      options: {
        prompt: `Write an email about "${subject}" to ${recipient}`,
        genre: 'email',
        topic: subject || 'general',
        recipient: recipient || 'colleague',
        length: 300
      }
    });
    
    if (response.success) {
      // Insert the generated text
      composeArea.innerHTML = response.generated_text;
    } else {
      // Show error
      showNotification('Error generating content: ' + response.message);
    }
  } catch (error) {
    console.error('Error generating draft:', error);
    showNotification('Error: ' + error.message);
  } finally {
    // Hide loading indicator
    hideLoadingIndicator(composeArea);
  }
}

// Improve existing writing
async function handleImproveWriting(composeArea) {
  const currentText = composeArea.innerText || composeArea.textContent;
  
  if (!currentText.trim()) {
    showNotification('Please write something first');
    return;
  }
  
  // Show loading indicator
  showLoadingIndicator(composeArea);
  
  try {
    // Send the current text for improvement
    const response = await chrome.runtime.sendMessage({
      action: 'generateContent',
      options: {
        prompt: `Improve this email while maintaining my writing style: ${currentText}`,
        length: currentText.split(' ').length
      }
    });
    
    if (response.success) {
      // Replace with improved text
      composeArea.innerHTML = response.generated_text;
    } else {
      // Show error
      showNotification('Error improving content: ' + response.message);
    }
  } catch (error) {
    console.error('Error improving writing:', error);
    showNotification('Error: ' + error.message);
  } finally {
    // Hide loading indicator
    hideLoadingIndicator(composeArea);
  }
}

// Handle dropdown actions (enhance, shorten, etc.)
async function handleDropdownAction(action, composeArea) {
  const currentText = composeArea.innerText || composeArea.textContent;
  
  if (!currentText.trim()) {
    showNotification(`Cannot ${action} empty text`);
    return;
  }
  
  // Map action to prompt
  const actionPrompts = {
    enhance: `Enhance this email while maintaining my writing style: ${currentText}`,
    shorten: `Make this email more concise while maintaining my writing style: ${currentText}`,
    elaborate: `Elaborate more on this email while maintaining my writing style: ${currentText}`,
    formalize: `Make this email more formal while maintaining my writing style: ${currentText}`,
    casualize: `Make this email more casual while maintaining my writing style: ${currentText}`
  };
  
  const prompt = actionPrompts[action];
  if (!prompt) return;
  
  // Show loading indicator
  showLoadingIndicator(composeArea);
  
  try {
    // Process the action
    const response = await chrome.runtime.sendMessage({
      action: 'generateContent',
      options: {
        prompt: prompt,
        length: currentText.split(' ').length
      }
    });
    
    if (response.success) {
      // Replace with processed text
      composeArea.innerHTML = response.generated_text;
    } else {
      // Show error
      showNotification(`Error ${action}ing content: ${response.message}`);
    }
  } catch (error) {
    console.error(`Error ${action}ing text:`, error);
    showNotification('Error: ' + error.message);
  } finally {
    // Hide loading indicator
    hideLoadingIndicator(composeArea);
  }
}

// Helper functions
function findSubjectField(composeArea) {
  // This would need to be adapted to Gmail's DOM structure
  return document.querySelector('input[name="subjectbox"]');
}

function findRecipientField(composeArea) {
  // This would need to be adapted to Gmail's DOM structure
  return document.querySelector('input[name="to"]');
}

function showLoadingIndicator(element) {
  const loader = document.createElement('div');
  loader.className = 'mailsense-loader';
  loader.innerHTML = '<div class="mailsense-spinner"></div><p>Processing...</p>';
  element.parentNode.insertBefore(loader, element.nextSibling);
}

function hideLoadingIndicator(element) {
  const loader = element.parentNode.querySelector('.mailsense-loader');
  if (loader) {
    loader.remove();
  }
}

function showNotification(message) {
  const notification = document.createElement('div');
  notification.className = 'mailsense-notification';
  notification.textContent = message;
  document.body.appendChild(notification);
  setTimeout(() => {
    notification.classList.add('show');
    setTimeout(() => {
      notification.classList.remove('show');
      setTimeout(() => {
        notification.remove();
      }, 300);
    }, 3000);
  }, 10);
}