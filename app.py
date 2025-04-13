from flask import Flask, request, jsonify, redirect, session, url_for
from flask_cors import CORS
import os
import json
import time
from mailsense.auth import get_credentials
from dotenv import load_dotenv
import importlib.util
import sys
import requests
import asyncio
import secrets
import pickle
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
import urllib.parse
import logging
from logging.handlers import RotatingFileHandler
from mailsense.storage import (read_file, write_file, append_to_file, 
                               file_exists, read_pickle, write_pickle,
                               list_files, delete_file, ensure_bucket_exists)

# Configure logging
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "mailsense.log")

# Create a custom formatter with more details
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)

# Set up file handler with rotation
file_handler = RotatingFileHandler(log_file, maxBytes=10485760, backupCount=10)
file_handler.setFormatter(formatter)

# Set up console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# Configure root logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Load environment variables
logger.info("Loading environment variables")
load_dotenv()

# Import modules dynamically
def import_module_from_file(module_name, file_path):
    logger.info(f"Dynamically importing module {module_name} from {file_path}")
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

# Import the necessary modules
logger.info("Importing required modules")
gmail_history = import_module_from_file("gmail_history", "gmail_history.py")
findvoice = import_module_from_file("findvoice", "findvoice.py")
generate = import_module_from_file("generate", "generate.py")

app = Flask(__name__)
CORS(app)  # Enable CORS for Chrome extension
logger.info("Flask app initialized with CORS enabled")

# Directory for user data
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_data")
os.makedirs(DATA_DIR, exist_ok=True)
logger.info(f"User data directory created at {DATA_DIR}")

# Add this to your Flask app initialization
app.secret_key = secrets.token_hex(16)  # For session management
logger.info("Flask secret key generated for session management")

# Store pending auth requests
auth_requests = {}

# Ensure S3 bucket exists when app starts
logger.info("Ensuring S3 bucket exists")
ensure_bucket_exists()

# For async job processing
import threading
import uuid

# Dictionary to store running jobs
email_fetch_jobs = {}

@app.route('/')
def index():
    """Root endpoint that provides API information"""
    logger.info("Root endpoint accessed")
    api_info = {
        "name": "MailSense API",
        "version": "1.0",
        "endpoints": [
            {"path": "/api/authenticate", "method": "POST", "description": "Start OAuth flow for authentication"},
            {"path": "/oauth2callback", "method": "GET", "description": "OAuth callback handler"},
            {"path": "/api/fetch-history", "method": "POST", "description": "Fetch email history"},
            {"path": "/api/analyze-voice", "method": "POST", "description": "Analyze writing voice"},
            {"path": "/api/generate-content", "method": "POST", "description": "Generate content based on voice"}
        ]
    }
    return jsonify(api_info)

