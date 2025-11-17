import time
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options


def scrape_craiglist():
    # --- Configure Chrome ---
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    # ✅ Let Selenium Manager handle ChromeDriver automatically
    driver = webdriver.Chrome(options=options)

    # --- Target URL ---
    URL = "https://newyork.craigslist.org/search/jjj?query=cashier#search=2~thumb~0"
    page = requests.get(URL)
    soup = BeautifulSoup(page.content, "html.parser")

    results = soup.find(id="searchform")
    job_elems = results.find_all("li", class_="result-row")

    # --- Collect listing links ---
    total_amt = 500
    links = []
    for i, job_elem in enumerate(job_elems):
        link = job_elem.find("a")["href"]
        links.append(link)
        if i >= total_amt:
            break

    print(f"🕵️ Found {len(links)} Craigslist resume listings.")

    # --- Scrape emails ---
    with open("test_emails.txt", "w", encoding="utf-8") as file1:
        for idx, link in enumerate(links, start=1):
            print(f"[{idx}/{len(links)}] Visiting: {link}")
            try:
                driver.get(link)
                time.sleep(2)

                # Click the “reply” button
                reply_button = driver.find_element(By.CSS_SELECTOR, "button.reply-button.js-only")
                reply_button.click()
                time.sleep(3)

                html_source = driver.page_source
                soupL = BeautifulSoup(html_source, "html.parser")

                results2 = soupL.find_all("input", class_="anonemail")
                if results2:
                    output = results2[0]["value"]
                    file1.write(output + "\n")
                    print("✅ Saved:", output)
                else:
                    print("⚠️ No email found for:", link)

            except Exception as e:
                print("❌ Error on link:", link, "-", e)
                continue

    driver.quit()
    print("\n✅ Scraping complete! Results saved to test_emails.txt")


if __name__ == "__main__":
    scrape_craiglist()
