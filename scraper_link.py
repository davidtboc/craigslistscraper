import os
import agentql
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import datetime
import time
import gspread
from google.oauth2.service_account import Credentials
import re
import sys

# --------------------------------------------------------------
# 1. SETUP: Load environment variables and configure APIs
# --------------------------------------------------------------
print("Loading environment variables...")
load_dotenv()

os.environ["AGENTQL_API_KEY"] = os.getenv('AGENTQL_API_KEY')
GOOGLE_SHEET_ID = "1Fc0JO91CAvciNYi5LMMUO9K8J_7yzYlp1LUFyOs6PqA"
GOOGLE_SHEETS_CREDS_FILE = os.getenv('GOOGLE_SHEETS_CREDS_FILE', 'credentials.json')

if not os.environ.get("AGENTQL_API_KEY"):
    raise ValueError("AGENTQL_API_KEY is missing. Please check your .env file.")

# Proxy configuration
PROXY_ENABLED = os.getenv('PROXY_ENABLED', 'false').lower() == 'true'
PROXY_SERVER = os.getenv('PROXY_SERVER')
PROXY_USERNAME = os.getenv('PROXY_USERNAME')
PROXY_PASSWORD = os.getenv('PROXY_PASSWORD')

if PROXY_ENABLED:
    if not all([PROXY_SERVER, PROXY_USERNAME, PROXY_PASSWORD]):
        raise ValueError("Proxy is enabled but credentials are incomplete. Check PROXY_SERVER, PROXY_USERNAME, and PROXY_PASSWORD in .env file.")
    print("✅ Proxy configuration loaded")
    print(f"   Proxy Server: {PROXY_SERVER}")
else:
    print("ℹ️  Proxy disabled - using direct connection")

print("✅ Configuration complete.")

# --------------------------------------------------------------
# 2. VALIDATION FUNCTIONS
# --------------------------------------------------------------
def validate_email(email):
    """Validates if a string is a properly formatted email address."""
    if not email or not isinstance(email, str):
        return False
    
    email_pattern = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$'
    
    if not re.match(email_pattern, email):
        return False
    
    invalid_domains = ['noreply', 'no-reply', 'donotreply', 'example.com', 'test.com']
    if any(domain in email.lower() for domain in invalid_domains):
        return False
    
    return True


def validate_phone(phone):
    """Validates if a string is a properly formatted US phone number."""
    if not phone or not isinstance(phone, str):
        return False
    
    digits_only = re.sub(r'\D', '', phone)
    
    if len(digits_only) not in [10, 11]:
        return False
    
    if len(digits_only) == 11 and digits_only[0] != '1':
        return False
    
    return True


def format_phone(phone):
    """Formats a phone number to standard (XXX) XXX-XXXX format."""
    if not phone:
        return None
    
    digits = re.sub(r'\D', '', phone)
    
    if len(digits) == 11 and digits[0] == '1':
        digits = digits[1:]
    
    if len(digits) == 10:
        return f"({digits[0:3]}) {digits[3:6]}-{digits[6:10]}"
    
    return phone


