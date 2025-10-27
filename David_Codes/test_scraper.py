import datetime
import time
from scraper_link import setup_google_sheets, get_todays_outreach_links, PROXY_ENABLED, PROXY_SERVER, PROXY_USERNAME, PROXY_PASSWORD
from playwright.sync_api import sync_playwright

def test_open_first_url():
    """Test to open the first URL from today's date and verify it loads."""
    print("\n🔍 Running test: Open first URL from today's date")
    
    # Step 1: Setup Google Sheets
    worksheet = setup_google_sheets()
    
    # Step 2: Fetch today's links
    todays_links = get_todays_outreach_links(worksheet)
    if not todays_links:
        print("⚠️  No links found for today's date.")
        return
    
    first_link = todays_links[0]
    row_number, url, date_added = first_link
    print(f"✅ Found first link: {url}")
    
    # Step 3: Open the URL using Playwright
    with sync_playwright() as playwright:
        print("🚀 Launching browser...")
        launch_options = {
            "headless": False
        }
        
        if PROXY_ENABLED:
            launch_options["proxy"] = {
                "server": PROXY_SERVER,
                "username": PROXY_USERNAME,
                "password": PROXY_PASSWORD
            }
            print("✅ Proxy configured successfully")
        
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page()
        
        try:
            print(f"🌐 Navigating to URL: {url}")
            page.goto(url, wait_until="domcontentloaded")
            print("✅ Craigslist page loaded successfully.")
            
            print("⏳ Staying on the page for 3 seconds...")
            time.sleep(3)
        except Exception as e:
            print(f"❌ Error loading the page: {e}")
        finally:
            print("🔒 Closing browser...")
            browser.close()
            print("✅ Browser closed.")

if __name__ == "__main__":
    test_open_first_url()
