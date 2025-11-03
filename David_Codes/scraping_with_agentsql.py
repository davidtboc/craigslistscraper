#install these libraries:
#pip install agentql playwright pandas openpyxl python-dotenv
#playwright install

import re # Add this to your imports
import sys
import agentql
from playwright.sync_api import sync_playwright
import pandas as pd
import time

from dotenv import load_dotenv

load_dotenv()

def scrape_agentql(playwright):

    target_url = input("Please enter the Craigslist search results URL you want to scrape: ")

    if not target_url:
        print("No URL provided. Exiting.")
        sys.exit()

    page_nr = 0

    #initiate the browser
    browser = playwright.chromium.launch_persistent_context(
        user_data_dir=r"C:\playwright",
        channel="chrome",
        headless=False,
        no_viewport=True,
    )

    data = []
    all_items = [] # Stores data from the detail pages (final output)

    page = agentql.wrap(browser.new_page())

    page.goto(target_url)

    # use your own words to describe what you're looking for
        # 1. The date, with formatting instruction
            # AgentQL can extract and format the timestamp (e.g., "20m ago") 
            # into the requested YYYY-MM-DD format.
        # 2. The location above the blue text (e.g., "White plains") 
        # 3. The hyperlink marked by the blue text
        # This will capture the job title (text) and its URL (href)

    QUERY = """
    {
        listings[] {
            post_date(format: "YYYY-MM-DD")
            location
            title_link {
                text
                href
            }
            http
        }
    }
        """

    # query_data returns data from the page
    response = page.query_data(QUERY)


    for listing in response['listings']:
        item = {
            'Date': listing.get('post_date'),
            'Location': listing.get('location'),
            'Title': listing['title_link'].get('text'),
            'URL': listing['title_link'].get('href')
        }
        data.append(item)

    for job in data:
        
        # Navigate to the job's URL
        page.goto(job['URL'])
        time.sleep(2) # Give the detail page time to load
        
        # Initialize item with basic data
        detail_item = {
            "Date": job['Date'],
            "Location": job['Location'],
            "Title": job['Title'],
            "URL": job["URL"],
            "Description": "",
            "ReplyEmail": ""
            "PhoneNumber" ""
        }

        # New AgentQL query for the detail page
        # Describe the elements you want to extract from the *specific* job page
        DETAIL_QUERY = """
        {
            email(format: @craigslist.org)
            phone_number()
        }
        """
        
        # --- Description Extraction (Needed before Phone Check) ---
        DETAIL_QUERY = """
        {
            # Scrape the main body text so we can search it for a phone number
            full_description(selector: "The main body of the job description")
        }
        """
        
        description_text = "N/A"
        try:
            detail_response = page.query_data(DETAIL_QUERY)
            description_text = detail_response.get("full_description", "N/A")
            detail_item["Description"] = description_text
        except Exception:
             detail_item["Description"] = "Error during description scraping."

        # --- NEW: Phone Number Check using Regex ---
        # This regex covers formats like (XXX) XXX-XXXX, XXX-XXX-XXXX, and XXXXXXXXXX.
        # It's flexible with spaces, dashes, and parentheses.
        phone_regex = r'(\(\d{3}\)\s*|\d{3}-)\d{3}[-\s]?\d{4}|\d{10}'
        
        match = re.search(phone_regex, description_text)
        
        if match:
            # If a match is found, store the first occurrence
            detail_item["PhoneNumber"] = match.group(0).strip()
            print(f"  Extracted Phone: {detail_item['PhoneNumber']}")
        else:
            # If no match, the field remains empty (or "N/A")
            detail_item["PhoneNumber"] = "N/A - No Phone Found"
            
        # --- Email Extraction Logic (Remains the same) ---
        try:
            # 1. Click the main "reply" button
            print("  Checking for Email...")
            reply_btn = page.get_by_prompt("the purple reply button")
            if reply_btn:
                reply_btn.click()
                time.sleep(1.5) 

                # 2. Scrape the unique job-specific email address
                EMAIL_QUERY = """
                {
                    job_email(selector: "The unique job poster email address with the formaat ...@job.craigslist.org")
                }
                """
                email_response = page.query_data(EMAIL_QUERY)
                detail_item["ReplyEmail"] = email_response.get("job_email", "N/A - Email Not Found")
                print(f"  Extracted Email: {detail_item['ReplyEmail']}")
            else:
                detail_item["ReplyEmail"] = "N/A - Reply Button Missing"

        except Exception as e:
            print(f"  Could not extract email. Error: {e}")
            detail_item["ReplyEmail"] = "Error during email extraction."

        # --- Final step: Save the completed item ---
        all_items.append(detail_item)

    return data



with sync_playwright() as playwright:
    products = scrape_agentql(playwright)

    df = pd.DataFrame(products)
    df.to_excel("agentql_products.xlsx",index=False)