# --------------------------------------------------------------
# 2B. PROXY VERIFICATION FUNCTION
# --------------------------------------------------------------
def test_proxy_connection(page):
    """
    Tests the proxy connection by checking the current IP address.
    
    Args:
        page: Playwright page instance
        
    Returns:
        dict: Contains success status, IP address, and any error messages
    """
    print("\n" + "─"*70)
    print("🔍 TESTING PROXY CONNECTION")
    print("─"*70)
    
    try:
        print("📡 Checking current IP address...")
        
        # Navigate to ipify API
        page.goto("https://api.ipify.org?format=text", wait_until="domcontentloaded")
        time.sleep(2)
        
        # Get the page content (IP address as plain text)
        ip_address = page.content()
        
        # Extract IP from HTML if wrapped in tags
        if "<" in ip_address:
            match = re.search(r'<body[^>]*>(.*?)</body>', ip_address, re.DOTALL)
            if match:
                ip_address = match.group(1).strip()
        
        ip_address = ip_address.strip()
        
        # Validate IP format
        if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip_address):
            print("✅ IP Address Retrieved Successfully")
            print(f"   Current IP: {ip_address}")
            
            if PROXY_ENABLED:
                print(f"   🔒 Using Proxy: YES")
                print(f"   📍 This is your PROXY IP (residential)")
                print(f"   ℹ️  Craigslist will see this IP, not your real IP")
            else:
                print(f"   🔓 Using Proxy: NO")
                print(f"   📍 This is your REAL IP (direct connection)")
                print(f"   ⚠️  Craigslist will see your actual IP address")
            
            print("─"*70)
            
            return {
                "success": True,
                "ip_address": ip_address,
                "proxy_active": PROXY_ENABLED
            }
        else:
            print(f"⚠️  Retrieved value doesn't look like an IP: {ip_address}")
            print("─"*70)
            return {
                "success": False,
                "error": "Invalid IP format",
                "raw_response": ip_address
            }
            
    except Exception as e:
        print(f"❌ Error checking IP address: {e}")
        print("─"*70)
        
        return {
            "success": False,
            "error": str(e)
        }


# --------------------------------------------------------------
# 3. GOOGLE SHEETS FUNCTIONS
# --------------------------------------------------------------
def setup_google_sheets():
    """Sets up connection to Google Sheets and returns worksheet object."""
    print("\n" + "="*70)
    print("🔗 CONNECTING TO GOOGLE SHEETS")
    print("="*70)
    
    if not os.path.exists(GOOGLE_SHEETS_CREDS_FILE):
        raise FileNotFoundError(f"❌ Credentials file not found: {GOOGLE_SHEETS_CREDS_FILE}")

    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]

    try:
        print(f"📂 Loading credentials from: {GOOGLE_SHEETS_CREDS_FILE}")
        creds = Credentials.from_service_account_file(GOOGLE_SHEETS_CREDS_FILE, scopes=scopes)
        
        print("🔐 Authorizing with Google...")
        gc = gspread.authorize(creds)
        
        print(f"📊 Opening spreadsheet: {GOOGLE_SHEET_ID}")
        spreadsheet = gc.open_by_key(GOOGLE_SHEET_ID)
        worksheet = spreadsheet.sheet1
        
        print("\n" + "="*70)
        print("✅ CONNECTION SUCCESSFUL!")
        print("="*70)
        print(f"📋 Spreadsheet: {spreadsheet.title}")
        print(f"📄 Worksheet: {worksheet.title}")
        
        headers = worksheet.row_values(1)
        print(f"\n📌 Key Columns:")
        print(f"   Column C (3):  Date Source Added")
        print(f"   Column K (11): Outreach Link")
        print(f"   Column L (12): Email (output)")
        print(f"   Column M (13): Phone (output)")
        print("="*70 + "\n")
        
        return worksheet
        
    except Exception as e:
        print("\n" + "="*70)
        print("❌ CONNECTION FAILED!")
        print("="*70)
        print(f"Error: {e}")
        print("="*70 + "\n")
        raise


def get_todays_outreach_links(worksheet):
    """Retrieves URLs from Column K for rows where Column C matches today's date."""
    print("\n📋 Fetching today's outreach links from Google Sheet...")
    
    try:
        today = datetime.date.today()
        today_str = today.strftime("%m/%d")
        print(f"  🔍 Looking for date: {today_str}")
        
        date_column = worksheet.col_values(3)
        url_column = worksheet.col_values(11)
        
        todays_links = []
        for row_num in range(1, len(date_column)):
            if row_num >= len(date_column) or not date_column[row_num]:
                print(f"  ⏹️  Reached empty cell at row {row_num + 1}, stopping")
                break
            
            date_value = date_column[row_num].strip()
            
            if date_value == today_str:
                if row_num < len(url_column) and url_column[row_num]:
                    url = url_column[row_num].strip()
                    actual_row = row_num + 1
                    todays_links.append((actual_row, url, date_value))
                    print(f"  ✅ Row {actual_row}: Found URL")
        
        print(f"\n✅ Found {len(todays_links)} links from today ({today_str})")
        return todays_links
        
    except Exception as e:
        print(f"❌ Error fetching today's outreach links: {e}")
        return []


