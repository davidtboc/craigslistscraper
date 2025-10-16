"""
Link Scraper - Google Sheets Link Processor
============================================

This script reads links from Google Sheets (Column K) and scrapes each link,
then writes the results back to the sheet (Column M).

WORKFLOW:
1. Connects to Google Sheets (same credentials as scraper_rewritten.py)
2. Reads unprocessed links from Column K (11) - "Outreach Link"
3. For each link:
   - Navigates to the URL from Column K
   - Scrapes data from the page (customize in scrape_link() function)
   - Writes result to Column M (13) - "Scraped Data"
   - Marks row as processed in Column N (14) - ✓ or ❌

USAGE:
    python link_scraper.py              # Process all unprocessed links
    python link_scraper.py --max=10     # Test with first 10 links
    python link_scraper.py --start=50   # Start from row 50

CUSTOMIZATION:
    Edit the scrape_link() function to customize what data to extract.
"""

import os
import agentql
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import datetime
import time
import gspread
from google.oauth2.service_account import Credentials
from urllib.parse import urlparse
import traceback

# --------------------------------------------------------------
# 1. SETUP: Load environment variables and configure APIs
# (Reuses exact same configuration as scraper_rewritten.py)
# --------------------------------------------------------------
print("Loading environment variables...")
load_dotenv()

# Set AgentQL API key (same as scraper_rewritten.py)
os.environ["AGENTQL_API_KEY"] = os.getenv('AGENTQL_API_KEY')

# Google Sheets configuration (same as scraper_rewritten.py)
GOOGLE_SHEET_ID = "1Fc0JO91CAvciNYi5LMMUO9K8J_7yzYlp1LUFyOs6PqA"
GOOGLE_SHEETS_CREDS_FILE = os.getenv('GOOGLE_SHEETS_CREDS_FILE', 'credentials.json')

# Validate environment variables
if not all([os.environ.get("AGENTQL_API_KEY")]):
    raise ValueError("AGENTQL_API_KEY is missing. Please check your .env file.")

print(f"✅ Configuration complete")
print(f"   - Using Google Sheet ID: {GOOGLE_SHEET_ID}")
print(f"   - Credentials file: {GOOGLE_SHEETS_CREDS_FILE}")

# --------------------------------------------------------------
# 2. CONFIGURATION: Define what to scrape and where to write
# --------------------------------------------------------------
# Column indices (0-based for internal use, but we'll use 1-based for Google Sheets API)
LINK_COLUMN = 11  # Column K - "Outreach Link"
RESULT_COLUMN = 13  # Column M - Where to write the scraped result
PROCESSED_FLAG_COLUMN = 14  # Column N - Track if row has been processed

# Define what data to extract from each link
# TODO: Customize this based on what you want to scrape
SCRAPE_QUERY = """
{
    page_title
    main_content
}
"""

# --------------------------------------------------------------
# 3. GOOGLE SHEETS FUNCTIONS
# --------------------------------------------------------------
def setup_google_sheets():
    """
    Sets up connection to Google Sheets.
    Uses the same authentication method as scraper_rewritten.py.

    Returns:
        worksheet: The first sheet of the spreadsheet
    """
    print("\n" + "="*70)
    print("CONNECTING TO GOOGLE SHEETS")
    print("="*70)
    print(f"Sheet ID: {GOOGLE_SHEET_ID}")
    print(f"Credentials: {GOOGLE_SHEETS_CREDS_FILE}")

    if not os.path.exists(GOOGLE_SHEETS_CREDS_FILE):
        raise FileNotFoundError(f"Credentials file not found: {GOOGLE_SHEETS_CREDS_FILE}")

    # Same scopes as scraper_rewritten.py
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]

    try:
        # Authenticate using service account (same as scraper_rewritten.py)
        creds = Credentials.from_service_account_file(GOOGLE_SHEETS_CREDS_FILE, scopes=scopes)
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(GOOGLE_SHEET_ID)
        worksheet = spreadsheet.sheet1
        print(f"✅ Connected to Google Sheet: {spreadsheet.title}")

        # Get and display headers with column letters
        headers = worksheet.row_values(1)
        print(f"\n📋 Sheet Structure:")
        for i, header in enumerate(headers[:15], 1):  # Show first 15 columns
            col_letter = chr(64 + i)  # A=65, so 64+1=A
            marker = " ← LINK SOURCE" if i == LINK_COLUMN else " ← RESULT OUTPUT" if i == RESULT_COLUMN else ""
            print(f"   Column {col_letter} ({i:2d}): {header}{marker}")

        # Ensure our result columns exist
        ensure_columns_exist(worksheet, headers)

        return worksheet

    except Exception as e:
        print(f"❌ Error setting up Google Sheets: {e}")
        raise