@app.route('/api/authenticate', methods=['POST'])
def authenticate():
    """Start OAuth flow with proper redirects"""
    logger.info("Authentication endpoint accessed")
    try:
        # Get or create user_id
        data = request.json
        user_id = data.get('user_id')
        
        # If no user_id provided, create one
        if not user_id:
            user_id = f"user_{secrets.token_hex(8)}"
            logger.info(f"Created new user_id: {user_id}")
        else:
            logger.info(f"Using provided user_id: {user_id}")
        
        # Create a state token to prevent CSRF
        state = secrets.token_hex(16)
        logger.info(f"Generated state token: {state}")
        
        # Look for client secrets in environment or file
        client_secrets_file = None
        
        # First, try to use environment variable
        secret_content = os.environ.get('GOOGLE_CLIENT_SECRETS')
        if secret_content:
            logger.info("Using client secrets from environment variable")
            # Write the content to a temporary file
            secrets_path = os.path.join(os.getcwd(), "client_secret_temp.json")
            with open(secrets_path, 'w') as f:
                f.write(secret_content)
            client_secrets_file = secrets_path
        else:
            # Fall back to looking for client secret files
            logger.info("Looking for client secrets file on disk")
            import glob
            client_secret_files = glob.glob("client_secret*.json")
            if client_secret_files:
                client_secrets_file = client_secret_files[0]
                logger.info(f"Found client secrets file: {client_secrets_file}")
        
        if not client_secrets_file:
            logger.error("No client secrets file found")
            return jsonify({"success": False, "message": "No client secrets file found"}), 400
        
        logger.info(f"Using credentials file: {client_secrets_file}")
        
        # Read client_id from client secrets file
        with open(client_secrets_file, 'r') as f:
            client_info = json.load(f)
            # Check if this is a web or installed client
            client_type = "web" if "web" in client_info else "installed"
            client_id = client_info[client_type]['client_id']
            logger.info(f"Using client type: {client_type}, client_id: {client_id[:8]}...")
        
        # Create the authorization URL
        SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
        
        # Use the redirect URI that's registered in Google Cloud Console
        redirect_uri = 'https://reelbrief.ai/oauth2callback'
        
        logger.info(f"Using redirect URI: {redirect_uri}")
        
        # Store user_id with auth request
        auth_requests[state] = {
            'client_secrets_file': client_secrets_file, 
            'return_url': request.headers.get('Referer'),
            'user_id': user_id,
            'redirect_uri': redirect_uri
        }
        logger.info(f"Stored auth request for state: {state}")
        
        # Build authorization URL
        params = {
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'scope': ' '.join(SCOPES),
            'response_type': 'code',
            'state': state,
            'access_type': 'offline',
            'prompt': 'consent'
        }
        
        auth_url = f"https://accounts.google.com/o/oauth2/auth?{urllib.parse.urlencode(params)}"
        logger.info(f"Generated auth URL: {auth_url[:60]}...")
        
        # Return the URL - extension will open this in a new tab
        return jsonify({"success": True, "auth_url": auth_url, "user_id": user_id})
    except Exception as e:
        import traceback
        traceback_str = traceback.format_exc()
        logger.error(f"Authentication error: {str(e)}")
        logger.error(traceback_str)
        return jsonify({"success": False, "message": str(e)}), 400

# Add a callback endpoint for OAuth
@app.route('/oauth2callback')
def oauth_callback():
    """Handle OAuth callback and exchange code for token"""
    logger.info("OAuth callback endpoint accessed")
    error = request.args.get('error')
    if error:
        logger.error(f"OAuth error received: {error}")
        return f"Error: {error}"
    
    state = request.args.get('state')
    if not state or state not in auth_requests:
        logger.error(f"Invalid state parameter: {state}")
        return "Invalid state parameter"
    
    auth_info = auth_requests.pop(state)
    code = request.args.get('code')
    user_id = auth_info.get('user_id', 'default')
    logger.info(f"Processing OAuth callback for user_id: {user_id}, state: {state}")
    
    try:
        # Create Flow instance with client secrets file
        logger.info(f"Creating OAuth flow with redirect URI: {auth_info['redirect_uri']}")
        flow = Flow.from_client_secrets_file(
            auth_info['client_secrets_file'],
            scopes=['https://www.googleapis.com/auth/gmail.readonly'],
            redirect_uri=auth_info['redirect_uri']
        )
        
        # Exchange code for credentials
        logger.info("Exchanging authorization code for credentials")
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        # Save the credentials to S3 instead of local file
        logger.info(f"Saving credentials to S3 for user_id: {user_id}")
        credentials_pickle = pickle.dumps(credentials)
        write_pickle(user_id, "gmail_credentials.pickle", credentials)
        logger.info("Credentials saved successfully")
        
        # Return success page with auto-close script
        logger.info("Returning success page to user")
        return """
        <html>
        <head>
            <title>Authentication Successful</title>
            <style>
                body { font-family: Arial, sans-serif; text-align: center; padding-top: 50px; }
                .success { color: green; }
                .container { max-width: 600px; margin: 0 auto; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1 class="success">Authentication Successful!</h1>
                <p>You can now close this window and return to the extension.</p>
            </div>
            <script>
                // Send message to extension that auth is complete
                setTimeout(function() {
                    window.close();
                }, 3000);
            </script>
        </body>
        </html>
        """
    except Exception as e:
        logger.error(f"Error exchanging code: {str(e)}")
        return f"Error exchanging code: {str(e)}"

