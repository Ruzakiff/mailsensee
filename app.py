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
    """Fetch Gmail history for the authenticated user, extracting only content they wrote"""
    try:
        # Get parameters from request
        data = request.json
        user_id = data.get('user_id', 'default')
        after_date = data.get('after_date', '2014/01/01')
        before_date = data.get('before_date', '2022/01/01')
        email_limit = data.get('email_limit', 1000)  # Default limit of 1000 emails
        
        # Get user's credentials
        tokens_dir = os.path.join(DATA_DIR, 'tokens')
        token_path = os.path.join(tokens_dir, f"{user_id}.pickle")
        
        if not os.path.exists(token_path):
            return jsonify({
                "success": False,
                "message": f"User not authenticated. Please authenticate first."
            }), 401
        
        # Load credentials
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)
            
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    with open(token_path, 'wb') as token:
                        pickle.dump(creds, token)
                except:
                    return jsonify({
                        "success": False,
                        "message": "Credentials expired and couldn't be refreshed."
                    }), 401
            else:
                return jsonify({
                    "success": False,
                    "message": "Invalid credentials. Please authenticate again."
                }), 401
        
        # Create user directory
        user_dir = os.path.join(DATA_DIR, user_id)
        os.makedirs(user_dir, exist_ok=True)
        
        # Set output file paths
        output_file = os.path.join(user_dir, "sent_emails.txt")
        progress_file = os.path.join(user_dir, "email_fetch_progress.txt")
        
        # Set up parameters for Gmail query
        client = gmail_history.GmailClient(user_id=user_id)
        query = f"in:sent after:{after_date.replace('/', '/')} before:{before_date.replace('/', '/')}"
        
        print(f"Fetching emails for user {user_id} with query: {query} (limit: {email_limit} emails)")
        
        # Initialize or load progress tracking
        processed_ids = set()
        if os.path.exists(progress_file):
            with open(progress_file, 'r') as f:
                processed_ids = set(line.strip() for line in f if line.strip())
            print(f"Resuming from previous run, {len(processed_ids)} emails already processed.")
        
        # Open the output file in append mode
        with open(output_file, 'a', encoding='utf-8') as out_file:
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
                            with open(progress_file, 'a') as prog:
                                prog.write(f"{msg_id}\n")
                            processed_ids.add(msg_id)
                            continue
                        
                        # Write to file immediately
                        out_file.write(f"Email ID: {msg_id}\n")
                        out_file.write(f"Date: {date}\n")
                        out_file.write(f"To: {to}\n")
                        out_file.write(f"Subject: {subject}\n")
                        out_file.write("Your Content:\n")
                        out_file.write(your_content)
                        out_file.write("\n" + "="*80 + "\n\n")
                        
                        # Flush to ensure it's written to disk
                        out_file.flush()
                        
                        # Mark as processed
                        with open(progress_file, 'a') as prog:
                            prog.write(f"{msg_id}\n")
                        
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
        
        # Add stats about the extraction
        with open(os.path.join(user_dir, "email_extraction_stats.txt"), 'w') as stats_file:
            stats_file.write(f"Total emails fetched: {total_fetched}\n")
            stats_file.write(f"Emails with user content extracted: {actual_processed}\n")
            stats_file.write(f"Extraction date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            stats_file.write(f"Limit reached: {limit_reached}\n")
            stats_file.write(f"Email limit: {email_limit}\n")
        
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
        
        # Set file paths
        user_dir = os.path.join(DATA_DIR, user_id)
        examples_file = os.path.join(user_dir, "filtered_voice_emails.txt")
        
        # Check if examples file exists
        if not os.path.exists(examples_file):
            return jsonify({
                "success": False,
                "message": f"Examples file not found: {examples_file}. Please run analyze-voice first."
            }), 400
        
        # Call the generate function - prioritize free-form prompt
        if prompt:
            # Use free-form prompt mode when prompt is provided
            generated_text = generate.generate_matching_text(
                examples_file=examples_file,
                model=model,
                max_tokens=2000,
                length=length,
                free_form_prompt=prompt,
                temperature=0  # Low temperature for more predictable results
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
                length=length
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
        
        # Call the refinement function
        refined_text = generate.refine_generated_text(
            examples=examples,
            original_text=original_text,
            refinement_instructions=refinement_instructions,
            model=model,
            max_tokens=2000,
            temperature=0
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
        print("Starting Flask server...")
        app.run(debug=True, port=5000) 