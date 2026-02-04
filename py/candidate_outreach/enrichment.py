from playwright.sync_api import sync_playwright
import time

def get_linkedin_profile_data(linkedin_url, headless=False):
    """
    Visits a LinkedIn profile and extracts the full text content.
    Returns a dictionary with 'raw_text'.
    """
    data = {
        'raw_text': ''
    }
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
             user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print(f"Visiting {linkedin_url}...")
        try:
            page.goto(linkedin_url)
            
            # Check for login redirection
            if "authware" in page.url or "login" in page.url or "signup" in page.url:
                print("Please log in to LinkedIn in the browser window...")
                try:
                    page.wait_for_url("**/in/**", timeout=60000)
                except:
                    print("Login timeout or failed to redirect to profile.")
                    pass # Try to capture what we have anyway
                    
            page.wait_for_load_state("domcontentloaded")
            # Wait a bit for dynamic content
            time.sleep(2)
            
            # Extract full visible text
            # We use document.body.innerText to get a reasonable representation of the page content
            # This is "dirty" but Gemini is good at parsing it.
            data['raw_text'] = page.evaluate("document.body.innerText")
            
        except Exception as e:
            print(f"Error scraping profile: {e}")
            
        finally:
            browser.close()
            
    return data

def enrich_candidate(candidate):
    """
    Enriches candidate dictionary with LinkedIn data.
    """
    url = candidate.get('linkedin_url')
    if url:
        profile_data = get_linkedin_profile_data(url)
        candidate['profile_text'] = profile_data.get('raw_text', '')
             
    return candidate
