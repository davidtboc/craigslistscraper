from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
import time
import gspread
from google.oauth2.service_account import Credentials

def scrape_craigslist_links(url):
    """
    Scrape job posting links from a Craigslist search results page.
    
    Args:
        url: The Craigslist search results URL
        
    Returns:
        List of job posting URLs
    """
    # Set up Selenium driver
    driver = webdriver.Chrome()  # or webdriver.Firefox()
    links = []
    
    try:
        # Navigate to the page
        driver.get(url)
        
        # Wait for results to load
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "cl-search-result")))
        
        # Give page a moment to fully render
        time.sleep(2)
        
        # Get page source and parse with BeautifulSoup
        soup = BeautifulSoup(driver.page_source, 'lxml')
        
        # Find all anchor tags with the posting links
        # Looking for: <a class="cl-app-anchor text-only result-thumb" href="...">
        anchors = soup.find_all('a', class_='text-only')
        
        # Extract href attributes from anchors that have "result-thumb" class
        for anchor in anchors:
            classes = anchor.get('class', [])
            if 'result-thumb' in classes or 'posting-title' in classes:
                href = anchor.get('href')
                if href and '/d/' in href:  # Craigslist posting URLs contain '/d/'
                    # Make sure it's a full URL
                    if not href.startswith('http'):
                        href = 'https://sfbay.craigslist.org' + href
                    links.append(href)
        
        print(f"Found {len(links)} job posting links")
        
    except Exception as e:
        print(f"Error scraping page: {e}")
    
    finally:
        # Clean up
        driver.quit()
    
    return links


def export_to_google_sheets(links, sheet_name, credentials_file='credentials.json'):
    """
    Export scraped links to Google Sheets.
    
    Args:
        links: List of URLs to export
        sheet_name: Name of the Google Sheet to write to
        credentials_file: Path to your Google Service Account JSON credentials
    """
    try:
        # Define the scope
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        
        # Authenticate using service account credentials
        creds = Credentials.from_service_account_file(credentials_file, scopes=scope)
        client = gspread.authorize(creds)
        
        # Open the sheet (or create if it doesn't exist)
        try:
            sheet = client.open(sheet_name).sheet1
        except gspread.SpreadsheetNotFound:
            spreadsheet = client.create(sheet_name)
            sheet = spreadsheet.sheet1
            print(f"Created new spreadsheet: {sheet_name}")
        
        # Clear existing data
        sheet.clear()
        
        # Add headers
        sheet.update('A1', [['Index', 'Job Posting URL', 'Timestamp']])
        
        # Prepare data with timestamp
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        data = [[i, link, timestamp] for i, link in enumerate(links, 1)]
        
        # Write data to sheet
        if data:
            sheet.update(f'A2:C{len(data) + 1}', data)
            print(f"Successfully exported {len(links)} links to Google Sheets")
        else:
            print("No links to export")
            
    except Exception as e:
        print(f"Error exporting to Google Sheets: {e}")


def copy_links_to_clipboard(links, delay=5):
    """
    Copy links to clipboard one at a time using Selenium.
    Uses JavaScript to copy to clipboard.
    
    Args:
        links: List of URLs to copy
        delay: Seconds to wait between copying each link
    """
    if not links:
        print("No links to copy")
        return
    
    print(f"\nCopying {len(links)} links to clipboard using Selenium...")
    print(f"Each link will be copied with a {delay} second delay")
    print("Press Ctrl+C to stop\n")
    
    driver = webdriver.Chrome()
    
    try:
        # Navigate to a blank page
        driver.get("data:text/html,<html><body></body></html>")
        
        for i, link in enumerate(links, 1):
            # Use JavaScript to copy text to clipboard
            driver.execute_script(f"""
                const text = arguments[0];
                navigator.clipboard.writeText(text).then(function() {{
                    console.log('Copied to clipboard');
                }}, function(err) {{
                    console.error('Could not copy text: ', err);
                }});
            """, link)
            
            print(f"[{i}/{len(links)}] Copied: {link}")
            
            if i < len(links):  # Don't wait after the last link
                time.sleep(delay)
    
    except KeyboardInterrupt:
        print("\n\nStopped by user")
    except Exception as e:
        print(f"Error copying to clipboard: {e}")
    finally:
        driver.quit()


def add_links_to_spreadsheet_column_k(links, spreadsheet_id, credentials_file='credentials.json'):
    """
    Add links to column K of a specific Google Spreadsheet.
    Each link will be added to a new row in column K.
    
    Args:
        links: List of URLs to add
        spreadsheet_id: The ID of the Google Spreadsheet
        credentials_file: Path to your Google Service Account JSON credentials
    """
    try:
        # Define the scope
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        
        # Authenticate using service account credentials
        creds = Credentials.from_service_account_file(credentials_file, scopes=scope)
        client = gspread.authorize(creds)
        
        # Open the spreadsheet by ID
        spreadsheet = client.open_by_key(spreadsheet_id)
        
        # Get the first sheet (or specify sheet name if needed)
        sheet = spreadsheet.get_worksheet(0)  # First sheet
        
        # Find the next empty row in column K
        col_k_values = sheet.col_values(11)  # Column K is the 11th column
        next_row = len(col_k_values) + 1
        
        print(f"\nAdding {len(links)} links to column K starting at row {next_row}")
        
        # Prepare data for column K
        data = [[link] for link in links]
        
        # Write data to column K
        if data:
            end_row = next_row + len(data) - 1
            sheet.update(f'K{next_row}:K{end_row}', data)
            print(f"Successfully added {len(links)} links to column K (rows {next_row}-{end_row})")
        else:
            print("No links to add")
            
    except Exception as e:
        print(f"Error adding links to spreadsheet: {e}")
        print("Make sure you've shared the spreadsheet with your service account email")


# Example usage
if __name__ == "__main__":
    # Replace with your actual Craigslist search URL
    search_url = "https://sfbay.craigslist.org/search/fbh#search=2~thumb~0"
    
    job_links = scrape_craigslist_links(search_url)
    
    # Print all found links
    print("\n" + "="*60)
    print("FOUND LINKS:")
    print("="*60)
    for i, link in enumerate(job_links, 1):
        print(f"{i}. {link}")
    
    # Add links to column K of your Google Spreadsheet
    if job_links:
        print("\n" + "="*60)
        spreadsheet_id = "1Fc0JO91CAvciNYi5LMMUO9K8J_7yzYlp1LUFyOs6PqA"
        add_links_to_spreadsheet_column_k(job_links, spreadsheet_id)