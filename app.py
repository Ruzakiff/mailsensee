from flask import Flask, request, jsonify
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

@app.route('/api/authenticate', methods=['POST'])
def authenticate():
    """Trigger the OAuth flow and return success status"""
    try:
        credentials = get_credentials()
        return jsonify({"success": True, "message": "Authentication successful"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

@app.route('/api/fetch-history', methods=['POST'])
def fetch_history():
    """Fetch Gmail history for the authenticated user"""
    try:
        # Get parameters from request
        data = request.json
        user_id = data.get('user_id', 'default')
        after_date = data.get('after_date', '2014/01/01')
        before_date = data.get('before_date', '2022/01/01')
        
        # Create user directory
        user_dir = os.path.join(DATA_DIR, user_id)
        os.makedirs(user_dir, exist_ok=True)
        
        # Set output file paths
        output_file = os.path.join(user_dir, "sent_emails.txt")
        progress_file = os.path.join(user_dir, "email_fetch_progress.txt")
        
        # For testing purposes, let's create a sample file with some content
        # This will simulate what gmail_history.main() would do
        # In production, you'd use the real gmail_history module
        with open(output_file, 'w') as f:
            f.write("Email ID: test_id_123\n")
            f.write("Date: Mon, 15 Aug 2022 10:30:45 -0700\n")
            f.write("To: recipient@example.com\n")
            f.write("Subject: Test Email Subject\n")
            f.write("Your Content:\n")
            f.write("This is a test email content created for testing purposes.\n")
            f.write("It simulates what would be fetched from the Gmail API.\n")
            f.write("Feel free to add more content as needed for testing.\n")
            f.write("\n" + "="*80 + "\n\n")
            
            # Add a few more sample emails
            f.write("Email ID: test_id_456\n")
            f.write("Date: Tue, 16 Aug 2022 14:20:10 -0700\n")
            f.write("To: manager@example.com\n")
            f.write("Subject: Project Update\n")
            f.write("Your Content:\n")
            f.write("Here's the latest update on our project:\n\n")
            f.write("We've completed the first phase ahead of schedule.\n")
            f.write("The team has been working efficiently despite some challenges.\n")
            f.write("I'd like to discuss next steps in our meeting tomorrow.\n")
            f.write("\n" + "="*80 + "\n\n")
        
        print(f"Created sample email file at {output_file} for testing")
        
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