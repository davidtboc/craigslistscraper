import os
import agentql
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import datetime
import openai
import json
import time
import gspread
from google.oauth2.service_account import Credentials
import pytz
from dateutil import parser
import re
from urllib.parse import urljoin, urlparse
from collections import defaultdict

# --------------------------------------------------------------
# 1. SETUP: Load environment variables and configure APIs
# --------------------------------------------------------------
print("Loading environment variables...")
load_dotenv()

os.environ["AGENTQL_API_KEY"] = os.getenv('AGENTQL_API_KEY')
PERPLEXITY_API_KEY = os.getenv('PERPLEXITY_API_KEY')
GOOGLE_SHEET_ID = "1Fc0JO91CAvciNYi5LMMUO9K8J_7yzYlp1LUFyOs6PqA"
GOOGLE_SHEETS_CREDS_FILE = os.getenv('GOOGLE_SHEETS_CREDS_FILE', 'credentials.json')

if not all([os.environ["AGENTQL_API_KEY"], PERPLEXITY_API_KEY]):
    raise ValueError("One or more environment variables are missing. Please check your .env file.")

client = openai.OpenAI(
    api_key=PERPLEXITY_API_KEY,
    base_url="https://api.perplexity.ai"
)
print("Configuration complete. Using Perplexity API.")

# --------------------------------------------------------------
# 2. GOOGLE SHEETS FUNCTIONS
# --------------------------------------------------------------
def setup_google_sheets():
    """Sets up connection to Google Sheets."""
    print("Setting up Google Sheets connection...")
    
    if not os.path.exists(GOOGLE_SHEETS_CREDS_FILE):
        raise FileNotFoundError(f"Credentials file not found: {GOOGLE_SHEETS_CREDS_FILE}")

    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]

    try:
        creds = Credentials.from_service_account_file(GOOGLE_SHEETS_CREDS_FILE, scopes=scopes)
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(GOOGLE_SHEET_ID)
        worksheet = spreadsheet.sheet1
        print(f"✅ Connected to Google Sheet: {spreadsheet.title}")
        
        headers = worksheet.row_values(1)
        print(f"✅ Headers: {headers[:5]}...")
        
        return worksheet
        
    except Exception as e:
        print(f"❌ Error setting up Google Sheets: {e}")
        raise

def get_todays_outreach_links(worksheet):
    """
    Retrieves URLs from Column K for rows where Column C matches today's date.
    
    Args:
        worksheet: The Google Sheets worksheet object
        
    Returns:
        List of tuples: (row_number, url, date_added)
    """
    print("\n📋 Fetching today's outreach links from Google Sheet...")
    
    try:
        # Get today's date in MM/DD format to match the sheet
        today = datetime.date.today()
        today_str = today.strftime("%m/%d")
        print(f"  Looking for date: {today_str}")
        
        # Get all values from Column C (Date Source Added) and Column K (Outreach Link)
        date_column = worksheet.col_values(3)  # Column C
        url_column = worksheet.col_values(11)  # Column K
        
        # Find matching rows
        todays_links = []
        for row_num in range(1, len(date_column)):  # Start from index 1 (row 2, skip header)
            # Check if we've reached empty cells
            if row_num >= len(date_column) or not date_column[row_num]:
                print(f"  ⏹️  Reached empty cell at row {row_num + 1}, stopping")
                break
            
            date_value = date_column[row_num].strip()
            
            # Check if date matches today
            if date_value == today_str:
                # Get corresponding URL from column K
                if row_num < len(url_column) and url_column[row_num]:
                    url = url_column[row_num].strip()
                    actual_row = row_num + 1  # +1 because sheet rows are 1-indexed
                    todays_links.append((actual_row, url, date_value))
                    print(f"  ✅ Row {actual_row}: Found today's date with URL")
        
        print(f"\n✅ Found {len(todays_links)} links from today ({today_str})")
        return todays_links
        
    except Exception as e:
        print(f"❌ Error fetching today's outreach links: {e}")
        return []

# --------------------------------------------------------------
# 3. AGENTQL QUERIES
# --------------------------------------------------------------
GET_REPLY_BUTTON_QUERY = """
{
    reply_button(xpath="/html/body/section/section/header/div[2]/div/button")
}
"""

GET_DROPDOWN_QUERY = """
{
    dropdown_button(xpath="//*[@id='18c5c2599924f239d35d200ba0c4cf102c40396d']/div/button")
}
"""

GET_COPY_BUTTON_QUERY = """
{
    copy_button
}
"""

