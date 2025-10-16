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
import schedule
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
TARGET_URL = os.getenv('TARGET_URL')
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
# 2. HTML PARSING CONFIGURATION
# --------------------------------------------------------------
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# Regex helpers for post URL detection
HTML_END_RE = re.compile(r"\.html(\?.*)?$", re.IGNORECASE)
NUM_ID_RE = re.compile(r"/(\d+)(?:\.html)?(?:\?|$)")

# Weights for scoring post URLs
WEIGHTS = {
    "ends_with_html": 3.0,
    "contains_numeric_id": 1.5,
    "has_d_segment": 1.5,
    "inside_result_container": 2.0,
    "anchor_text_present": 0.8,
    "data_pid_present": 2.0,
    "absolute_host_matches": 1.0,
    "rel_nofollow": -0.5,
}

# --------------------------------------------------------------
# 3. AGENTQL QUERIES (for individual post pages)
# --------------------------------------------------------------
GET_POSTING_BODY_QUERY = """
{
    posting_body(element: "#postingbody")
}
"""

GET_EMAIL_QUERY = """
{
    reply_link(element: "a[href*='mailto']")
}
"""

# --------------------------------------------------------------
# 4. HTML PARSING FUNCTIONS
# --------------------------------------------------------------
def extract_post_urls_with_playwright(page, base_url):
    """
    Alternative method: Extract post URLs directly from Playwright page.
    This is more reliable for JavaScript-rendered content.

    Args:
        page: Playwright page object
        base_url: Base URL for the search

    Returns:
        List of tuples: (url, is_today, date_str, parsed_date)
    """
    print("\n🔍 Using Playwright direct extraction method...")
    results = []

    try:
        # Find all anchor tags that look like post links
        all_links = page.locator('a[href*=".html"]').all()
        print(f"  Found {len(all_links)} potential post links")

        today = datetime.date.today()

        for idx, link in enumerate(all_links, 1):
            try:
                href = link.get_attribute('href')

                # Skip non-post links
                if not href or any(skip in href for skip in ['/search/', 'javascript:', 'mailto:', '#', '/about/']):
                    continue

                # Make absolute URL
                if href.startswith('http'):
                    full_url = href
                else:
                    full_url = urljoin(base_url, href)

                # Try to find associated date element (look in parent or nearby elements)
                try:
                    parent = link.locator('xpath=ancestor::li[1] | ancestor::div[1]').first
                    date_elem = parent.locator('time, span[class*="date"]').first
                    date_text = date_elem.get_attribute('title') or date_elem.inner_text()

                    # Simple today check
                    is_today = 'today' in date_text.lower() or today.strftime('%Y') in date_text

                    if is_today:
                        results.append((full_url, True, today.strftime("%m/%d"), today))
                        print(f"  ✅ Item {idx}: {full_url[:60]}... (TODAY)")
                except:
                    # No date found, add anyway
                    results.append((full_url, False, "Unknown", None))
                    print(f"  ⚠️  Item {idx}: {full_url[:60]}... (no date)")

            except Exception as e:
                print(f"  ❌ Error processing link {idx}: {e}")
                continue

    except Exception as e:
        print(f"❌ Playwright extraction error: {e}")

    return results

def parse_craigslist_date(date_span):
    """
    Parses date from Craigslist date span element.
    
    Args:
        date_span: BeautifulSoup span element with class 'cl-date'
        
    Returns:
        Tuple of (is_today: bool, date_str: str, parsed_date: date)
    """
    try:
        today = datetime.date.today()
        
        # Get the title attribute which has full date
        date_title = date_span.get('title', '')
        display_date = date_span.get_text().strip()
        
        if not date_title:
            # Fallback to display text
            if display_date.lower() == "today":
                return True, today.strftime("%m/%d"), today
            
            try:
                parsed_date = parser.parse(display_date).date()
                if parsed_date.year == 1900:
                    parsed_date = parsed_date.replace(year=today.year)
                is_today = parsed_date == today
                return is_today, parsed_date.strftime("%m/%d"), parsed_date
            except:
                return False, display_date, None
        
        # Parse title: "Sun Oct 12 2025 17:27:56 GMT-0700 (Pacific Daylight Time)"
        date_part = date_title.split(' GMT')[0]
        parsed_date = parser.parse(date_part).date()
        
        is_today = parsed_date == today
        formatted_date = parsed_date.strftime("%m/%d")
        
        return is_today, formatted_date, parsed_date
        
    except Exception as e:
        print(f"Error parsing date: {e}")
        return False, display_date if display_date else "Unknown", None