def check_if_contact_exists(worksheet, row_number):
    """Checks if contact info already exists in Column L (email) for the given row."""
    try:
        email_column = 12
        cell_value = worksheet.cell(row_number, email_column).value
        
        if cell_value and cell_value.strip():
            if '@' in cell_value:
                print(f"  ⏭️  Row {row_number} already has email: {cell_value}")
                return True
        
        return False
        
    except Exception as e:
        print(f"  ⚠️  Error checking existing contact for row {row_number}: {e}")
        return False


def update_contact_in_sheet(worksheet, row_number, email=None, phone=None):
    """Updates contact information in Google Sheets for a specific row."""
    success = False
    
    try:
        email_column = 12
        phone_column = 13
        
        if email and validate_email(email):
            worksheet.update_cell(row_number, email_column, email)
            print(f"  ✅ Updated Row {row_number}, Column L (Email): {email}")
            success = True
        else:
            status_msg = "No email found"
            worksheet.update_cell(row_number, email_column, status_msg)
            print(f"  ⚠️  Updated Row {row_number}, Column L: {status_msg}")
        
        if phone and validate_phone(phone):
            formatted_phone = format_phone(phone)
            worksheet.update_cell(row_number, phone_column, formatted_phone)
            print(f"  ✅ Updated Row {row_number}, Column M (Phone): {formatted_phone}")
            success = True
        else:
            status_msg = "No phone found"
            worksheet.update_cell(row_number, phone_column, status_msg)
            print(f"  ⚠️  Updated Row {row_number}, Column M: {status_msg}")
        
        time.sleep(0.5)
        
        return success
        
    except Exception as e:
        print(f"  ❌ Error updating Google Sheet for row {row_number}: {e}")
        return False


# --------------------------------------------------------------
# 4. AGENTQL QUERIES
# --------------------------------------------------------------
GET_REPLY_BUTTON_QUERY = """
{
    reply_button
}
"""

GET_CONTACT_OPTIONS_QUERY = """
{
    email_button(contains_text="email")
    call_button(contains_text="call")
    text_button(contains_text="text")
}
"""

GET_COPY_BUTTON_QUERY = """
{
    copy_button
}
"""


# --------------------------------------------------------------
# 5. CONTACT EXTRACTION FUNCTIONS
# --------------------------------------------------------------
def extract_from_clipboard(page, option_button, contact_type):
    """Clicks a contact option button, clicks copy, and reads from clipboard."""
    try:
        print(f"  📋 Extracting {contact_type}...")
        
        option_button.click()
        print(f"  ✅ Clicked {contact_type} button")
        time.sleep(1)
        
        copy_response = page.query_elements(GET_COPY_BUTTON_QUERY)
        if copy_response.copy_button:
            copy_response.copy_button.click()
            print(f"  ✅ Clicked copy button for {contact_type}")
            time.sleep(0.5)
            
            # METHOD 1: Try clipboard
            try:
                contact_info = page.evaluate("navigator.clipboard.readText()")
                
                if contact_info and contact_info.strip():
                    contact_info = contact_info.strip()
                    
                    if contact_type == "email" and validate_email(contact_info):
                        print(f"  ✅ Extracted {contact_type} from clipboard: {contact_info}")
                        return contact_info
                    elif contact_type in ["call", "text"] and validate_phone(contact_info):
                        print(f"  ✅ Extracted {contact_type} from clipboard: {contact_info}")
                        return contact_info
                    else:
                        print(f"  ⚠️  Clipboard contained invalid {contact_type}: {contact_info}")
            except Exception as clipboard_error:
                print(f"  ⚠️  Clipboard read failed: {clipboard_error}")
            
            # METHOD 2: Fallback to HTML parsing
            print(f"  🔄 Falling back to HTML parsing for {contact_type}...")
            page_content = page.content()
            
            if contact_type == "email":
                pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
                matches = re.findall(pattern, page_content)
                valid_emails = [m for m in matches if validate_email(m)]
                if valid_emails:
                    contact_info = valid_emails[0]
                    print(f"  ✅ Extracted {contact_type} from HTML: {contact_info}")
                    return contact_info
            
            elif contact_type in ["call", "text"]:
                pattern = r'\b(?:\+?1[-.]?)?\(?([0-9]{3})\)?[-.]?([0-9]{3})[-.]?([0-9]{4})\b'
                matches = re.findall(pattern, page_content)
                if matches:
                    phone_digits = ''.join(matches[0])
                    phone = format_phone(phone_digits)
                    if validate_phone(phone):
                        print(f"  ✅ Extracted {contact_type} from HTML: {phone}")
                        return phone
        else:
            print(f"  ⚠️  Copy button not found for {contact_type}")
        
        print(f"  ⚠️  No valid {contact_type} found")
        return None
        
    except Exception as e:
        print(f"  ❌ Error extracting {contact_type}: {e}")
        return None


