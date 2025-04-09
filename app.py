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
from mailsense.storage import (read_file, write_file, append_to_file, 
                               file_exists, read_pickle, write_pickle,
                               list_files, delete_file, ensure_bucket_exists)

# Load environment variables
load_dotenv()

# Import modules dynamically
def import_module_from_file(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

# Import the necessary modules
gmail_history = import_module_from_file("gmail_history", "gmail_history.py")
findvoice = import_module_from_file("findvoice", "findvoice.py")
generate = import_module_from_file("generate", "generate.py")

app = Flask(__name__)
CORS(app)  # Enable CORS for Chrome extension

# Directory for user data
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_data")
os.makedirs(DATA_DIR, exist_ok=True)

# Add this to your Flask app initialization
app.secret_key = secrets.token_hex(16)  # For session management

# Store pending auth requests
auth_requests = {}

# Ensure S3 bucket exists when app starts
ensure_bucket_exists()

@app.route('/')
def index():
    """Root endpoint that provides API information"""
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
    try:
        # Get or create user_id
        data = request.json
        user_id = data.get('user_id')
        
        # If no user_id provided, create one
        if not user_id:
            user_id = f"user_{secrets.token_hex(8)}"
        
        # Create a state token to prevent CSRF
        state = secrets.token_hex(16)
        
        # Get client secrets file
        import glob
        client_secret_files = glob.glob("client_secret*.json")
        if not client_secret_files:
            return jsonify({"success": False, "message": "No client secrets file found"}), 400
        
        client_secrets_file = client_secret_files[0]
        
        # Read client_id from client secrets file
        with open(client_secrets_file, 'r') as f:
            client_info = json.load(f)
            client_id = client_info['installed']['client_id']
        
        # Create the authorization URL
        SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
        redirect_uri = url_for('oauth_callback', _external=True)
        
        # Store user_id with auth request
        auth_requests[state] = {
            'client_secrets_file': client_secrets_file, 
            'return_url': request.headers.get('Referer'),
            'user_id': user_id
        }
        
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
        
        # Return the URL - extension will open this in a new tab
        return jsonify({"success": True, "auth_url": auth_url, "user_id": user_id})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

# Add a callback endpoint for OAuth
@app.route('/oauth2callback')
def oauth_callback():
    """Handle OAuth callback and exchange code for token"""
    error = request.args.get('error')
    if error:
        return f"Error: {error}"
    
    state = request.args.get('state')
    if not state or state not in auth_requests:
        return "Invalid state parameter"
    
    auth_info = auth_requests.pop(state)
    code = request.args.get('code')
    user_id = auth_info.get('user_id', 'default')
    
    try:
        # Create tokens directory if it doesn't exist
        tokens_dir = os.path.join(DATA_DIR, 'tokens')
        os.makedirs(tokens_dir, exist_ok=True)
        
        # Create Flow instance with client secrets file
        flow = Flow.from_client_secrets_file(
            auth_info['client_secrets_file'],
            scopes=['https://www.googleapis.com/auth/gmail.readonly'],
            redirect_uri=url_for('oauth_callback', _external=True)
        )
        
        # Exchange code for credentials
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        # Save the credentials for this specific user
        token_path = os.path.join(tokens_dir, f"{user_id}.pickle")
        with open(token_path, 'wb') as token:
            pickle.dump(credentials, token)
        
        # Return success page with auto-close script
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
        return f"Error exchanging code: {str(e)}"

# Add an endpoint to check auth status
@app.route('/api/auth-status', methods=['GET'])
def auth_status():
    """Check if user is authenticated"""
    try:
        user_id = request.args.get('user_id', 'default')
        tokens_dir = os.path.join(DATA_DIR, 'tokens')
        token_path = os.path.join(tokens_dir, f"{user_id}.pickle")
        
        if os.path.exists(token_path):
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)
                
            if creds and creds.valid:
                return jsonify({"authenticated": True})
            elif creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    with open(token_path, 'wb') as token:
                        pickle.dump(creds, token)
                    return jsonify({"authenticated": True})
                except:
                    pass
                    
        return jsonify({"authenticated": False})
    except Exception as e:
        return jsonify({"authenticated": False, "error": str(e)})