def extract_post_urls_and_dates_from_html(html, base_url, debug_mode=False):
    """
    Extracts post URLs and their dates from Craigslist search results HTML.

    Args:
        html: HTML content of the search results page
        base_url: Base URL for resolving relative links
        debug_mode: If True, saves HTML to file for debugging

    Returns:
        List of tuples: (url, is_today, date_str, parsed_date)
    """
    soup = BeautifulSoup(html, 'lxml')
    results = []

    # Debug: Save HTML if requested
    if debug_mode:
        debug_file = f"debug_html_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        with open(debug_file, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"🐛 Debug: HTML saved to {debug_file}")

    # Try multiple strategies to find result items
    print("\n🔍 Attempting to find result items...")

    # Strategy 1: Look for li elements with result-related classes
    result_items = soup.find_all('li', class_=re.compile(r'(result-row|cl-search-result|cl-static-search-result)', re.IGNORECASE))
    print(f"  Strategy 1 (li with result classes): {len(result_items)} items")

    # Strategy 2: Look for any li with data-pid attribute (common in Craigslist)
    if not result_items:
        result_items = soup.find_all('li', attrs={'data-pid': True})
        print(f"  Strategy 2 (li with data-pid): {len(result_items)} items")

    # Strategy 3: Look for divs with result classes
    if not result_items:
        result_items = soup.find_all('div', class_=re.compile(r'result', re.IGNORECASE))
        print(f"  Strategy 3 (div with result class): {len(result_items)} items")

    # Strategy 4: Look for any element with 'result' in class and containing an anchor
    if not result_items:
        result_items = soup.find_all(['li', 'div'], class_=re.compile(r'.*', re.IGNORECASE))
        result_items = [item for item in result_items if item.find('a', href=re.compile(r'\.html'))]
        print(f"  Strategy 4 (any element with .html link): {len(result_items)} items")

    # Strategy 5: Debug - show all li elements
    if not result_items:
        all_lis = soup.find_all('li')
        print(f"  Strategy 5 (DEBUG - all li elements): {len(all_lis)} items")
        if all_lis:
            print(f"  Sample li classes: {[li.get('class') for li in all_lis[:5]]}")
        result_items = all_lis

    print(f"\n✅ Total result items found: {len(result_items)}\n")

    for idx, item in enumerate(result_items, 1):
        try:
            # Find the post link - try multiple selectors
            link = None

            # Strategy A: Common link selectors
            link_elem = (
                item.find('a', class_=re.compile(r'(result-title|main|cl-app-anchor)', re.IGNORECASE)) or
                item.find('a', href=re.compile(r'\.html')) or
                item.find('a', {'data-pid': True}) or
                item.find('a')  # Fallback: any anchor
            )

            if link_elem and link_elem.get('href'):
                href = link_elem['href']
                # Skip non-post links (like gallery, map, etc.)
                if any(skip in href for skip in ['/search/', 'javascript:', 'mailto:', '#']):
                    continue
                link = urljoin(base_url, href)
                print(f"  📎 Item {idx}: Found link: {link[:80]}")
            else:
                print(f"  ⚠️  Item {idx}: No link found, skipping")
                continue

            # Find the date - try multiple selectors
            date_span = (
                item.find('time', attrs={'title': re.compile(r'\b\d{4}\b')}) or
                item.find('span', attrs={'title': re.compile(r'\b\d{4}\b')}) or
                item.find('time', class_=re.compile(r'date', re.IGNORECASE)) or
                item.find('span', class_=re.compile(r'date', re.IGNORECASE)) or
                item.find('time') or
                item.find('span', attrs={'title': True})
            )

            if link and date_span:
                is_today, date_str, parsed_date = parse_craigslist_date(date_span)
                print(f"     📅 Date: {date_span.get('title', date_span.text)[:50]} (today? {is_today})")
                if is_today:
                    results.append((link, is_today, date_str, parsed_date))
                    print(f"     ✅ Added to results")
            elif link:
                print(f"     ⚠️  No date found for this link")
                # Still try to add it with unknown date
                results.append((link, False, "Unknown", None))

        except Exception as e:
            print(f"  ❌ Item {idx}: Error parsing - {e}")
            continue

    return results