def extract_contact_info_from_page(page):
    """Extracts contact info by clicking reply and handling available contact options."""
    try:
        print("  📧 Attempting to extract contact information...")
        
        contact_info = {
            "email": None,
            "phone": None
        }
        
        # Step 1: Click reply button
        print("  ⏳ Step 1: Clicking reply button...")
        try:
            reply_response = page.query_elements(GET_REPLY_BUTTON_QUERY)
            if reply_response.reply_button:
                print("  ⏳ Waiting 10 seconds to avoid captcha...")
                time.sleep(10)
                
                reply_response.reply_button.click()
                print("  ✅ Clicked reply button")
                time.sleep(2)
            else:
                print("  ⚠️  Reply button not found")
                return None
        except Exception as e:
            print(f"  ❌ Could not click reply button: {e}")
            return None
        
        # Step 2: Query for contact options
        print("  ⏳ Step 2: Checking available contact options...")
        try:
            contact_options = page.query_elements(GET_CONTACT_OPTIONS_QUERY)
            
            has_email = contact_options.email_button is not None
            has_call = contact_options.call_button is not None
            has_text = contact_options.text_button is not None
            
            available = []
            if has_email: available.append("email")
            if has_call: available.append("call")
            if has_text: available.append("text")
            
            if not available:
                print("  ⚠️  No contact options found in dropdown")
                return None
            
            print(f"  ✅ Found contact options: {', '.join(available)}")
            
            # Step 3: Extract email
            if has_email:
                contact_info["email"] = extract_from_clipboard(
                    page, contact_options.email_button, "email"
                )
            else:
                print("  ⚠️  No email option available")
            
            # Step 4: Extract phone (prefer call over text)
            if has_call:
                contact_info["phone"] = extract_from_clipboard(
                    page, contact_options.call_button, "call"
                )
            elif has_text:
                contact_info["phone"] = extract_from_clipboard(
                    page, contact_options.text_button, "text"
                )
            else:
                print("  ⚠️  No phone option available (no call or text)")
            
            return contact_info
            
        except Exception as e:
            print(f"  ❌ Error querying contact options: {e}")
            return None
            
    except Exception as e:
        print(f"  ❌ Error extracting contact info: {e}")
        return None


