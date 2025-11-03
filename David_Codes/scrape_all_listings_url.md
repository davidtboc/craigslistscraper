Here is the PRD converted to Markdown, with the requested libraries added.

PRD: Python Craigslist URL Scraper
1. Project Overview
Goal: Create a command-line Python script that prompts a user for a Craigslist search results URL, scrapes the first 20 individual listing URLs from that page, and saves the extracted URLs into a JSON file.

2. Key Requirements
R-1: The script must prompt the user in the terminal to provide a URL.

R-2: The script must print a confirmation message after the user provides the URL.

R-3: The script must fetch the HTML content of the provided URL.

R-4: The script must parse the HTML to find all listing links, specifically targeting the <a> tags with the class posting-title.

R-5: The script must extract the href attribute (the URL) from a maximum of 20 listing links.

R-6: The script must store the list of extracted URLs in a JSON file named listings.json.

3. Technical Stack & Dependencies
Language: Python 3.8+

Libraries:

requests: For making HTTP requests to fetch the page HTML.

beautifulsoup4: For parsing the HTML and extracting data.

lxml: A high-performance parser for BeautifulSoup.

json: (Python standard library) For writing the output file.

selenium: (Added per request) For browser automation.

gspread: (Added per request) For interacting with Google Sheets.

playwright: (Added per request) For browser automation.

4. Actionable Task Checklist
Here is the detailed, step-by-step implementation plan.

Phase 1: Project Setup & Environment
[ ] Task 1.1: Create a new project directory.

Bash

mkdir craigslist_scraper
cd craigslist_scraper
[ ] Task 1.2: Create a Python virtual environment.

Bash

python3 -m venv venv
[ ] Task 1.3: Activate the virtual environment.

macOS/Linux: source venv/bin/activate

Windows: .\venv\Scripts\activate

[ ] Task 1.4: Create a requirements.txt file.

Bash

touch requirements.txt
[ ] Task 1.5: Add the required libraries to requirements.txt.

Plaintext

requests
beautifulsoup4
lxml
selenium
gspread
playwright
[ ] Task 1.6: Install the dependencies.

Bash

pip install -r requirements.txt
[ ] Task 1.7: Install Playwright's browser binaries.

Bash

playwright install
[ ] Task 1.8: Create the main Python script file.

Bash

touch scraper.py
Phase 2: Python Script (scraper.py) Implementation
[ ] Task 2.1: Import Libraries

At the top of scraper.py, add the necessary imports.

Python

import requests
import json
from bs4 import BeautifulSoup
import sys

# Imports added as per request
from selenium import webdriver
import gspread
from playwright.sync_api import sync_playwright
[ ] Task 2.2: Define the Main Function

Define a main() function that will hold the primary logic.

Python

def main():
    # Logic will go here
    pass

if __name__ == "__main__":
    main()
[ ] Task 2.3: Prompt for URL (R-1)

Inside main(), prompt the user for the URL and store it.

Python

def main():
    search_url = input("Please paste the Craigslist search URL: ")
    # ... rest of the logic
[ ] Task 2.4: Validate and Confirm (R-2)

Add validation to check if the URL is provided and looks like a Craigslist link. Print confirmation.

Python

def main():
    search_url = input("Please paste the Craigslist search URL: ")

    if not search_url or "craigslist.org" not in search_url:
        print("Invalid URL. Please provide a valid Craigslist search link.")
        sys.exit(1)

    print(f"\n[INFO] Starting scrape for: {search_url}")
    # ... rest of the logic
[ ] Task 2.5: Fetch HTML (R-3)

Add logic to fetch the page content using requests. Include a User-Agent header to mimic a browser.

Python

# Inside main(), after the print statement:

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36'
}
try:
    response = requests.get(search_url, headers=headers)
    response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)
    print("[INFO] Page fetched successfully.")
except requests.exceptions.RequestException as e:
    print(f"[ERROR] Could not fetch page: {e}")
    sys.exit(1)
[ ] Task 2.6: Parse HTML & Extract Links (R-4, R-5)

Use BeautifulSoup to parse the HTML.

Find all <a> tags with the class posting-title.

Limit the results to 20.

Loop through the tags and extract the href attribute.

Python

# Inside main(), inside the try block, after fetching the response:

soup = BeautifulSoup(response.text, 'lxml')
extracted_links = []

# Find all <a> tags with the class 'posting-title' and limit to 20
listing_tags = soup.find_all('a', class_='posting-title', limit=20)

print(f"[INFO] Found {len(listing_tags)} links.")

for link_tag in listing_tags:
    url = link_tag.get('href')
    if url:
        extracted_links.append(url)
[ ] Task 2.7: Save to JSON (R-6)

Write the extracted_links list to a file named listings.json.

Python

# Inside main(), at the end of the try block:

output_filename = 'listings.json'
with open(output_filename, 'w') as f:
    json.dump(extracted_links, f, indent=4)

print(f"\n[SUCCESS] Successfully saved {len(extracted_links)} links to {output_filename}")
Phase 3: Execution and Verification
[ ] Task 3.1: Run the script from your terminal.

Bash

python scraper.py
[ ] Task 3.2: When prompted, paste the example URL: https://sfbay.craigslist.org/search/jjj?query=cashier#search=2~thumb~0

[ ] Task 3.3: Verify the terminal output. It should show:

The confirmation message.

"Page fetched successfully."

"Found 20 links." (or fewer, if the page has less)

"[SUCCESS] Successfully saved 20 links to listings.json"

[ ] Task 3.4: Check your project directory for listings.json.

[ ] Task 3.5: Open listings.json and confirm it contains a JSON array of URLs.