# Add an endpoint to check auth status
@app.route('/api/auth-status', methods=['GET'])
def auth_status():
    """Check if user is authenticated by verifying their credentials exist in S3"""
    try:
        user_id = request.args.get('user_id', 'default')
        logger.info(f"Checking auth status for user_id: {user_id}")
        
        # Check if credentials exist in S3 instead of local file
        credentials_file = "gmail_credentials.pickle"
        if file_exists(user_id, credentials_file):
            logger.info(f"Credentials file found for user_id: {user_id}")
            try:
                # Try to load credentials to verify they're valid
                creds = read_pickle(user_id, credentials_file)
                
                if creds and creds.valid:
                    logger.info(f"Valid credentials found for user_id: {user_id}")
                    return jsonify({"authenticated": True})
                elif creds and creds.expired and creds.refresh_token:
                    logger.info(f"Expired credentials found for user_id: {user_id}, attempting refresh")
                    try:
                        creds.refresh(Request())
                        # Update refreshed credentials in S3
                        logger.info(f"Credentials refreshed successfully for user_id: {user_id}")
                        write_pickle(user_id, credentials_file, creds)
                        return jsonify({"authenticated": True})
                    except Exception as refresh_error:
                        logger.error(f"Error refreshing credentials: {refresh_error}")
            except Exception as e:
                logger.error(f"Error reading credentials from S3: {e}")
                    
        logger.info(f"No valid credentials found for user_id: {user_id}")
        return jsonify({"authenticated": False})
    except Exception as e:
        logger.error(f"Error checking auth status: {e}")
        return jsonify({"authenticated": False, "error": str(e)})

@app.route('/api/start-fetch-history', methods=['POST'])
def start_fetch_history():
    """Start an asynchronous email history fetch job."""
    try:
        data = request.json
        user_id = data.get('user_id', 'default')
        logger.info(f"Start fetch history endpoint accessed for user_id: {user_id}")
        
        # Get date range if specified
        after_date = data.get('after_date', '2014/01/01')
        before_date = data.get('before_date', '2022/01/01')
        email_limit = int(data.get('limit', 1000))
        
        logger.info(f"Fetch parameters - after_date: {after_date}, before_date: {before_date}, limit: {email_limit}")
        
        # Generate a unique job ID
        job_id = str(uuid.uuid4())
        logger.info(f"Generated job_id: {job_id} for user_id: {user_id}")
        
        # Store job parameters and initial status
        job_info = {
            'job_id': job_id,
            'user_id': user_id,
            'status': 'pending',
            'params': {
                'after_date': after_date,
                'before_date': before_date,
                'limit': email_limit
            },
            'progress': {
                'total_fetched': 0,
                'processed': 0,
                'limit_reached': False
            },
            'start_time': time.time(),
            'last_updated': time.time()
        }
        
        # Store job info in S3
        write_file(user_id, f"jobs/{job_id}/status.json", json.dumps(job_info))
        
        # Start the fetch in a background thread
        thread = threading.Thread(
            target=fetch_emails_async,
            args=(job_id, user_id, after_date, before_date, email_limit)
        )
        thread.daemon = True  # Make thread a daemon so it doesn't block app shutdown
        
        # Store the thread in memory
        email_fetch_jobs[job_id] = {
            'thread': thread,
            'info': job_info
        }
        
        # Start the thread
        thread.start()
        logger.info(f"Started background thread for job_id: {job_id}")
        
        return jsonify({
            "success": True,
            "message": "Email fetch job started successfully",
            "job_id": job_id
        })
    except Exception as e:
        logger.error(f"Error starting fetch history job: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": str(e)}), 400

