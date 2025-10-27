import requests
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

def scrape_craigslist_urls(search_url):
    """
    Scrapes all posting URLs from a Craigslist search results page.
    
    Args:
        search_url (str): The URL of the Craigslist search results page.
    """
    
    # Set a User-Agent header to mimic a real browser
    # Craigslist may block requests without a valid User-Agent
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        # Fetch the page content
        response = requests.get(search_url, headers=headers)
        response.raise_for_status()  # Raise an exception for bad status codes (like 404 or 403)

        # Parse the HTML content
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all list items that represent a posting.
        # Based on the page's HTML, postings are <li> elements
        # with the class "cl-static-search-result".
        postings = soup.find_all('li', class_='cl-static-search-result')
        
        if not postings:
            print("No postings found. The page structure may have changed or the request was blocked.")
            return

        print(f"Found {len(postings)} postings. Extracting URLs...\n")

        # Loop through each posting and extract its URL
        for post in postings:
            # The link is in an <a> tag directly inside the list item
            a_tag = post.find('a')
            
            if a_tag and a_tag.has_attr('href'):
                # Get the URL from the 'href' attribute
                url = a_tag['href']
                print(url)

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
        print("Craigslist may be blocking this request. You might need to use more advanced techniques like proxies or browser automation (e.g., Selenium).")
    except requests.exceptions.RequestException as err:
        print(f"An error occurred: {err}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    # The URL from the page you are currently viewing
    URL_TO_SCRAPE = "https://sfbay.craigslist.org/search/jjj?query=cashier"
    
    scrape_craigslist_urls(URL_TO_SCRAPE)