def ensure_columns_exist(worksheet, current_headers):
    """Ensures the necessary columns exist in the spreadsheet."""
    print("\nChecking if result columns exist...")

    # Check if we need to add column headers
    if len(current_headers) < RESULT_COLUMN:
        print(f"  Adding header for column {RESULT_COLUMN}...")
        worksheet.update_cell(1, RESULT_COLUMN, "Scraped Data")

    if len(current_headers) < PROCESSED_FLAG_COLUMN:
        print(f"  Adding header for column {PROCESSED_FLAG_COLUMN}...")
        worksheet.update_cell(1, PROCESSED_FLAG_COLUMN, "Processed")

    print("✅ Columns ready")

def get_unprocessed_links(worksheet):
    """
    Retrieves all rows that have links in Column K but haven't been processed yet.

    Reads from Column K (11) - "Outreach Link"
    Checks Column N (14) - "Processed" flag

    Returns:
        List of tuples: (row_number, link_url)
    """
    print("\n" + "="*70)
    print("READING LINKS FROM COLUMN K (Outreach Link)")
    print("="*70)

    try:
        # Get all values from the sheet
        all_values = worksheet.get_all_values()
        print(f"Total rows in sheet: {len(all_values)}")

        unprocessed = []

        # Skip header row (index 0), start from row 2
        for row_idx, row in enumerate(all_values[1:], start=2):
            # Check if row has enough columns to contain our link column
            if len(row) < LINK_COLUMN:
                continue

            # Get the link from Column K (index 10, since 0-based)
            # LINK_COLUMN = 11, so array index is 10
            link = row[LINK_COLUMN - 1].strip() if len(row) >= LINK_COLUMN else ""

            # Get the processed flag from Column N (index 13, since 0-based)
            processed_flag = row[PROCESSED_FLAG_COLUMN - 1].strip() if len(row) >= PROCESSED_FLAG_COLUMN else ""

            # If there's a link and it hasn't been processed
            if link and processed_flag != "✓":
                unprocessed.append((row_idx, link))
                print(f"   Row {row_idx}: {link[:60]}... (unprocessed)")

        print(f"\n✅ Found {len(unprocessed)} unprocessed links in Column K")

        if not unprocessed:
            print("   No unprocessed links found. Either:")
            print("   - All links have been processed (marked with ✓)")
            print("   - Column K is empty")
            print("   - All rows are missing the processed flag")

        return unprocessed

    except Exception as e:
        print(f"❌ Error fetching links from Column K: {e}")
        import traceback
        traceback.print_exc()
        return []

def update_row_data(worksheet, row_number, scraped_data, success=True):
    """
    Updates a row with the scraped data and marks it as processed.

    Args:
        worksheet: Google Sheets worksheet object
        row_number: Row number to update (1-based)
        scraped_data: Data to write to the result column
        success: Whether the scraping was successful
    """
    try:
        # Write the scraped data
        worksheet.update_cell(row_number, RESULT_COLUMN, scraped_data)

        # Mark as processed
        if success:
            worksheet.update_cell(row_number, PROCESSED_FLAG_COLUMN, "✓")
        else:
            worksheet.update_cell(row_number, PROCESSED_FLAG_COLUMN, "❌")

        print(f"  ✅ Updated row {row_number}")
        return True

    except Exception as e:
        print(f"  ❌ Error updating row {row_number}: {e}")
        return False

# --------------------------------------------------------------
# 4. WEB SCRAPING FUNCTIONS
# --------------------------------------------------------------
def scrape_link(page, url):
    """
    Scrapes a single link (from Column K) and extracts relevant data.

    This function navigates to the URL from Column K (Outreach Link)
    and extracts data from the page.

    Args:
        page: Playwright page object (wrapped with AgentQL)
        url: URL to scrape (from Column K)

    Returns:
        Extracted data as string, or error message
    """
    try:
        print(f"  🌐 Navigating to URL from Column K...")
        print(f"     {url}")

        # Navigate to the URL from Column K
        response = page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # Check if page loaded successfully
        if response and response.status >= 400:
            return f"Error: HTTP {response.status}"

        # Wait for content to load
        time.sleep(2)

        print(f"  ✅ Page loaded successfully")

        # TODO: Customize this section based on what you want to scrape
        # ============================================================
        # CUSTOMIZATION AREA - Edit this to scrape what you need
        # ============================================================

        # Option 1: Use AgentQL for structured extraction
        try:
            result = page.query_elements(SCRAPE_QUERY)
            title = result.page_title.inner_text() if hasattr(result, 'page_title') else "N/A"
            content = result.main_content.inner_text() if hasattr(result, 'main_content') else "N/A"

            scraped_data = f"Title: {title} | Content: {content[:100]}..."

        except Exception as e:
            # Fallback: Just get the page title
            print(f"  ⚠️  AgentQL query failed, using fallback: {e}")
            scraped_data = page.title()

        # ============================================================
        # END CUSTOMIZATION AREA
        # ============================================================

        print(f"  ✅ Successfully scraped: {scraped_data[:60]}...")
        return scraped_data

    except Exception as e:
        error_msg = f"Error: {str(e)[:100]}"
        print(f"  ❌ Scraping failed: {error_msg}")
        return error_msg

