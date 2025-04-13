from googleapiclient.discovery import build
from .auth import get_credentials
import os
import pickle
from google.auth.transport.requests import Request
from .storage import read_pickle, file_exists, write_pickle

def get_user_credentials(user_id='default'):
    """Get credentials for a specific user."""
    # First try with the known filename
    token_file = "gmail_credentials.pickle"  # This is the filename used in the OAuth flow
    
    if file_exists(user_id, token_file):
        try:
            creds = read_pickle(user_id, token_file)
            
            if not creds.valid:
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    write_pickle(user_id, token_file, creds)
                else:
                    raise Exception(f"Invalid credentials for user {user_id}")
            return creds
        except Exception as e:
            raise Exception(f"Error loading credentials for {user_id}: {str(e)}")
    
    # Try alternate filenames as fallbacks
    alt_token_files = ["gmail_token.pickle", "token.pickle"]
    for alt_file in alt_token_files:
        if file_exists(user_id, alt_file):
            try:
                creds = read_pickle(user_id, alt_file)
                
                if not creds.valid:
                    if creds.expired and creds.refresh_token:
                        creds.refresh(Request())
                        write_pickle(user_id, alt_file, creds)
                    else:
                        continue  # Try next file
                return creds
            except Exception:
                continue  # Try next file
    
    # Fallback to local files - configurable for Docker environments
    data_dir = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "user_data"))
    tokens_dir = os.path.join(data_dir, 'tokens')
    os.makedirs(tokens_dir, exist_ok=True)
    token_path = os.path.join(tokens_dir, f"{user_id}.pickle")
    
    if not os.path.exists(token_path):
        raise Exception(f"No credentials found for user {user_id}")
    
    try:
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)
        
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(token_path, 'wb') as token:
                    pickle.dump(creds, token)
            else:
                raise Exception(f"Invalid credentials for user {user_id}")
    except Exception as e:
        raise Exception(f"Error loading credentials for {user_id}: {str(e)}")
    
    return creds

class GmailClient:
    """Client to interact with Gmail API."""
    
    def __init__(self, user_id='default'):
        """Initialize the Gmail API client."""
        self.user_id = user_id
        creds = get_user_credentials(user_id)
        self.service = build('gmail', 'v1', credentials=creds)
    
    def get_emails(self, label="SENT", max_results=10):
        """Get emails with the specified label.
        
        Args:
            label: Label to search for (default: SENT)
            max_results: Maximum number of results to return
            
        Returns:
            List of emails
        """
        results = self.service.users().messages().list(
            userId='me', 
            labelIds=[label], 
            maxResults=max_results
        ).execute()
        
        messages = results.get('messages', [])
        
        emails = []
        for message in messages:
            msg = self.service.users().messages().get(
                userId='me', id=message['id'], format='full'
            ).execute()
            
            # Extract email details
            headers = msg['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
            to = next((h['value'] for h in headers if h['name'] == 'To'), 'Unknown')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
            
            # Extract body
            body = ""
            if 'parts' in msg['payload']:
                for part in msg['payload']['parts']:
                    if part['mimeType'] == 'text/plain':
                        body = part['body'].get('data', '')
                        break
            elif 'body' in msg['payload']:
                body = msg['payload']['body'].get('data', '')
            
            # Create email object
            email = {
                'id': message['id'],
                'subject': subject,
                'from': sender,
                'to': to,
                'date': date,
                'body': body
            }
            
            emails.append(email)
        
        return emails

def list_sent_emails():
    """List sent emails as a command-line utility."""
    client = GmailClient()
    emails = client.get_emails(label="SENT", max_results=10)
    
    for email in emails:
        print(f"Subject: {email['subject']}")
        print(f"To: {email['to']}")
        print(f"Date: {email['date']}")
        print("-" * 40) 