@app.route('/api/fetch-history-status', methods=['GET'])
def fetch_history_status():
    """Check the status of an asynchronous email fetch job."""
    try:
        job_id = request.args.get('job_id')
        user_id = request.args.get('user_id', 'default')
        
        if not job_id:
            return jsonify({"success": False, "message": "No job_id provided"}), 400
        
        logger.info(f"Checking status for job_id: {job_id}, user_id: {user_id}")
        
        # Check if job status file exists in S3
        job_status_file = f"jobs/{job_id}/status.json"
        
        if not file_exists(user_id, job_status_file):
            logger.error(f"Job status file not found for job_id: {job_id}")
            return jsonify({
                "success": False,
                "message": f"Job not found with ID: {job_id}"
            }), 404
        
        # Read job status from S3
        job_status_content = read_file(user_id, job_status_file)
        job_status = json.loads(job_status_content)
        
        # Check if job is completed and output file exists
        output_file = "sent_emails.txt"
        output_exists = file_exists(user_id, output_file)
        
        # Get stats if available
        stats_file = "email_extraction_stats.txt"
        stats = {}
        if file_exists(user_id, stats_file):
            stats_content = read_file(user_id, stats_file)
            stats_lines = stats_content.split("\n")
            for line in stats_lines:
                if ":" in line:
                    key, value = line.split(":", 1)
                    stats[key.strip()] = value.strip()
        
        # Return comprehensive status information
        response = {
            "success": True,
            "job_id": job_id,
            "status": job_status.get("status", "unknown"),
            "progress": job_status.get("progress", {}),
            "start_time": job_status.get("start_time"),
            "last_updated": job_status.get("last_updated"),
            "output_ready": output_exists and job_status.get("status") == "completed",
            "stats": stats
        }
        
        # If job is completed, add more details
        if job_status.get("status") == "completed":
            response["message"] = "Email fetch job completed successfully"
            response["output_file"] = output_file
            response["emails_processed"] = job_status.get("progress", {}).get("total_fetched", 0)
            response["emails_with_content"] = job_status.get("progress", {}).get("processed", 0)
            response["limit_reached"] = job_status.get("progress", {}).get("limit_reached", False)
        
        # If job failed, include error message
        if job_status.get("status") == "failed":
            response["message"] = job_status.get("error", "Job failed with unknown error")
        
        logger.info(f"Returning status for job_id: {job_id}: {job_status.get('status')}")
        return jsonify(response)
    except Exception as e:
        logger.error(f"Error checking fetch history status: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": str(e)}), 400

