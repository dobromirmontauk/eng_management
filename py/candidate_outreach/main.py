import argparse
import sys
import os
from .sheets import get_candidates_from_sheet
from .enrichment import enrich_candidate
from .email_builder import render_email_gemini
from .gmail import create_draft

def main():
    parser = argparse.ArgumentParser(description='Candidate Outreach Automation Tool')
    parser.add_argument('--sheet-id', required=True, help='Google Spreadsheet ID')
    parser.add_argument('--range', default='Sheet1!A:C', help='Sheet range to read (default: Sheet1!A:C)')
    parser.add_argument('--template-file', required=True, help='Path to the email template file')
    parser.add_argument('--gemini-key', required=False, help='Google Gemini API Key')
    parser.add_argument('--headless', action='store_true', help='Run browser in headless mode')
    
    args = parser.parse_args()
    
    # Check for API Key in args or env
    gemini_key = args.gemini_key or os.environ.get('GEMINI_API_KEY')
    if not gemini_key:
        print("Error: Gemini API Key is required. Set GEMINI_API_KEY env var or use --gemini-key.")
        sys.exit(1)
    
    # 1. Read Template
    try:
        with open(args.template_file, 'r') as f:
            template_content = f.read()
    except FileNotFoundError:
        print(f"Error: Template file not found at {args.template_file}")
        sys.exit(1)

    # 2. Fetch Candidates
    print(f"Fetching candidates from Sheet {args.sheet_id}...")
    try:
        candidates = get_candidates_from_sheet(args.sheet_id, args.range)
    except Exception as e:
        print(f"Error fetching from Sheets: {e}")
        # Hint for credentials
        print("Ensure 'credentials.json' is in the current directory and you have authenticated.")
        sys.exit(1)
        
    print(f"Found {len(candidates)} candidates.")

    # 3. Process Each Candidate
    for candidate in candidates:
        print(f"\nProcessing {candidate.get('name')} ({candidate.get('email')})...")
        
        # Enrich
        try:
            print("  Enriching data from LinkedIn (Full Page)...")
            candidate = enrich_candidate(candidate)
        except Exception as e:
            print(f"  Warning: Enrichment failed for {candidate.get('name')}: {e}")
            
        # Build Email with Gemini
        print("  Generating email with Gemini...")
        subject, body = render_email_gemini(template_content, candidate, gemini_key)
        
        # Create Draft
        try:
             create_draft(candidate.get('email'), subject, body)
             print(f"  Draft created for {candidate.get('name')}.")
        except Exception as e:
             print(f"  Error creating draft: {e}")

    print("\nDone!")

if __name__ == '__main__':
    main()