# --------------------------------------------------------------
# 4. URL PROCESSING FUNCTIONS
# --------------------------------------------------------------
def extract_email_from_page(page):
    """
    Extracts email by clicking reply button, dropdown, and copy button.
    
    Args:
        page: AgentQL wrapped Playwright page
        
    Returns:
        Email address or None
    """
    try:
        print("  📧 Attempting to extract email...")
        
        # Step 1: Click the reply button
        print("  ⏳ Step 1: Clicking reply button...")
        try:
            reply_response = page.query_elements(GET_REPLY_BUTTON_QUERY)
            if reply_response.reply_button:
                reply_response.reply_button.click()
                print("  ✅ Clicked reply button")
                time.sleep(2)  # Wait for modal/dropdown to load
            else:
                print("  ⚠️  Reply button not found")
                return None
        except Exception as e:
            print(f"  ⚠️  Could not click reply button: {e}")
            return None
        
        # Step 2: Click the dropdown
        print("  ⏳ Step 2: Clicking dropdown...")
        try:
            dropdown_response = page.query_elements(GET_DROPDOWN_QUERY)
            if dropdown_response.dropdown_button:
                dropdown_response.dropdown_button.click()
                print("  ✅ Clicked dropdown")
                time.sleep(1)  # Wait for dropdown options to appear
            else:
                print("  ⚠️  Dropdown not found")
                return None
        except Exception as e:
            print(f"  ⚠️  Could not click dropdown: {e}")
            return None
        
        # Step 3: Click copy button and get email
        print("  ⏳ Step 3: Clicking copy button...")
        try:
            copy_response = page.query_elements(GET_COPY_BUTTON_QUERY)
            if copy_response.copy_button:
                copy_response.copy_button.click()
                print("  ✅ Clicked copy button")
                time.sleep(0.5)
                
                # Try to get email from clipboard or page content
                page_content = page.content()
                
                # Look for email patterns
                email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
                emails = re.findall(email_pattern, page_content)
                
                # Filter out common non-real emails
                filtered_emails = [email for email in emails 
                                 if not any(domain in email.lower() 
                                 for domain in ['noreply', 'no-reply', 'donotreply', 'example.com'])]
                
                if filtered_emails:
                    email = filtered_emails[0]
                    print(f"  ✅ Extracted email: {email}")
                    return email
                else:
                    print("  ⚠️  No email found after clicking copy")
                    return None
            else:
                print("  ⚠️  Copy button not found")
                return None
        except Exception as e:
            print(f"  ⚠️  Could not click copy button: {e}")
            return None
            
    except Exception as e:
        print(f"  ❌ Error extracting email: {e}")
        return None

def process_url(url, row_number, browser, page):
    """
    Processes a single URL - visits it and extracts information.
    
    Args:
        url: The URL to process
        row_number: The row number in the Google Sheet
        browser: Playwright browser instance (reused)
        page: Playwright page instance (reused)
        
    Returns:
        Dictionary with extracted data
    """
    print(f"\n{'─'*70}")
    print(f"Processing Row {row_number}: {url[:60]}...")
    print(f"{'─'*70}")
    
    try:
        # Navigate to URL
        page.goto(url, wait_until="domcontentloaded")
        time.sleep(3)  # Wait for page to load
        
        # Get page content
        page_title = page.title()
        print(f"  ✅ Successfully visited: {page_title}")
        
        # Extract email using the reply button workflow
        email = extract_email_from_page(page)
        
        result = {
            "row_number": row_number,
            "url": url,
            "status": "visited",
            "page_title": page_title,
            "email": email
        }
        
        return result
        
    except Exception as e:
        print(f"  ❌ Error processing URL: {e}")
        return {
            "row_number": row_number,
            "url": url,
            "status": "error",
            "error": str(e),
            "email": None
        }

# --------------------------------------------------------------
# 5. MAIN PROCESSING SCRIPT
# --------------------------------------------------------------
def run_outreach_processor(test_mode=True, max_links=3, timeout_seconds=20):
    """
    Main function to process outreach links.
    
    Args:
        test_mode: If True, limits processing to first few links
        max_links: Maximum number of links to process in test mode
        timeout_seconds: Maximum runtime in seconds
    """
    print(f"\n{'='*70}")
    print(f"STARTING OUTREACH PROCESSOR - {datetime.datetime.now()}")
    if test_mode:
        print(f"⚠️  TEST MODE: Will process max {max_links} links or timeout after {timeout_seconds}s")
    print(f"{'='*70}")
    
    start_time = time.time()
    
    # Setup Google Sheets
    try:
        worksheet = setup_google_sheets()
    except Exception as e:
        print(f"❌ FAILURE: Could not connect to Google Sheets: {e}")
        return False
    
    # Check timeout
    if time.time() - start_time > timeout_seconds:
        print(f"⏱️  Timeout reached after {timeout_seconds}s")
        return True
    
    # Get today's outreach links
    todays_links = get_todays_outreach_links(worksheet)
    
    if not todays_links:
        print("⚠️  No outreach links found for today")
        return False
    
    # Limit links in test mode
    if test_mode:
        todays_links = todays_links[:max_links]
        print(f"🧪 Processing only first {len(todays_links)} links (test mode)")
    
    # Start browser once and reuse it
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        page = agentql.wrap(browser.new_page())
        
        results = []
        
        # Process each URL
        for row_num, url, date_added in todays_links:
            # Check timeout
            if time.time() - start_time > timeout_seconds:
                print(f"\n⏱️  Timeout reached after {timeout_seconds}s")
                break
            
            result = process_url(url, row_num, browser, page)
            results.append(result)
            
            # Small delay between requests
            time.sleep(2)
        
        print("\nKeeping browser open for 5 seconds...")
        time.sleep(5)
        browser.close()
    
    elapsed_time = time.time() - start_time
    
    # Summary
    print(f"\n{'='*70}")
    print(f"PROCESSING COMPLETE")
    print(f"{'='*70}")
    print(f"✅ Total URLs processed: {len(results)}")
    successful = sum(1 for r in results if r.get('status') == 'visited')
    failed = sum(1 for r in results if r.get('status') == 'error')
    print(f"✅ Successful: {successful}")
    print(f"❌ Failed: {failed}")
    print(f"⏱️  Time elapsed: {elapsed_time:.2f}s")
    print(f"{'='*70}\n")
    
    return True

def main():
    """Main function."""
    import sys
    
    # Toggle test mode here:
    # test_mode=True: Process only 3 links, timeout after 20s
    # test_mode=False: Process all links, no timeout
    success = run_outreach_processor(test_mode=True, max_links=3, timeout_seconds=20)
    
    if not success:
        print("\n❌ PROCESSOR FAILED")
        sys.exit(1)
    else:
        print("\n✅ PROCESSOR SUCCEEDED")
        sys.exit(0)

if __name__ == "__main__":
    main()