def fetch_emails_async(job_id, user_id, after_date, before_date, email_limit):
    """Asynchronously fetch emails from Gmail - runs in background thread"""
    logger.info(f"Starting async email fetch for job_id: {job_id}, user_id: {user_id}")
    
    # Update job status to in_progress
    update_job_status(job_id, user_id, "in_progress")
    
    try:
        # Set the query to get sent emails from the specified date range
        query = f"in:sent after:{after_date} before:{before_date}"
        
        # Create the Gmail client
        client = gmail_history.GmailClient(user_id)
        
        # Prepare output file
        output_file = f"sent_emails.txt"
        
        # Check if we have a progress file in S3
        progress_file = f"email_fetch_progress.txt"
        processed_ids = set()
        
        if file_exists(user_id, progress_file):
            progress_content = read_file(user_id, progress_file)
            processed_ids = set(line.strip() for line in progress_content.split('\n') if line.strip())
            logger.info(f"Resuming from previous run, {len(processed_ids)} emails already processed.")
        else:
            logger.info(f"No progress file found, starting fresh fetch for user_id: {user_id}")
        
        # Track our progress
        page_token = None
        total_fetched = 0
        actual_processed = 0
        limit_reached = False
        
        # Loop to handle pagination
        while True:
            # Check if we've reached the limit
            if total_fetched >= email_limit:
                logger.info(f"Reached email processing limit of {email_limit}")
                limit_reached = True
                break
            
            # Fetch a batch of emails
            try:
                logger.info(f"Fetching batch of messages, page_token: {page_token}")
                results = client.service.users().messages().list(
                    userId='me',
                    q=query,
                    maxResults=min(100, email_limit - total_fetched),  # Don't fetch more than we need
                    pageToken=page_token
                ).execute()
            except Exception as e:
                logger.error(f"Error fetching messages: {e}")
                update_job_status(job_id, user_id, "failed", error=str(e))
                return
            
            messages = results.get('messages', [])
            if not messages:
                logger.info("No more messages found in Gmail")
                break
                
            batch_size = len(messages)
            logger.info(f"Processing batch of {batch_size} emails...")
            
            # Process each message
            for i, message in enumerate(messages):
                # Check if we've reached the limit
                if total_fetched >= email_limit:
                    logger.info(f"Reached email processing limit of {email_limit} during batch")
                    limit_reached = True
                    break
                    
                total_fetched += 1
                msg_id = message['id']
                
                # Skip if already processed
                if msg_id in processed_ids:
                    logger.debug(f"Skipping already processed message: {msg_id}")
                    continue
                
                try:
                    # Get full message details
                    logger.debug(f"Fetching full message details for ID: {msg_id}")
                    msg = client.service.users().messages().get(
                        userId='me', id=msg_id, format='full'
                    ).execute()
                    
                    # Extract email details
                    headers = msg['payload']['headers']
                    subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
                    to = next((h['value'] for h in headers if h['name'].lower() == 'to'), 'Unknown')
                    date = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'Unknown')
                    
                    logger.debug(f"Processing email - Date: {date}, Subject: {subject[:30]}...")
                    
                    # Extract body
                    body = ""
                    if 'parts' in msg['payload']:
                        for part in msg['payload']['parts']:
                            if part['mimeType'] == 'text/plain':
                                body = gmail_history.decode_body(part['body'].get('data', ''))
                                logger.debug("Extracted plain text body")
                                break
                            elif part['mimeType'] == 'text/html' and not body:
                                body = gmail_history.clean_html(gmail_history.decode_body(part['body'].get('data', '')))
                                logger.debug("Extracted and cleaned HTML body")
                    elif 'body' in msg['payload'] and 'data' in msg['payload']['body']:
                        body = gmail_history.decode_body(msg['payload']['body'].get('data', ''))
                        logger.debug("Extracted body from payload")
                    
                    # Extract only the user's original content
                    your_content = gmail_history.extract_your_content(body, date)
                    
                    # Skip emails with empty content after extraction
                    if not your_content.strip():
                        logger.debug(f"Skipping email with no original content: {msg_id}")
                        # Mark as processed to avoid reprocessing
                        append_to_file(user_id, progress_file, f"{msg_id}\n")
                        processed_ids.add(msg_id)
                        continue
                    
                    # Write to S3 instead of local file
                    email_content = f"Email ID: {msg_id}\nDate: {date}\nTo: {to}\nSubject: {subject}\nYour Content:\n{your_content}\n{'='*80}\n\n"
                    append_to_file(user_id, output_file, email_content)
                    logger.debug(f"Saved email content to S3 for ID: {msg_id}")
                    
                    # Mark as processed in S3
                    append_to_file(user_id, progress_file, f"{msg_id}\n")
                    processed_ids.add(msg_id)
                    actual_processed += 1
                    
                    # Update job status every 10 emails
                    if (i + 1) % 10 == 0:
                        update_job_progress(job_id, user_id, total_fetched, actual_processed, limit_reached)
                        logger.info(f"  Processed {i + 1}/{batch_size} in current batch, saved {actual_processed} emails")
                    
                except Exception as e:
                    logger.error(f"Error processing message {msg_id}: {e}")
                
                # Sleep briefly to avoid hitting rate limits
                time.sleep(0.05)
            
            # Check if limit was reached during batch processing
            if limit_reached:
                break
            
            logger.info(f"Batch complete. Total processed: {total_fetched}, saved: {actual_processed} with user content.")
            
            # Update job status after each batch
            update_job_progress(job_id, user_id, total_fetched, actual_processed, limit_reached)
            
            # Check if there are more pages
            page_token = results.get('nextPageToken')
            if not page_token:
                logger.info("No more pages of results available")
                break
        
        # Add stats about the extraction to S3
        stats_content = f"Total emails fetched: {total_fetched}\n"
        stats_content += f"Emails with user content extracted: {actual_processed}\n"
        stats_content += f"Extraction date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        stats_content += f"Limit reached: {limit_reached}\n"
        stats_content += f"Email limit: {email_limit}\n"
        write_file(user_id, "email_extraction_stats.txt", stats_content)
        
        # Update job status to completed
        update_job_status(
            job_id, 
            user_id, 
            "completed", 
            progress={
                'total_fetched': total_fetched,
                'processed': actual_processed,
                'limit_reached': limit_reached
            }
        )
        
        logger.info(f"Email fetch complete for job_id: {job_id}, user_id: {user_id}. Found {total_fetched} emails, saved {actual_processed}.")
        
    except Exception as e:
        logger.error(f"Error in async fetch_emails: {str(e)}", exc_info=True)
        update_job_status(job_id, user_id, "failed", error=str(e))

