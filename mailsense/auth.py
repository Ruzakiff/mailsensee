import os
import json
import pickle
import webbrowser
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# If modifying these scopes, delete the token.pickle file
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_credentials():
    """Get valid user credentials from storage or through OAuth flow."""
    creds = None
    # The token.pickle file stores the user's access and refresh tokens
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open('token.pickle', 'wb') as token:
                    pickle.dump(creds, token)
                print("Using refreshed credentials")
            except Exception as e:
                print(f"Could not refresh token: {e}")
                creds = None
        
        if not creds or not creds.valid:
            # Direct manual authentication approach
            try:
                # First, get the client secrets file
                import glob
                client_secret_files = glob.glob("client_secret*.json")
                if not client_secret_files:
                    raise FileNotFoundError("No client_secret*.json file found")
                
                client_secrets_file = client_secret_files[0]
                print(f"Using credentials file: {client_secrets_file}")
                
                # Create the flow with manual redirect
                flow = InstalledAppFlow.from_client_secrets_file(
                    client_secrets_file, SCOPES)
                flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
                
                # Generate the authorization URL
                auth_url, _ = flow.authorization_url(
                    access_type='offline',
                    prompt='consent'
                )
                
                print("\nGo to this URL in your browser:")
                print(auth_url)
                print("\nAfter you approve, you'll get a code. Copy that code and paste it below.")
                
                # Get the authorization code from the user
                code = input("\nEnter the authorization code: ")
                
                # Exchange the code for credentials
                flow.fetch_token(code=code)
                creds = flow.credentials
                
                # Save the credentials for future runs
                with open('token.pickle', 'wb') as token:
                    pickle.dump(creds, token)
                
            except Exception as e:
                print(f"\nAuthentication error: {str(e)}")
                print("\nGetting an 'invalid_grant' error? Try these steps:")
                print("1. Make sure you're copy-pasting the ENTIRE code")
                print("2. Try using a different browser")
                print("3. Check that you've added your email as a test user in Google Cloud Console")
                raise Exception("Authentication failed. See above for troubleshooting steps.")
    
    return creds

def main():
    """Run the OAuth flow and print success message."""
    print("Starting Gmail authentication process...")
    
    try:
        creds = get_credentials()
        print("\nAuthentication successful! You now have access to your Gmail data.")
        return 0
    except Exception as e:
        print(f"\nAuthentication failed: {str(e)}")
        return 1

if __name__ == '__main__':
    main() 