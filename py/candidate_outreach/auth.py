import os.path
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# If modifying these scopes, delete the file token.json.
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/gmail.compose'
]

def get_credentials(credentials_path='credentials.json', token_path='token.json'):
    """Shows basic usage of the Gmail API.
    Lists the user's Gmail labels.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_path):
                print(f"\n[!] Credentials file not found at '{credentials_path}'.")
                print("Go to Google Cloud Console -> APIs & Services -> Credentials.")
                print("Create 'OAuth client ID' (Application type: Desktop app).")
                print("Download the JSON file, OR verify it's in this directory.")
                print("\nAlternatively, open the JSON file in a text editor, copy the content, and paste it below.")
                
                try:
                    # Use input() to read from stdin (user interaction)
                    json_content = input("Paste your credentials JSON here: ").strip()
                    if not json_content:
                        raise ValueError("Empty input")
                        
                    # Validate JSON
                    json.loads(json_content)
                    
                    # Save it
                    with open(credentials_path, 'w') as f:
                        f.write(json_content)
                    print(f"Saved credentials to {credentials_path}.")
                    
                except Exception as e:
                     raise FileNotFoundError(f"Missing {credentials_path} and failed to read input: {e}")
                
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
            
        # Save the credentials for the next run
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
            
    return creds
