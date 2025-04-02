from googleapiclient.discovery import build
from .auth import get_credentials

class GmailClient:
    """Client to interact with Gmail API."""
    
    def __init__(self):
        """Initialize the Gmail API client."""
        creds = get_credentials()
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