#These are requirements to run the scraper
#pip install patchright
#patchright install chromium

import sys
from patchright.sync_api import sync_playwright
import pandas as pd
import time

target_url = input("Please enter the URL you want to scrape: ")

if not target_url:
    print("No URL provided. Exiting.")
    sys.exit()

def scrape_indeed(playwright):
    browser = playwright.chromium.launch_persistent_context(
        user_data_dir="C:\playwright",
        channel="chrome",
        headless=False,
        no_viewport=True,
    )


    page = browser.new_page()


    page_count = 0

    jobs = []



    while page_count < 2:

        print("SCRAPING LIST ITEMS")

        page.goto(target_url)

        time.sleep(10)
        
        craigslist_posts = page.locator('.posting-title')

        for post in craigslist_posts.element_handles():
            item = {}

            item['Title'] = post.inner_text()
            item['URL'] = post.get_attribute("href")

            jobs.append(item)
    
        page_count += 1
        print(f"Title: {item['Title']}, URL: {item['URL']}")

    all_items = []

    for job in jobs[:20]:

        print("SCRAPING DETAILS PAGE")

        
        page.goto(job['URL'])

        time.sleep(4)

        item = {}

        item["Title"] = job['Title']
        item["URL"] = job["URL"]
        item["CompanyName"] = ""
        item["Location"] = ""

        #company_name = page.get_by_test_id("inlineHeader-companyName")

        # 3️⃣ Click the "Reply" button
        reply_button = page.locator('button.reply-button.js-only')
        if reply_button.count() > 0:
            reply_button.first.click()
            time.sleep(4)  # wait for modal to appear
            
            # 4️⃣ Click the "Email" option
            email_button = page.locator('button.reply-option-header >> text=email')
            if email_button.count() > 0:
                email_button.first.click()
                time.sleep(4)  # wait for email input to appear
                
                # 5️⃣ Grab the email from the input field
                email_input = page.locator('input')  # Craigslist usually puts the email in an input field
                if email_input.count() > 0:
                    item["Email"] = email_input.input_value()  # read the email text
        
        # 6️⃣ Add the item to your results
        all_items.append(item)


    browser.close()

    return all_items



with sync_playwright() as playwright:
    jobs = scrape_indeed(playwright)

    df = pd.DataFrame(jobs)
    df.to_excel("jobs.xlsx",index=False)