def update_job_status(job_id, user_id, status, error=None, progress=None):
    """Update the status of a job in S3"""
    logger.info(f"Updating job status for job_id: {job_id} to {status}")
    
    job_status_file = f"jobs/{job_id}/status.json"
    
    # Read current job info if it exists
    current_job_info = {}
    if file_exists(user_id, job_status_file):
        try:
            job_info_content = read_file(user_id, job_status_file)
            current_job_info = json.loads(job_info_content)
        except Exception as e:
            logger.error(f"Error reading job status: {e}")
    
    # Update job info
    current_job_info['status'] = status
    current_job_info['last_updated'] = time.time()
    
    if error:
        current_job_info['error'] = error
    
    if progress:
        current_job_info['progress'] = progress
    
    # Write updated job info to S3
    write_file(user_id, job_status_file, json.dumps(current_job_info))
    
    # Also update in-memory tracking if job is in memory
    if job_id in email_fetch_jobs:
        email_fetch_jobs[job_id]['info'] = current_job_info

def update_job_progress(job_id, user_id, total_fetched, actual_processed, limit_reached):
    """Update only the progress part of job status"""
    progress = {
        'total_fetched': total_fetched,
        'processed': actual_processed, 
        'limit_reached': limit_reached
    }
    
    # Get current job info
    job_status_file = f"jobs/{job_id}/status.json"
    
    # Read current job info if it exists
    current_job_info = {}
    if file_exists(user_id, job_status_file):
        try:
            job_info_content = read_file(user_id, job_status_file)
            current_job_info = json.loads(job_info_content)
        except Exception as e:
            logger.error(f"Error reading job status: {e}")
    
    # Update just the progress
    current_job_info['progress'] = progress
    current_job_info['last_updated'] = time.time()
    
    # Write updated job info to S3
    write_file(user_id, job_status_file, json.dumps(current_job_info))
    
    # Also update in-memory tracking if job is in memory
    if job_id in email_fetch_jobs:
        email_fetch_jobs[job_id]['info']['progress'] = progress
        email_fetch_jobs[job_id]['info']['last_updated'] = time.time()

# Keep the existing fetch-history endpoint for backward compatibility
@app.route('/api/fetch-history', methods=['POST'])
def fetch_history():
    """Legacy synchronous endpoint - starts a job and waits for completion"""
    logger.info("Legacy fetch-history endpoint accessed - redirecting to async implementation")
    try:
        # Start the async job
        data = request.json
        user_id = data.get('user_id', 'default')
        
        # Call the async endpoint internally
        response = start_fetch_history()
        response_data = response.get_json()
        
        if not response_data.get('success', False):
            return response
        
        job_id = response_data.get('job_id')
        logger.info(f"Waiting for async job {job_id} to complete")
        
        # Wait for the job to complete (with timeout)
        start_time = time.time()
        max_wait_time = 300  # 5 minutes max wait
        
        while time.time() - start_time < max_wait_time:
            # Check job status
            job_status_file = f"jobs/{job_id}/status.json"
            
            if file_exists(user_id, job_status_file):
                job_info_content = read_file(user_id, job_status_file)
                job_info = json.loads(job_info_content)
                
                status = job_info.get('status')
                
                if status == 'completed':
                    logger.info(f"Job {job_id} completed successfully")
                    # Return success with job details
                    progress = job_info.get('progress', {})
                    return jsonify({
                        "success": True,
                        "message": "Email history fetched successfully",
                        "job_id": job_id,
                        "output_file": "sent_emails.txt",
                        "emails_processed": progress.get('total_fetched', 0),
                        "emails_with_content": progress.get('processed', 0),
                        "limit_reached": progress.get('limit_reached', False)
                    })
                
                if status == 'failed':
                    logger.info(f"Job {job_id} failed")
                    return jsonify({
                        "success": False,
                        "message": job_info.get('error', 'Unknown error occurred')
                    }), 400
            
            # Sleep for a bit before checking again
            time.sleep(2)
        
        # If we get here, the job is taking too long
        logger.warning(f"Job {job_id} is taking too long - returning job ID to client")
        return jsonify({
            "success": True,
            "message": "Job started but taking longer than expected",
            "job_id": job_id,
            "async": True  # Indicate that client should poll for results
        })
        
    except Exception as e:
        logger.error(f"Error in fetch_history: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": str(e)}), 400