# --------------------------------------------------------------
# 5. UTILITY FUNCTIONS
# --------------------------------------------------------------
def extract_state_from_url(url: str) -> str:
    """Extracts state abbreviation from Craigslist URL."""
    city_to_state = {
        'newyork': 'NY', 'albany': 'NY', 'buffalo': 'NY', 'rochester': 'NY', 'syracuse': 'NY',
        'losangeles': 'CA', 'sfbay': 'CA', 'sandiego': 'CA', 'sacramento': 'CA', 'fresno': 'CA',
        'chicago': 'IL', 'peoria': 'IL', 'rockford': 'IL', 'springfieldil': 'IL',
        'houston': 'TX', 'dallas': 'TX', 'austin': 'TX', 'sanantonio': 'TX', 'elpaso': 'TX',
        'miami': 'FL', 'tampa': 'FL', 'orlando': 'FL', 'jacksonville': 'FL', 'tallahassee': 'FL',
        'philadelphia': 'PA', 'pittsburgh': 'PA', 'harrisburg': 'PA', 'erie': 'PA',
        'atlanta': 'GA', 'columbus': 'OH', 'cleveland': 'OH', 'cincinnati': 'OH',
        'detroit': 'MI', 'boston': 'MA', 'seattle': 'WA', 'portland': 'OR', 'denver': 'CO',
        'phoenix': 'AZ', 'lasvegas': 'NV', 'albuquerque': 'NM', 'saltlakecity': 'UT',
        # Add more as needed
    }
    
    try:
        if 'craigslist.org' in url:
            city_part = url.split('//')[1].split('.')[0]
            return city_to_state.get(city_part, 'Unknown')
        return 'Unknown'
    except Exception as e:
        print(f"Error extracting state: {e}")
        return 'Unknown'

def extract_location_from_url(url: str) -> str:
    """Extracts location name from Craigslist URL."""
    city_names = {
        'newyork': 'New York', 'losangeles': 'Los Angeles', 'chicago': 'Chicago',
        'houston': 'Houston', 'miami': 'Miami', 'dallas': 'Dallas', 'austin': 'Austin',
        'seattle': 'Seattle', 'boston': 'Boston', 'atlanta': 'Atlanta', 'portland': 'Portland',
        'sfbay': 'San Francisco Bay Area', 'sandiego': 'San Diego',
    }
    
    try:
        if 'craigslist.org' in url:
            city_part = url.split('//')[1].split('.')[0]
            return city_names.get(city_part, city_part.replace('-', ' ').title())
        return 'Unknown'
    except:
        return 'Unknown'

def extract_email_from_page(page) -> str:
    """Extracts email from page HTML."""
    try:
        email_response = page.query_elements(GET_EMAIL_QUERY)
        if email_response.reply_link:
            href = email_response.reply_link.get_attribute("href")
            if href and href.startswith("mailto:"):
                email = href.replace("mailto:", "")
                if email and "@" in email:
                    return email
        
        page_content = page.content()
        craigslist_email_pattern = r'[a-f0-9]{32}@job\.craigslist\.org'
        matches = re.findall(craigslist_email_pattern, page_content)
        if matches:
            return matches[0]
        
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        email_matches = re.findall(email_pattern, page_content)
        
        filtered_emails = [email for email in email_matches 
                          if not any(domain in email.lower() 
                          for domain in ['noreply', 'no-reply', 'donotreply', 'example.com'])]
        
        return filtered_emails[0] if filtered_emails else None
    except Exception as e:
        print(f"Error extracting email: {e}")
        return None

# --------------------------------------------------------------
# 6. GOOGLE SHEETS FUNCTIONS
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

def check_duplicate_posting(worksheet, posting_url):
    """Checks if a posting URL already exists in the sheet."""
    try:
        urls = worksheet.col_values(11)  # Column 11 is Outreach Link
        return posting_url in urls
    except Exception as e:
        print(f"Error checking for duplicates: {e}")
        return False

def append_to_google_sheet(worksheet, data):
    """Appends a row of data to the Google Sheet."""
    print("📝 Adding data to Google Sheet...")
    
    import hashlib
    url_hash = hashlib.md5(data.get('Outreach Link', '').encode()).hexdigest()[:8]
    unique_id = f"CL_{url_hash}"
    
    row = [
        unique_id,                        # Column 1 - ID
        data.get('Company', ''),          # Column 2 - Company
        data.get('Date Source Added', ''), # Column 3 - Date Source Added
        data.get('State', ''),            # Column 4 - State
        data.get('Source', 'Craigslist'), # Column 5 - Source
        data.get('Name', ''),             # Column 6 - Name
        data.get('Address', ''),          # Column 7 - Address
        data.get('Type of Business', ''), # Column 8 - Type of Business
        data.get('Email', ''),            # Column 9 - Email
        data.get('Phone Number', ''),     # Column 10 - Phone Number
        data.get('Outreach Link', ''),    # Column 11 - Outreach Link
        data.get('Website', '')           # Column 12 - Website
    ]
    
    try:
        worksheet.append_row(row)
        print(f"✅ Successfully added - ID: {unique_id}, Company: {data.get('Company', 'N/A')}")
        return True
    except Exception as e:
        print(f"❌ Error adding data to Google Sheet: {e}")
        raise

