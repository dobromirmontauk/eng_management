from google import genai

def render_email_gemini(template_str, candidate_data, api_key):
    """
    Generates an email using Google Gemini based on the template and candidate profile text.
    """
    if not api_key:
        raise ValueError("Gemini API Key is required for email generation.")
        
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
You are a professional recruiter drafting an outreach email.

**Candidate Information:**
Name: {candidate_data.get('name')}
Email: {candidate_data.get('email')}
LinkedIn Profile Text (Unstructured):
\"\"\"
{candidate_data.get('profile_text', 'No profile data found.')}
\"\"\"

**Email Template:**
\"\"\"
{template_str}
\"\"\"

**Instructions:**
1. Analyze the LinkedIn profile text to identify the candidate's last 3 jobs and their university/college (if mentioned).
2. Fill out the email template.
3. Personalize the email based on their experience.
4. **Output strictly the JSON format below with no markdown formatting**:
{{
  "subject": "The email subject line",
  "body": "The email body text"
}}
"""
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash', 
            contents=prompt
        )
        
        # Attempt to parse JSON response. 
        # Gemini might wrap in ```json ... ```
        content = response.text.replace('```json', '').replace('```', '').strip()
        
        import json
        result = json.loads(content)
        return result['subject'], result['body']
        
    except Exception as e:
        print(f"Error generating email with Gemini: {e}")
        # print(f"Raw response might have been: {response.text if 'response' in locals() else 'N/A'}")
        return "Error Generating Email", f"Failed to generate email. Error: {e}"