# --------------------------------------------------------------
# 5. MAIN SCRAPING SCRIPT
# --------------------------------------------------------------
def run_link_scraper(max_links=None, start_row=None):
    """
    Main function to scrape links from Google Sheets.

    Args:
        max_links: Maximum number of links to process (None for all)
        start_row: Start from a specific row number (None to start from beginning)
    """
    print(f"\n{'='*70}")
    print(f"STARTING LINK SCRAPER - {datetime.datetime.now()}")
    print(f"{'='*70}")

    # Setup Google Sheets
    try:
        worksheet = setup_google_sheets()
    except Exception as e:
        print(f"❌ FAILURE: Could not connect to Google Sheets: {e}")
        return False

    # Get unprocessed links
    unprocessed_links = get_unprocessed_links(worksheet)

    if not unprocessed_links:
        print("\n✅ No unprocessed links found. All done!")
        return True

    # Filter by start_row if specified
    if start_row:
        unprocessed_links = [(row, link) for row, link in unprocessed_links if row >= start_row]
        print(f"📍 Filtering to rows >= {start_row}")

    # Limit number of links if specified
    if max_links:
        unprocessed_links = unprocessed_links[:max_links]
        print(f"📍 Processing first {max_links} links")

    print(f"\n📋 Processing {len(unprocessed_links)} links...\n")

    processed_count = 0
    failed_count = 0

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        page = agentql.wrap(browser.new_page())

        try:
            for idx, (row_number, link) in enumerate(unprocessed_links, 1):
                print(f"\n{'─'*70}")
                print(f"Processing {idx}/{len(unprocessed_links)}")
                print(f"Row {row_number} | Column K Link: {link[:50]}...")
                print(f"{'─'*70}")

                try:
                    # Step 1: Access the link from Column K and scrape it
                    print(f"  📖 Reading link from Column K (row {row_number})")
                    scraped_data = scrape_link(page, link)

                    # Step 2: Determine if successful
                    success = not scraped_data.startswith("Error:")

                    # Step 3: Write result back to Column M
                    print(f"  📝 Writing result to Column M (row {row_number})")
                    if update_row_data(worksheet, row_number, scraped_data, success):
                        if success:
                            processed_count += 1
                            print(f"  ✅ Row {row_number} completed successfully")
                        else:
                            failed_count += 1
                            print(f"  ⚠️  Row {row_number} failed with error")

                    # Rate limiting - be nice to the servers
                    time.sleep(2)

                except Exception as e:
                    print(f"  ❌ Error processing row {row_number}: {e}")
                    traceback.print_exc()

                    # Mark as failed in sheet
                    update_row_data(worksheet, row_number, f"Error: {str(e)[:100]}", success=False)
                    failed_count += 1
                    continue

            # Final report
            print(f"\n{'='*70}")
            print(f"SCRAPING COMPLETE")
            print(f"{'='*70}")
            print(f"✅ Successfully processed: {processed_count}")
            print(f"❌ Failed: {failed_count}")
            print(f"📊 Total: {processed_count + failed_count}")
            print(f"{'='*70}\n")

            return processed_count > 0

        except Exception as e:
            print(f"\n❌ CRITICAL ERROR during scraping: {e}")
            traceback.print_exc()
            return False
        finally:
            print("Closing browser...")
            browser.close()

# --------------------------------------------------------------
# 6. MAIN ENTRY POINT
# --------------------------------------------------------------
def main():
    """Main function."""
    import sys

    # Parse command line arguments
    max_links = None
    start_row = None

    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if arg.startswith("--max="):
                max_links = int(arg.split("=")[1])
            elif arg.startswith("--start="):
                start_row = int(arg.split("=")[1])
            elif arg == "--help":
                print("\nUsage: python link_scraper.py [options]")
                print("\nOptions:")
                print("  --max=N      Process maximum N links")
                print("  --start=N    Start from row N")
                print("  --help       Show this help message")
                print("\nExamples:")
                print("  python link_scraper.py                # Process all unprocessed links")
                print("  python link_scraper.py --max=10       # Process first 10 links")
                print("  python link_scraper.py --start=50     # Start from row 50")
                print("  python link_scraper.py --max=5 --start=10  # Process 5 links starting from row 10")
                return

    success = run_link_scraper(max_links=max_links, start_row=start_row)

    if not success:
        print("\n❌ SCRAPER FAILED")
        sys.exit(1)
    else:
        print("\n✅ SCRAPER SUCCEEDED")
        sys.exit(0)

if __name__ == "__main__":
    main()