# --------------------------------------------------------------
# 7. LLM ANALYSIS FUNCTION
# --------------------------------------------------------------
def analyze_job_posting(job_text: str) -> dict:
    """Uses Perplexity's model to analyze job posting text."""
    print("  Analyzing with LLM...")
    
    business_types = "['restaurant', 'salon', 'nail salon', 'barber shop', 'retail', 'office', 'warehouse', 'construction', 'healthcare', 'education', 'other']"
    
    system_prompt = (
        "You are an expert data extraction assistant. Analyze the job posting text and extract information. "
        "Return ONLY a valid JSON object with the keys: 'company_name', 'contact_name', 'address', "
        "'business_type', 'email', 'phone_number', 'website'. No other text."
    )
    
    user_prompt = f"""
    Extract from this job posting:
    1. company_name: Company/business name (or "N/A")
    2. contact_name: Any person's name mentioned (or "N/A")
    3. address: Business address (or "")
    4. business_type: ONE of {business_types}
    5. email: Email address (or null)
    6. phone_number: 10-digit phone number (or null)
    7. website: Company website URL (or "N/A")

    Job Posting Text:
    ---
    {job_text}
    ---
    """

    try:
        response = client.chat.completions.create(
            model="llama-3-sonar-large-32k-online",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        print(f"  ⚠️  LLM analysis error: {e}")
        return {
            "company_name": "N/A",
            "contact_name": "N/A",
            "address": "",
            "business_type": "other",
            "email": None,
            "phone_number": None,
            "website": "N/A"
        }

# --------------------------------------------------------------
# 8. MAIN SCRAPING SCRIPT
# --------------------------------------------------------------
def run_scraper():
    """Main scraping function."""
    print(f"\n{'='*70}")
    print(f"STARTING CRAIGSLIST SCRAPER - {datetime.datetime.now()}")
    print(f"{'='*70}")
    
    # Setup Google Sheets
    try:
        worksheet = setup_google_sheets()
    except Exception as e:
        print(f"❌ FAILURE: Could not connect to Google Sheets: {e}")
        return False

    entries_added = 0
    
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        page = agentql.wrap(browser.new_page())

        try:
            # Navigate to search URL
            search_url = TARGET_URL if TARGET_URL else "https://newyork.craigslist.org/search/jjj?query=cashier#search=2~thumb~0"
            print(f"\n📍 Navigating to: {search_url}")
            page.goto(search_url, wait_until="domcontentloaded")

            # Wait for dynamic content to load - try multiple strategies
            print("⏳ Waiting for search results to load...")

            # Strategy 1: Wait for common result selectors
            try:
                page.wait_for_selector('li[class*="result"], li[data-pid], .result-row, .cl-search-result', timeout=10000)
                print("  ✅ Results detected via selector")
            except:
                print("  ⚠️  Timeout waiting for result selectors, continuing anyway...")

            # Additional wait for any JavaScript rendering
            time.sleep(3)

            # Get HTML content
            html_content = page.content()
            print("✅ Page loaded, parsing HTML...")

            # Method 1: Try BeautifulSoup HTML parsing with debug mode
            print("\n" + "="*70)
            print("METHOD 1: BeautifulSoup HTML Parsing")
            print("="*70)
            post_data = extract_post_urls_and_dates_from_html(html_content, search_url, debug_mode=True)

            # Method 2: If Method 1 fails, use Playwright direct extraction
            if not post_data:
                print("\n" + "="*70)
                print("METHOD 2: Playwright Direct Extraction (Fallback)")
                print("="*70)
                post_data = extract_post_urls_with_playwright(page, search_url)

            if not post_data:
                print("\n❌ FAILURE: No job postings found using either method")
                print("   Check the debug HTML file to see the actual page structure")
                return False
            
            # Filter for today's postings only
            today_postings = []
            found_first_today = False
            
            for url, is_today, date_str, parsed_date in post_data:
                if is_today:
                    found_first_today = True
                    today_postings.append({
                        'url': url,
                        'date': date_str,
                        'parsed_date': parsed_date
                    })
                else:
                    # Stop when we hit first non-today posting after finding today's posts
                    if found_first_today:
                        print(f"⏹️  Reached end of today's postings, stopping collection")
                        break
            
            if not today_postings:
                print("⚠️  WARNING: No postings from today found")
                print("❌ FAILURE: Cannot add entries to Google Sheets without today's postings")
                return False
            
            print(f"\n{'='*70}")
            print(f"📊 Found {len(today_postings)} postings from TODAY to process")
            print(f"{'='*70}\n")

            # Process each posting
            processed_count = 0
            skipped_count = 0
            failed_urls = []
            
            for i, posting_info in enumerate(today_postings, 1):
                try:
                    posting_url = posting_info['url']
                    posting_date = posting_info['date']
                    
                    print(f"\n{'─'*70}")
                    print(f"Processing {i}/{len(today_postings)}: {posting_url[:60]}...")
                    print(f"{'─'*70}")
                    
                    # Check for duplicates
                    if check_duplicate_posting(worksheet, posting_url):
                        print(f"⊗ Duplicate found, skipping")
                        skipped_count += 1
                        continue
                    
                    # Navigate to posting
                    page.goto(posting_url, wait_until="domcontentloaded")
                    time.sleep(1)
                    
                    # Get posting body text
                    body_response = page.query_elements(GET_POSTING_BODY_QUERY)
                    # Use inner_text() for AgentQL/Playwright elements, not get_text()
                    posting_text = body_response.posting_body.inner_text()

                    # Analyze with LLM
                    llm_data = analyze_job_posting(posting_text)

                    # Extract additional data
                    state = extract_state_from_url(posting_url)
                    html_email = extract_email_from_page(page)
                    email = html_email if html_email else llm_data.get("email")
                    location = extract_location_from_url(posting_url)
                    
                    website = llm_data.get("website")
                    if not website or website == "N/A":
                        website = f"{llm_data.get('business_type', 'Business')} - {location}"

                    # Assemble final data
                    final_data = {
                        "Company": llm_data.get("company_name", "N/A"),
                        "Date Source Added": posting_date,
                        "State": state,
                        "Source": "Craigslist",
                        "Name": llm_data.get("contact_name", "N/A"),
                        "Address": llm_data.get("address", ""),
                        "Type of Business": llm_data.get("business_type", ""),
                        "Email": email,
                        "Phone Number": llm_data.get("phone_number", ""),
                        "Outreach Link": posting_url,
                        "Website": website
                    }

                    print(f"\n  📋 Extracted Data:")
                    print(f"     Company: {final_data['Company']}")
                    print(f"     Email: {final_data['Email']}")
                    print(f"     Business Type: {final_data['Type of Business']}")

                    # Add to Google Sheets
                    if append_to_google_sheet(worksheet, final_data):
                        processed_count += 1
                        entries_added += 1

                    # Small delay
                    time.sleep(1.5)

                except Exception as e:
                    print(f"  ❌ Error processing posting: {e}")
                    failed_urls.append(posting_url)
                    continue

            # Final report
            print(f"\n{'='*70}")
            print(f"SCRAPING COMPLETE")
            print(f"{'='*70}")
            print(f"✅ Successfully processed: {processed_count}")
            print(f"⊗ Skipped (duplicates): {skipped_count}")
            print(f"❌ Failed: {len(failed_urls)}")
            
            if entries_added > 0:
                print(f"\n🎉 SUCCESS: Added {entries_added} entries to Google Sheets")
            else:
                print(f"\n❌ FAILURE: No entries were added to Google Sheets")
                
            if failed_urls:
                print("\nFailed URLs:")
                for url in failed_urls[:5]:
                    print(f"  - {url}")
            print(f"{'='*70}\n")
            
            return entries_added > 0

        except Exception as e:
            print(f"\n❌ CRITICAL ERROR during scraping: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            print("Keeping browser open for 10 seconds...")
            time.sleep(10)
            browser.close()

def main():
    """Main function."""
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--schedule":
        pst = pytz.timezone('US/Pacific')
        schedule.every().day.at("21:00").do(run_scraper)
        
        print("📅 Scheduler started. Will run daily at 9:00 PM PST.")
        print("Press Ctrl+C to stop.")
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n⏹️  Scheduler stopped.")
    else:
        success = run_scraper()
        if not success:
            print("\n❌ SCRAPER FAILED - No entries added to Google Sheets")
            sys.exit(1)
        else:
            print("\n✅ SCRAPER SUCCEEDED - Entries added to Google Sheets")
            sys.exit(0)

if __name__ == "__main__":
    main()