@app.route('/api/fetch-history', methods=['POST'])
def fetch_history():
    """Fetch email history from Gmail."""
    try:
        data = request.json
        user_id = data.get('user_id', 'default')
        
        # Get date range if specified
        after_date = data.get('after_date', '2014/01/01')
        before_date = data.get('before_date', '2022/01/01')
        email_limit = int(data.get('limit', 1000))
        
        # Set the query to get sent emails from the specified date range
        query = f"in:sent after:{after_date} before:{before_date}"
        
        print(f"Fetching sent emails for {user_id} from {after_date} to {before_date}...")
        
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
            print(f"Resuming from previous run, {len(processed_ids)} emails already processed.")
        
        # Track our progress
        page_token = None
        total_fetched = 0
        actual_processed = 0
        limit_reached = False
        
        # Loop to handle pagination
        while True:
            # Check if we've reached the limit
            if total_fetched >= email_limit:
                print(f"Reached email processing limit of {email_limit}")
                limit_reached = True
                break
            
            # Fetch a batch of emails
            try:
                results = client.service.users().messages().list(
                    userId='me',
                    q=query,
                    maxResults=min(100, email_limit - total_fetched),  # Don't fetch more than we need
                    pageToken=page_token
                ).execute()
            except Exception as e:
                print(f"Error fetching messages: {e}")
                return jsonify({"success": False, "message": f"Error fetching messages: {str(e)}"}), 400
            
            messages = results.get('messages', [])
            if not messages:
                break
                
            batch_size = len(messages)
            print(f"Processing batch of {batch_size} emails...")
            
            # Process each message
            for i, message in enumerate(messages):
                # Check if we've reached the limit
                if total_fetched >= email_limit:
                    print(f"Reached email processing limit of {email_limit} during batch")
                    limit_reached = True
                    break
                    
                total_fetched += 1
                msg_id = message['id']
                
                # Skip if already processed
                if msg_id in processed_ids:
                    continue
                
                try:
                    # Get full message details
                    msg = client.service.users().messages().get(
                        userId='me', id=msg_id, format='full'
                    ).execute()
                    
                    # Extract email details
                    headers = msg['payload']['headers']
                    subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
                    to = next((h['value'] for h in headers if h['name'].lower() == 'to'), 'Unknown')
                    date = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'Unknown')
                    
                    # Extract body
                    body = ""
                    if 'parts' in msg['payload']:
                        for part in msg['payload']['parts']:
                            if part['mimeType'] == 'text/plain':
                                body = gmail_history.decode_body(part['body'].get('data', ''))
                                break
                            elif part['mimeType'] == 'text/html' and not body:
                                body = gmail_history.clean_html(gmail_history.decode_body(part['body'].get('data', '')))
                    elif 'body' in msg['payload'] and 'data' in msg['payload']['body']:
                        body = gmail_history.decode_body(msg['payload']['body'].get('data', ''))
                    
                    # Extract only the user's original content
                    your_content = gmail_history.extract_your_content(body, date)
                    
                    # Skip emails with empty content after extraction
                    if not your_content.strip():
                        print(f"Skipping email with no original content: {msg_id}")
                        # Mark as processed to avoid reprocessing
                        append_to_file(user_id, progress_file, f"{msg_id}\n")
                        processed_ids.add(msg_id)
                        continue
                    
                    # Write to S3 instead of local file
                    email_content = f"Email ID: {msg_id}\nDate: {date}\nTo: {to}\nSubject: {subject}\nYour Content:\n{your_content}\n{'='*80}\n\n"
                    append_to_file(user_id, output_file, email_content)
                    
                    # Mark as processed in S3
                    append_to_file(user_id, progress_file, f"{msg_id}\n")
                    processed_ids.add(msg_id)
                    actual_processed += 1
                    
                    # Progress update
                    if (i + 1) % 10 == 0:
                        print(f"  Processed {i + 1}/{batch_size} in current batch, saved {actual_processed} emails")
                    
                except Exception as e:
                    print(f"Error processing message {msg_id}: {e}")
                
                # Sleep briefly to avoid hitting rate limits
                time.sleep(0.05)
            
            # Check if limit was reached during batch processing
            if limit_reached:
                break
            
            print(f"Batch complete. Total processed: {total_fetched}, saved: {actual_processed} with user content.")
            
            # Check if there are more pages
            page_token = results.get('nextPageToken')
            if not page_token:
                break
        
        # Add stats about the extraction to S3
        stats_content = f"Total emails fetched: {total_fetched}\n"
        stats_content += f"Emails with user content extracted: {actual_processed}\n"
        stats_content += f"Extraction date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        stats_content += f"Limit reached: {limit_reached}\n"
        stats_content += f"Email limit: {email_limit}\n"
        write_file(user_id, "email_extraction_stats.txt", stats_content)
        
        limit_message = " (reached configured limit)" if limit_reached else ""
        
        return jsonify({
            "success": True, 
            "message": f"Email history fetched successfully. Found {total_fetched} emails{limit_message}, saved {actual_processed} with user-authored content.",
            "output_file": output_file,
            "emails_processed": total_fetched,
            "emails_with_content": actual_processed,
            "limit_reached": limit_reached
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

@app.route('/api/analyze-voice', methods=['POST'])
def analyze_voice():
    """Process emails to extract authentic voice patterns"""
    try:
        data = request.json
        user_id = data.get('user_id', 'default')
        
        # Set file paths
        user_dir = os.path.join(DATA_DIR, user_id)
        input_file = os.path.join(user_dir, "sent_emails.txt")
        output_file = os.path.join(user_dir, "filtered_voice_emails.txt")
        
        # Check if input file exists
        if not os.path.exists(input_file):
            return jsonify({
                "success": False,
                "message": f"Input file not found: {input_file}. Please run fetch-history first."
            }), 400
        
        # Setup findvoice arguments
        old_argv = sys.argv.copy()
        
        # Configure arguments for findvoice.main()
        sys.argv = [
            'findvoice.py',
            input_file,
            '--output', output_file,
            '--model', data.get('model', 'gpt-4o'),
            '--optimize'  # Enable optimization for better results
        ]
        
        # Add optional parameters if provided
        if data.get('chunk_size'):
            sys.argv.extend(['--chunk-size', str(data.get('chunk_size'))])
        
        if data.get('target_tokens'):
            sys.argv.extend(['--target-tokens', str(data.get('target_tokens'))])
        
        print(f"Running voice analysis with args: {sys.argv}")
        
        # Run the findvoice main function
        result = asyncio.run(findvoice.main())
        
        # Restore original argv
        sys.argv = old_argv
        
        if result != 0:
            return jsonify({
                "success": False,
                "message": f"Voice analysis failed with error code {result}"
            }), 400
        
        return jsonify({
            "success": True, 
            "message": "Voice analysis completed",
            "output_file": output_file
        })
    except Exception as e:
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
        
        # Get the user context if provided
        context = data.get('context', {})
        
        # Set file paths
        user_dir = os.path.join(DATA_DIR, user_id)
        examples_file = os.path.join(user_dir, "filtered_voice_emails.txt")
        
        # Check if examples file exists
        if not os.path.exists(examples_file):
            return jsonify({
                "success": False,
                "message": f"Examples file not found: {examples_file}. Please run analyze-voice first."
            }), 400
        
        # Call the generate function with context - prioritize free-form prompt
        if prompt:
            # Use free-form prompt mode when prompt is provided
            generated_text = generate.generate_matching_text(
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
            generated_text = generate.generate_matching_text(
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
        
        return jsonify({
            "success": True,
            "generated_text": generated_text
        })
    except Exception as e:
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
        
        # Get the user context if provided
        context = data.get('context', {})
        
        if not original_text:
            return jsonify({
                "success": False,
                "message": "Original text is required for refinement."
            }), 400
            
        if not refinement_instructions:
            return jsonify({
                "success": False,
                "message": "Refinement instructions are required."
            }), 400
        
        # Set file paths
        user_dir = os.path.join(DATA_DIR, user_id)
        examples_file = os.path.join(user_dir, "filtered_voice_emails.txt")
        
        # Check if examples file exists
        if not os.path.exists(examples_file):
            return jsonify({
                "success": False,
                "message": f"Examples file not found: {examples_file}. Please run analyze-voice first."
            }), 400
        
        # Read examples
        with open(examples_file, 'r', encoding='utf-8') as f:
            examples = f.read()
        
        # Call the refinement function with context
        refined_text = generate.refine_generated_text(
            examples=examples,
            original_text=original_text,
            refinement_instructions=refinement_instructions,
            model=model,
            max_tokens=2000,
            temperature=0,
            user_context=context  # Pass the user context
        )
        
        return jsonify({
            "success": True,
            "refined_text": refined_text
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

# Move the test functions here, but don't call them immediately

def test_authenticate():
    url = "http://localhost:5000/api/authenticate"
    response = requests.post(url, json={})
    
    print("Authentication Response:")
    print(f"Status Code: {response.status_code}")
    print(json.dumps(response.json(), indent=2))

def test_fetch_history():
    url = "http://localhost:5000/api/fetch-history"
    payload = {
        "user_id": "test_user",
        "after_date": "2019/01/01",
        "before_date": "2022/01/01"
    }
    
    response = requests.post(url, json=payload)
    
    print("Fetch History Response:")
    print(f"Status Code: {response.status_code}")
    print(json.dumps(response.json(), indent=2))

def test_analyze_voice():
    url = "http://localhost:5000/api/analyze-voice"
    payload = {
        "user_id": "test_user"
    }
    
    response = requests.post(url, json=payload)
    
    print("Analyze Voice Response:")
    print(f"Status Code: {response.status_code}")
    print(json.dumps(response.json(), indent=2))

def test_generate_content():
    url = "http://localhost:5000/api/generate-content"
    payload = {
        "user_id": "test_user",
        "prompt": "Write a professional email explaining a project delay",
        "genre": "email",
        "topic": "project update",
        "tone": "professional",
        "recipient": "manager",
        "length": 200
    }
    
    response = requests.post(url, json=payload)
    
    print("Generate Content Response:")
    print(f"Status Code: {response.status_code}")
    print(json.dumps(response.json(), indent=2))

def test_all_endpoints():
    base_url = "http://localhost:5000/api"
    
    # Test 1: Authentication
    print("\n=== Testing Authentication ===")
    auth_response = requests.post(f"{base_url}/authenticate", json={})
    print(f"Status: {auth_response.status_code}")
    print(json.dumps(auth_response.json(), indent=2))
    
    # Proceed only if authentication was successful
    if not auth_response.json().get("success", False):
        print("Authentication failed. Cannot proceed with further tests.")
        return
    
    # Test 2: Fetch History
    print("\n=== Testing Fetch History ===")
    fetch_payload = {
        "user_id": "test_user",
        "after_date": "2019/01/01",
        "before_date": "2022/01/01"
    }
    
    fetch_response = requests.post(f"{base_url}/fetch-history", json=fetch_payload)
    print(f"Status: {fetch_response.status_code}")
    print(json.dumps(fetch_response.json(), indent=2))
    
    # Allow some time for the file to be written
    time.sleep(2)
    
    # Test 3: Analyze Voice
    print("\n=== Testing Analyze Voice ===")
    voice_payload = {
        "user_id": "test_user"
    }
    
    voice_response = requests.post(f"{base_url}/analyze-voice", json=voice_payload)
    print(f"Status: {voice_response.status_code}")
    print(json.dumps(voice_response.json(), indent=2))
    
    # Allow some time for processing
    time.sleep(2)
    
    # Test 4: Generate Content
    print("\n=== Testing Generate Content ===")
    generate_payload = {
        "user_id": "test_user",
        "prompt": "Write a professional email explaining a project delay",
        "genre": "email",
        "topic": "project update",
        "tone": "professional",
        "recipient": "manager",
        "length": 200
    }
    
    generate_response = requests.post(f"{base_url}/generate-content", json=generate_payload)
    print(f"Status: {generate_response.status_code}")
    
    result = generate_response.json()
    
    # Print the generated text separately for better readability
    if "generated_text" in result:
        generated_text = result.pop("generated_text")
        print(json.dumps(result, indent=2))
        print("\nGenerated Text:")
        print("=" * 50)
        print(generated_text)
        print("=" * 50)
    else:
        print(json.dumps(result, indent=2))

if __name__ == "__main__":
    import sys
    
    # Check if we want to run tests or start the server
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("Running tests against Flask server...")
        print("Make sure the server is already running in another terminal!")
        test_all_endpoints()
    else:
        # Get host and port from environment variables with defaults
        host = os.environ.get('HOST', '0.0.0.0')  # Listen on all interfaces by default
        port = int(os.environ.get('PORT', 8080))
        debug = True
        
        print(f"Starting Flask server on {host}:{port} (debug={debug})...")
        app.run(host=host, port=port, debug=debug) 