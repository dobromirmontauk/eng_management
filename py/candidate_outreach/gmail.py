import base64
from email.message import EmailMessage
from googleapiclient.discovery import build
from .auth import get_credentials

def create_draft(candidate_email, subject, body):
    """
    Creates a draft email in the user's Gmail account.
    """
    creds = get_credentials()
    service = build('gmail', 'v1', credentials=creds)
    
    message = EmailMessage()
    message.set_content(body)
    message['To'] = candidate_email
    message['Subject'] = subject
    
    # Encode the message
    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    
    create_message = {
        'message': {
            'raw': encoded_message
        }
    }
    
    draft = service.users().drafts().create(userId='me', body=create_message).execute()
    print(f'Draft id: {draft["id"]} created for {candidate_email}')
    return draft