@app.route('/api/analyze-voice', methods=['POST'])
def analyze_voice():
    """Process emails to extract authentic voice patterns"""
    try:
        data = request.json
        user_id = data.get('user_id', 'default')
        logger.info(f"Analyze voice endpoint accessed for user_id: {user_id}")
        
        # Set file paths - Currently using local filesystem
        input_file = "sent_emails.txt"
        output_file = "filtered_voice_emails.txt"
        
        # Check if input file exists in S3 instead of local
        if not file_exists(user_id, input_file):
            logger.error(f"Input file not found for user_id: {user_id}")
            return jsonify({
                "success": False,
                "message": f"Input file not found: {input_file}. Please run fetch-history first."
            }), 400
        
        # Setup findvoice arguments
        old_argv = sys.argv.copy()
        
        # Get model from request
        model = data.get('model', 'gpt-4o')
        logger.info(f"Using model: {model} for voice analysis")
        
        # Configure arguments for findvoice.main() - Update to use user_id for S3
        sys.argv = [
            'findvoice.py',
            '--user-id', user_id,  # Add user_id parameter
            '--input', input_file,  # Change to just the filename
            '--output', output_file,
            '--model', model,
            '--optimize'  # Enable optimization for better results
        ]
        
        # Add optional parameters if provided
        if data.get('chunk_size'):
            chunk_size = data.get('chunk_size')
            sys.argv.extend(['--chunk-size', str(chunk_size)])
            logger.info(f"Using custom chunk size: {chunk_size}")
        
        if data.get('target_tokens'):
            target_tokens = data.get('target_tokens')
            sys.argv.extend(['--target-tokens', str(target_tokens)])
            logger.info(f"Using custom target tokens: {target_tokens}")
        
        logger.info(f"Running voice analysis with args: {sys.argv}")
        
        # Run the findvoice main function
        result = asyncio.run(findvoice.main())
        
        # Restore original argv
        sys.argv = old_argv
        
        if result != 0:
            logger.error(f"Voice analysis failed with error code {result}")
            return jsonify({
                "success": False,
                "message": f"Voice analysis failed with error code {result}"
            }), 400
        
        logger.info(f"Voice analysis completed successfully for user_id: {user_id}")
        return jsonify({
            "success": True, 
            "message": "Voice analysis completed",
            "output_file": output_file
        })
    except Exception as e:
        logger.error(f"Error in analyze_voice: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": str(e)}), 400

