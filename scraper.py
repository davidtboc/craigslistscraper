import os
import urllib.parse
import agentql
from playwright.sync_api import sync_playwright
from pyairtable import Api
from dotenv import load_dotenv
import json
import requests  # Needed for webhook

# --------------------------------------------------------------
# Load environment variables from .env file.
# --------------------------------------------------------------
load_dotenv()

USER_NAME = os.getenv('EMAIL')
PASSWORD = os.getenv('PASSWORD')
os.environ["AGENTQL_API_KEY"] = os.getenv('AGENTQL_API_KEY')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # Make sure this is in your .env!

# --------------------------------------------------------------
# STEP 1: Article URL we want to redirect to post-login
# --------------------------------------------------------------
ARTICLE_URL = "https://www.bizjournals.com/southflorida/news/2025/08/28/nurock-proposes-affordable-housing-in-wellington.html"

# --------------------------------------------------------------
# STEP 2: URL encode the path portion for the `r=` param
# --------------------------------------------------------------
parsed = urllib.parse.urlparse(ARTICLE_URL)
encoded_path = urllib.parse.quote(parsed.path)

# --------------------------------------------------------------
# STEP 3: Construct login URL with encoded redirect
# --------------------------------------------------------------
LOGIN_URL = f"https://www.bizjournals.com/southflorida/login?r={encoded_path}#/"

# --------------------------------------------------------------
# STEP 4: AgentQL queries
# --------------------------------------------------------------
EMAIL_INPUT_QUERY = """
{
    login_form{
        email_input
        next_btn
    }
}
"""

PASSWORD_INPUT_QUERY = """
{
    login_form{
        password_input
        next_btn
    }
}
"""

# --------------------------------------------------------------
# STEP 5: Playwright script with AgentQL + browser console logging
# --------------------------------------------------------------
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=False)
    page = agentql.wrap(browser.new_page())

    # Navigate to login URL
    page.goto(LOGIN_URL)

    # Email step
    response = page.query_elements(EMAIL_INPUT_QUERY)
    response.login_form.email_input.fill(USER_NAME)
    page.wait_for_timeout(1000)
    response.login_form.next_btn.click()

    # Password step
    password_response = page.query_elements(PASSWORD_INPUT_QUERY)
    password_response.login_form.password_input.fill(PASSWORD)
    page.wait_for_timeout(1000)
    password_response.login_form.next_btn.click()

    # Save login session
    page.context.storage_state(path="sfbj_login.json")

    # Wait for redirect to article page
    page.wait_for_url(ARTICLE_URL, timeout=15000)
    page.wait_for_load_state("domcontentloaded")

    # Scrape content from <p class="content">
    paragraphs = page.locator("p.content").all_text_contents()
    full_text = "\n\n".join(paragraphs)

    # Log to browser console – pass as argument!
    page.evaluate(
        'text => console.log("----- ARTICLE CONTENT -----\\n" + text + "\\n----- END OF ARTICLE -----")',
        full_text
    )

    # Send to production n8n webhook
    try:
        response = requests.post(WEBHOOK_URL, json={
            "article_url": ARTICLE_URL,
            "article_text": full_text
        })
        print("Webhook sent. Status:", response.status_code)
    except Exception as e:
        print("Failed to send webhook:", str(e))

    # Keep browser open briefly to see console
    page.wait_for_timeout(1000000)
