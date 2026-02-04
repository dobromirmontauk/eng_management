from googleapiclient.discovery import build
from .auth import get_credentials

def get_candidates_from_sheet(spreadsheet_id, range_name):
    """
    Fetches candidate data from a Google Sheet.
    Assumes columns are: Name, Email, LinkedIn URL
    Returns a list of dictionaries.
    """
    creds = get_credentials()
    service = build('sheets', 'v4', credentials=creds)

    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=spreadsheet_id,
                                range=range_name).execute()
    values = result.get('values', [])

    candidates = []
    
    if not values:
        print('No data found.')
        return candidates

    # Assume first row is header. 
    # For simplicity, let's map by index if headers match expectations, 
    # or just assume column order: Name, Email, LinkedIn
    
    # headers = values[0] 
    # To make it robust, let's look for "Name", "Email", "LinkedIn" in headers
    
    # Simple implementation: expect specific order
    # Row format: [Name, Email, LinkedIn URL, ...]
    
    for row in values[1:]: # Skip header
        if len(row) < 3:
            continue
            
        name = row[0]
        email = row[1]
        linkedin_url = row[2]
        
        candidates.append({
            'name': name,
            'email': email,
            'linkedin_url': linkedin_url
        })
        
    return candidates