@app.route('/api/generate-content', methods=['POST'])
def generate_content():
    """Generate content matching the user's writing style"""
    try:
        data = request.json
        user_id = data.get('user_id', 'default')
        prompt = data.get('prompt', '')
        genre = data.get('genre', 'email')
        topic = data.get('topic', 'response')
        tone = data.get('tone', 'professional')
        recipient = data.get('recipient', 'colleague')
        length = data.get('length', 300)
        model = data.get('model', 'gpt-4o')
        
        logger.info(f"Generate content endpoint accessed for user_id: {user_id}")
        logger.info(f"Generation parameters - model: {model}, genre: {genre}, topic: {topic}, tone: {tone}, length: {length}")
        
        # Get the user context if provided
        context = data.get('context', {})
        if context:
            logger.info(f"User context provided: {json.dumps(context)[:100]}...")
        
        # Use S3 filename instead of local path
        examples_file = "filtered_voice_emails.txt"
        
        # Check if examples file exists in S3
        if not file_exists(user_id, examples_file):
            logger.error(f"Examples file not found for user_id: {user_id}")
            return jsonify({
                "success": False,
                "message": f"Examples file not found: {examples_file}. Please run analyze-voice first."
            }), 400
        
        # Call the generate function with S3 access
        if prompt:
            # Use free-form prompt mode when prompt is provided
            logger.info(f"Using free-form prompt: {prompt[:50]}...")
            generated_text = generate.generate_matching_text(
                user_id=user_id,  # Pass user_id for S3 access
                examples_file=examples_file,
                model=model,
                max_tokens=2000,
                length=length,
                free_form_prompt=prompt,
                temperature=0,  # Low temperature for more predictable results
                user_context=context  # Pass the user context
            )
        else:
            # Fallback to structured parameters if no prompt provided
            logger.info(f"Using structured parameters for generation")
            generated_text = generate.generate_matching_text(
                user_id=user_id,  # Pass user_id for S3 access
                examples_file=examples_file,
                model=model,
                max_tokens=2000,
                genre=genre,
                topic=topic,
                tone=tone,
                recipient=recipient,
                length=length,
                user_context=context  # Pass the user context
            )
        
        logger.info(f"Content generation successful, generated {len(generated_text)} characters")
        return jsonify({
            "success": True,
            "generated_text": generated_text
        })
    except Exception as e:
        logger.error(f"Error in generate_content: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": str(e)}), 400

@app.route('/api/refine-content', methods=['POST'])
def refine_content():
    """Refine previously generated content while maintaining the user's style"""
    try:
        data = request.json
        user_id = data.get('user_id', 'default')
        original_text = data.get('original_text', '')
        refinement_instructions = data.get('refinement', '')
        model = data.get('model', 'gpt-4o')
        
        logger.info(f"Refine content endpoint accessed for user_id: {user_id}")
        logger.info(f"Refinement parameters - model: {model}")
        logger.info(f"Refinement instructions: {refinement_instructions[:100]}...")
        
        # Get the user context if provided
        context = data.get('context', {})
        if context:
            logger.info(f"User context provided: {json.dumps(context)[:100]}...")
        
        if not original_text:
            logger.error("Original text is required but not provided")
            return jsonify({
                "success": False,
                "message": "Original text is required for refinement."
            }), 400
            
        if not refinement_instructions:
            logger.error("Refinement instructions are required but not provided")
            return jsonify({
                "success": False,
                "message": "Refinement instructions are required."
            }), 400
        
        # Use S3 filename instead of local path
        examples_file = "filtered_voice_emails.txt"
        
        # Check if examples file exists in S3
        if not file_exists(user_id, examples_file):
            logger.error(f"Examples file not found for user_id: {user_id}")
            return jsonify({
                "success": False,
                "message": f"Examples file not found: {examples_file}. Please run analyze-voice first."
            }), 400
        
        # Read examples from S3
        logger.info(f"Reading voice examples from S3 for user_id: {user_id}")
        examples = read_file(user_id, examples_file)
        
        # Call the refinement function with context
        logger.info("Calling refinement function")
        refined_text = generate.refine_generated_text(
            examples=examples,
            original_text=original_text,
            refinement_instructions=refinement_instructions,
            model=model,
            max_tokens=2000,
            temperature=0,
            user_context=context  # Pass the user context
        )
        
        logger.info(f"Content refinement successful, refined text length: {len(refined_text)} characters")
        return jsonify({
            "success": True,
            "refined_text": refined_text
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

if __name__ == "__main__":
    # Get host and port from environment variables with defaults
    host = os.environ.get('HOST', '0.0.0.0')  # Listen on all interfaces by default
    port = int(os.environ.get('PORT', 8080))
    debug = True
    
    print(f"Starting Flask server on {host}:{port} (debug={debug})...")
    app.run(host=host, port=port, debug=debug) 