# --------------------------------------------------------------
# 6. URL PROCESSING FUNCTION
# --------------------------------------------------------------
def process_url(url, row_number, page, worksheet):
    """Processes a single URL - visits it, extracts contact info, and updates Google Sheet."""
    print(f"\n{'─'*70}")
    print(f"🔗 Processing Row {row_number}")
    print(f"🌐 URL: {url[:60]}{'...' if len(url) > 60 else ''}")
    print(f"{'─'*70}")
    
    if check_if_contact_exists(worksheet, row_number):
        print(f"  ⏭️  Skipping - contact already exists")
        return {
            "row_number": row_number,
            "url": url,
            "status": "skipped",
            "reason": "Contact already exists in sheet",
            "email": None,
            "phone": None
        }
    
    try:
        print(f"  🌐 Navigating to URL...")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            print(f"  ✅ Successfully loaded: {page.title()}")
        except Exception as e:
            print(f"  ❌ HTTP Error while loading URL: {e}")
            return {
                "row_number": row_number,
                "url": url,
                "status": "error",
                "error": f"HTTP Error: {e}",
                "email": None,
                "phone": None,
                "sheet_updated": False
            }
        
        contact_info = extract_contact_info_from_page(page)
        email = contact_info.get("email") if contact_info else None
        phone = contact_info.get("phone") if contact_info else None
        
        sheet_updated = update_contact_in_sheet(worksheet, row_number, email=email, phone=phone)
        
        if email or phone:
            status = "success"
            print(f"  ✅ Extraction successful")
        else:
            status = "no_contact"
            print(f"  ⚠️  No valid contact information found")
        
        return {
            "row_number": row_number,
            "url": url,
            "status": status,
            "email": email,
            "phone": phone,
            "sheet_updated": sheet_updated
        }
        
    except Exception as e:
        print(f"  ❌ Error processing URL: {e}")
        return {
            "row_number": row_number,
            "url": url,
            "status": "error",
            "error": str(e),
            "email": None,
            "phone": None,
            "sheet_updated": False
        }
        

