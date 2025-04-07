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
    """Fetch Gmail history for the authenticated user"""
    try:
        # Get parameters from request
        data = request.json
        user_id = data.get('user_id', 'default')
        after_date = data.get('after_date', '2014/01/01')
        before_date = data.get('before_date', '2022/01/01')
        
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
        
        # For testing purposes, create a sample file...
        # In production, you would use the gmail_history module with the user's credentials
        
        return jsonify({
            "success": True, 
            "message": "Email history fetched successfully",
            "output_file": output_file
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
        
        # Changed: Call main properly, based on how it's defined in findvoice.py
        old_argv = sys.argv.copy()
        sys.argv = [
            'findvoice.py',
            input_file,
            '--output', output_file,
            '--optimize'
        ]
        asyncio.run(findvoice.main())
        sys.argv = old_argv
        
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
        
        # Set file paths
        user_dir = os.path.join(DATA_DIR, user_id)
        examples_file = os.path.join(user_dir, "filtered_voice_emails.txt")
        
        # Check if examples file exists
        if not os.path.exists(examples_file):
            # For testing: Create a dummy examples file with minimal content
            os.makedirs(os.path.dirname(examples_file), exist_ok=True)
            with open(examples_file, 'w') as f:
                f.write("This is a sample email to use for testing.\n\n")
                f.write("I hope this helps with the testing process.\n\n")
                f.write("Let me know if you need anything else.\n\n")
            
            print(f"Created dummy examples file at {examples_file} for testing")
        
        # For testing, we can either call the real generate function or use a mock
        # Here's a simple mock implementation
        mock_response = (
            "Subject: Update on Project Timeline\n\n"
            "I wanted to provide an update regarding the timeline for our current project. Unfortunately, we are experiencing a delay.\n\n"
            "The team has encountered some unforeseen challenges that have impacted our original schedule. We are actively working to address these issues and are committed to minimizing any further delays.\n\n"
            "I hope this helps with understanding the current situation. We are doing everything we can to get back on track as soon as possible.\n\n"
            "Let me know if you have any questions or need further information.\n\n"
            "Thank you for your understanding and support."
        )
        
        # Uncomment this to use the real generate module
        # generated_text = generate.generate_matching_text(
        #     examples_file=examples_file,
        #     free_form_prompt=prompt if prompt else None,
        #     genre=genre,
        #     topic=topic,
        #     tone=tone,
        #     recipient=recipient,
        #     length=length
        # )
        
        # For testing, use the mock response
        generated_text = mock_response
        
        return jsonify({
            "success": True,
            "generated_text": generated_text
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