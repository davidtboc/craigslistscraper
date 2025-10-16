# Link Scraper - Google Sheets Link Processor

This script **reads links from Column K** in your Google Sheets, **navigates to each URL**, scrapes data from the page, and **writes results back to Column M**.

## Overview

**Workflow:**
1. Connects to Google Sheets using **same credentials as scraper_rewritten.py** ✅
2. **Reads links from Column K (11)** - "Outreach Link"
3. **Navigates to each URL** from Column K
4. **Scrapes data** from the page (customizable)
5. **Writes results to Column M (13)** - "Scraped Data"
6. **Marks processed** with ✓ in Column N (14) - "Processed"

## Visual Workflow

```
┌────────────────────────────────────────────────────────────────┐
│ Google Sheet (ID: 1Fc0JO91CAvciNYi5LMMUO9K8J_7yzYlp1LUFyOs6PqA)│
├────┬────────┬──────────────────┬────────────┬────────────┬────┤
│Row │  ...   │ Column K         │ Column M   │ Column N   │    │
│    │        │ Outreach Link    │ Scraped    │ Processed  │    │
├────┼────────┼──────────────────┼────────────┼────────────┼────┤
│ 2  │  ...   │ https://nyc...   │            │            │    │
│    │        │      ↓ (access)  │            │            │    │
│    │        │      ↓ (navigate)│            │            │    │
│    │        │      ↓ (scrape)  │            │            │    │
│    │        │                  │ → Result   │ → ✓        │    │
└────┴────────┴──────────────────┴────────────┴────────────┴────┘
```

## Setup

✅ **No additional setup needed!**

The script **reuses credentials from scraper_rewritten.py**:
- Same `.env` file (`AGENTQL_API_KEY`)
- Same `credentials.json` (Google Sheets)
- Same Google Sheet ID

If your first scraper works, this will work automatically!

## Usage

### Basic Usage

Process all unprocessed links:
```bash
python link_scraper.py
```

### Options

```bash
# Process only the first 10 links (good for testing)
python link_scraper.py --max=10

# Start from row 50
python link_scraper.py --start=50

# Process 5 links starting from row 20
python link_scraper.py --max=5 --start=20

# Show help
python link_scraper.py --help
```

## Customization

### What Data to Scrape

The script currently scrapes the page title and main content as a placeholder. You need to customize this based on your needs.

**To customize, edit the `scrape_link()` function in [link_scraper.py](link_scraper.py:120-160):**

#### Example 1: Scrape specific elements with AgentQL

```python
# Define your query at the top of the file (line 38)
SCRAPE_QUERY = """
{
    company_name
    phone_number
    address
    description
}
"""

# In scrape_link() function (around line 138)
result = page.query_elements(SCRAPE_QUERY)
company = result.company_name.inner_text() if hasattr(result, 'company_name') else "N/A"
phone = result.phone_number.inner_text() if hasattr(result, 'phone_number') else "N/A"

scraped_data = f"Company: {company} | Phone: {phone}"
```

#### Example 2: Extract specific information from Craigslist posts

```python
# For Craigslist posts, you can reuse queries from scraper_rewritten.py
GET_POSTING_BODY_QUERY = """
{
    posting_body(element: "#postingbody")
}
"""

# In scrape_link()
body_response = page.query_elements(GET_POSTING_BODY_QUERY)
posting_text = body_response.posting_body.inner_text()

# Extract what you need from posting_text
scraped_data = posting_text[:500]  # First 500 characters
```

#### Example 3: Use Playwright selectors

```python
# In scrape_link()
try:
    # Get specific element by CSS selector
    email_elem = page.locator('a[href*="mailto"]').first
    email = email_elem.get_attribute('href').replace('mailto:', '')

    # Get text content
    price = page.locator('.price').inner_text()

    scraped_data = f"Email: {email} | Price: {price}"
except:
    scraped_data = "Not found"
```

### Change Output Columns

To write results to different columns, edit these constants at the top of [link_scraper.py](link_scraper.py:25-30):

```python
LINK_COLUMN = 11          # Column K - Where to read links FROM
RESULT_COLUMN = 13        # Column M - Where to WRITE results TO
PROCESSED_FLAG_COLUMN = 14  # Column N - Tracking column
```

## Features

### ✅ Smart Processing
- Only processes rows that haven't been processed yet
- Skips rows without links
- Marks completed rows with ✓

### ✅ Error Handling
- Failed scrapes are marked with ❌
- Error messages are written to the result column
- Script continues even if individual links fail

### ✅ Progress Tracking
- Shows progress: "Processing 5/20 - Row 47"
- Final summary with success/failure counts
- Marks rows as processed to avoid re-scraping

### ✅ Rate Limiting
- 2-second delay between requests
- Prevents getting blocked by websites

## Output Format

The script writes data to your Google Sheet:

| ... | Outreach Link | Website | **Scraped Data** | **Processed** |
|-----|---------------|---------|------------------|---------------|
| ... | https://... | ... | Title: ABC Company \| Content: ... | ✓ |
| ... | https://... | ... | Error: HTTP 404 | ❌ |
| ... | https://... | ... | Title: XYZ Corp \| Content: ... | ✓ |

## Common Use Cases

### Use Case 1: Extract additional contact info
Scrape the Craigslist posting links to find additional contact information not captured in the first scraper.

### Use Case 2: Verify data
Visit links to verify that businesses are still active or information is current.

### Use Case 3: Enrich data
Extract additional fields like business hours, social media links, or detailed descriptions.

## Troubleshooting

### "No unprocessed links found"
- Check that Column K has links
- Clear the "Processed" column (Column N) to re-process rows
- Use `--start=N` to start from a specific row

### Scraping fails
- Check that the website is accessible
- Customize the scraping logic for the specific website structure
- Increase timeout in `page.goto()` (line 138)

### Google Sheets errors
- Ensure `credentials.json` is in the same directory
- Verify the service account has edit permissions on the sheet
- Check that the Sheet ID is correct

## Testing

Start with a small batch to test your scraping logic:

```bash
# Test with just 3 links
python link_scraper.py --max=3
```

Check the results in your Google Sheet before processing all links.

## Integration with scraper_rewritten.py

This script is designed to work seamlessly with your existing Craigslist scraper:

1. **Run scraper_rewritten.py** → Populates Column K with Craigslist links
2. **Run link_scraper.py** → Processes those links and adds data to Column M

You can run them sequentially or separately as needed.

## Next Steps

1. **Customize the scraping logic** in `scrape_link()` function based on what data you need
2. **Test with a small batch** using `--max=5`
3. **Review results** in Google Sheets
4. **Run on all links** once you're satisfied with the output

## Support

If you need to modify the script:
- **Scraping logic**: Edit the `scrape_link()` function (line 120+)
- **Column mapping**: Edit constants at top of file (line 25-30)
- **Output format**: Modify how `scraped_data` is formatted in `scrape_link()`