# --------------------------------------------------------------
# 7. MAIN PROCESSING SCRIPT
# --------------------------------------------------------------
def run_outreach_processor(test_mode=True, max_links=3, timeout_seconds=60):
    """Main function to process outreach links and extract contact information."""
    print(f"\n{'='*70}")
    print(f"🚀 STARTING OUTREACH PROCESSOR")
    print(f"📅 Start Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if test_mode:
        print(f"⚠️  TEST MODE ENABLED")
        print(f"   - Max Links: {max_links}")
        print(f"   - Timeout: {timeout_seconds}s")
    else:
        print(f"✅ PRODUCTION MODE")
        print(f"   - Processing all links")
        print(f"   - Timeout: {timeout_seconds}s")
    
    print(f"{'='*70}")
    
    start_time = time.time()
    
    # Step 1: Setup Google Sheets
    print(f"\n{'─'*70}")
    print(f"📊 STEP 1: Connecting to Google Sheets")
    print(f"{'─'*70}")
    try:
        worksheet = setup_google_sheets()
    except Exception as e:
        print(f"\n{'='*70}")
        print(f"❌ CRITICAL FAILURE: Could not connect to Google Sheets")
        print(f"❌ Error: {e}")
        print(f"{'='*70}\n")
        return False
    
    elapsed = time.time() - start_time
    if elapsed > timeout_seconds:
        print(f"\n⏱️  Timeout reached after {elapsed:.2f}s during setup")
        return True
    
    # Step 2: Get today's links
    print(f"\n{'─'*70}")
    print(f"🔍 STEP 2: Fetching Today's Links")
    print(f"{'─'*70}")
    
    todays_links = get_todays_outreach_links(worksheet)
    
    if not todays_links:
        print(f"\n{'='*70}")
        print(f"⚠️  NO LINKS FOUND")
        print(f"⚠️  No outreach links found for today's date")
        print(f"{'='*70}\n")
        return False
    
    original_count = len(todays_links)
    if test_mode:
        todays_links = todays_links[:max_links]
        print(f"\n🧪 Test Mode: Processing {len(todays_links)} of {original_count} links")
    else:
        print(f"\n✅ Production Mode: Processing all {len(todays_links)} links")
    
    # Step 3: Launch browser
    print(f"\n{'─'*70}")
    print(f"🌐 STEP 3: Launching Browser and Processing URLs")
    print(f"{'─'*70}")
    
    results = []
    
    with sync_playwright() as playwright:
        try:
            print(f"🚀 Configuring browser...")
            launch_options = {
                "headless": False,
                "ignoreHTTPSErrors": True  # Add this option to ignore SSL certificate errors
            }
            
            if PROXY_ENABLED:
                print(f"🔒 Proxy Status: ENABLED")
                print(f"   Server: {PROXY_SERVER}")
                print(f"   Username: {PROXY_USERNAME[:20]}...")
                launch_options["proxy"] = {
                    "server": PROXY_SERVER,
                    "username": PROXY_USERNAME,
                    "password": PROXY_PASSWORD
                }
                print(f"✅ Proxy configured successfully")
            else:
                print(f"ℹ️  Proxy Status: DISABLED")
                print(f"   Using direct connection (no proxy)")
            
            print(f"🚀 Launching browser...")
            browser = playwright.chromium.launch(**launch_options)
            print(f"✅ Browser launched successfully")
            
            print(f"📄 Creating new page...")
            page = agentql.wrap(browser.new_page())
            print(f"✅ Page created and wrapped with AgentQL")
            
            # Test proxy connection
            if PROXY_ENABLED:
                print(f"\n{'─'*70}")
                print(f"🔍 Verifying Proxy Connection")
                print(f"{'─'*70}")
                
                ip_result = test_proxy_connection(page)
                
                if ip_result["success"]:
                    detected_ip = ip_result["ip_address"]
                    print(f"\n✅ Proxy Verification Complete")
                    print(f"   Detected IP: {detected_ip}")
                    print(f"   ✅ Proxy is working correctly!")
                else:
                    print(f"\n⚠️  Proxy Verification Failed")
                    print(f"   Error: {ip_result.get('error', 'Unknown error')}")
                    print(f"   ⚠️  Continuing anyway, but proxy may not be working")
                
                print(f"\n{'─'*70}")
                print(f"⏳ Waiting 3 seconds before starting URL processing...")
                print(f"{'─'*70}")
                time.sleep(3)
            
            print(f"\n{'─'*70}")
            print(f"⚙️  PROCESSING URLS")
            print(f"{'─'*70}")
            
            for idx, (row_num, url, date_added) in enumerate(todays_links, 1):
                print(f"\n[{idx}/{len(todays_links)}] Starting next URL...")
                
                elapsed = time.time() - start_time
                if elapsed > timeout_seconds:
                    print(f"\n{'='*70}")
                    print(f"⏱️  TIMEOUT REACHED")
                    print(f"⏱️  Stopped after {elapsed:.2f}s")
                    print(f"⏱️  Processed {len(results)}/{len(todays_links)} URLs")
                    print(f"{'='*70}")
                    break
                
                result = process_url(url, row_num, page, worksheet)
                results.append(result)
                
                if idx < len(todays_links):
                    print(f"  ⏳ Waiting 2 seconds before next URL...")
                    time.sleep(2)
            
            print(f"\n{'─'*70}")
            print(f"⏸️  Keeping browser open for 5 seconds...")
            print(f"{'─'*70}")
            time.sleep(5)
            
            print(f"🔒 Closing browser...")
            browser.close()
            print(f"✅ Browser closed successfully")
            
        except Exception as e:
            print(f"\n{'='*70}")
            print(f"❌ ERROR IN BROWSER OPERATIONS")
            print(f"❌ Error: {e}")
            print(f"{'='*70}")
    
    elapsed_time = time.time() - start_time
    
    # Step 4: Print summary
    print(f"\n{'='*70}")
    print(f"📊 PROCESSING SUMMARY")
    print(f"{'='*70}")
    
    total_processed = len(results)
    successful = sum(1 for r in results if r.get('status') == 'success')
    skipped = sum(1 for r in results if r.get('status') == 'skipped')
    no_contact = sum(1 for r in results if r.get('status') == 'no_contact')
    errors = sum(1 for r in results if r.get('status') == 'error')
    
    print(f"\n📈 Results Breakdown:")
    print(f"   Total URLs Processed:    {total_processed}")
    print(f"   ✅ Success (contact found): {successful}")
    print(f"   ⏭️  Skipped (already done):  {skipped}")
    print(f"   ⚠️  No Contact Found:       {no_contact}")
    print(f"   ❌ Errors:                 {errors}")
    
    attempted = total_processed - skipped
    if attempted > 0:
        success_rate = (successful / attempted) * 100
        print(f"\n📊 Success Rate: {success_rate:.1f}% ({successful}/{attempted} attempted)")
    
    print(f"\n⏱️  Timing:")
    print(f"   Total Time: {elapsed_time:.2f}s")
    if total_processed > 0:
        avg_time = elapsed_time / total_processed
        print(f"   Average per URL: {avg_time:.2f}s")
    
    emails_found = sum(1 for r in results if r.get('email'))
    phones_found = sum(1 for r in results if r.get('phone'))
    print(f"\n📧 Contact Information Extracted:")
    print(f"   Emails: {emails_found}")
    print(f"   Phones: {phones_found}")
    
    print(f"\n{'='*70}")
    print(f"✅ PROCESSING COMPLETE")
    print(f"📅 End Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")
    
    return True


# --------------------------------------------------------------07
# 8. MAIN ENTRY POINT
# --------------------------------------------------------------
def main():
    """Main entry point function - configures and runs the outreach processor."""
    print("\n" + "="*70)
    print("🎯 CRAIGSLIST CONTACT SCRAPER")
    print("="*70)
    print("📝 Script: scraper_link.py")
    print("🎯 Purpose: Extract contact info from Craigslist listings")
    print("📊 Output: Google Sheets (Column L=Email, Column M=Phone)")
    print("="*70)
    
    # ──────────────────────────────────────────────────────────
    # CONFIGURATION: Toggle between test and production mode
    # ──────────────────────────────────────────────────────────
    
    # TEST MODE CONFIGURATION
    TEST_MODE = True
    MAX_LINKS = 3
    TIMEOUT_SECONDS = 60
    
    # PRODUCTION MODE CONFIGURATION
    # To run in production mode, set TEST_MODE = False
    # TEST_MODE = False
    # MAX_LINKS = None
    # TIMEOUT_SECONDS = 600
    
    print("\n⚙️  CONFIGURATION:")
    if TEST_MODE:
        print(f"   Mode: TEST")
        print(f"   Max Links: {MAX_LINKS}")
        print(f"   Timeout: {TIMEOUT_SECONDS}s")
    else:
        print(f"   Mode: PRODUCTION")
        print(f"   Max Links: ALL")
        print(f"   Timeout: {TIMEOUT_SECONDS}s")
    
    print(f"\n🔒 PROXY CONFIGURATION:")
    if PROXY_ENABLED:
        print(f"   Status: ENABLED ✅")
        print(f"   Server: {PROXY_SERVER}")
        print(f"   Provider: Bright Data / Smartproxy")
        if TEST_MODE:
            print(f"   IP Test: Will run before processing URLs")
    else:
        print(f"   Status: DISABLED ❌")
        print(f"   Connection: Direct (using your real IP)")
        print(f"   ⚠️  Captchas may occur with heavy usage")
    
    print("="*70)
    
    try:
        success = run_outreach_processor(
            test_mode=TEST_MODE,
            max_links=MAX_LINKS,
            timeout_seconds=TIMEOUT_SECONDS
        )
    except KeyboardInterrupt:
        print("\n\n" + "="*70)
        print("⚠️  INTERRUPTED BY USER")
        print("⚠️  Script stopped via Ctrl+C")
        print("="*70)
        sys.exit(130)
    except Exception as e:
        print("\n\n" + "="*70)
        print("❌ UNEXPECTED ERROR")
        print(f"❌ Error: {e}")
        print("="*70)
        sys.exit(1)
    
    if not success:
        print("\n" + "="*70)
        print("❌ PROCESSOR FAILED")
        print("❌ Critical error prevented processing")
        print("="*70 + "\n")
        sys.exit(1)
    else:
        print("\n" + "="*70)
        print("✅ PROCESSOR SUCCEEDED")
        print("✅ All processing completed successfully")
        print("="*70 + "\n")
        sys.exit(0)


# ------------------------------------------------


# ------------------------------------------------
# --------------------------------------------------------------
if __name__ == "__main__":
    main()