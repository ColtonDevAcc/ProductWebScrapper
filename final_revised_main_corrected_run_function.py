
import asyncio
import os
import json
import re
from playwright.async_api import async_playwright

SBR_WS_CDP = 'wss://brd-customer-hl_d949117f-zone-scraping_browser:dktuknhdre03@brd.superproxy.io:9222'
LIMIT_PRODUCTS = 10


def parse_nutrition_details(text):
    nutrients = []

    if not text:
        return {}, nutrients

    lines = text.split('\n')
    for i in range(len(lines)):
        line = lines[i].strip()
        if line.startswith("Amount per serving"):
            serving = {
                "servingSize": re.findall(r"\d+\.?\d*", lines[i+1])[0],
                "servingSizeUnit": re.findall(r"[a-zA-Z]+", lines[i+1])[0],
                "totalServings": 1
            }
        else:
            match = re.match(
                r"(?P<name>\w+).*?(?P<amount>\d+\.?\d*).*?(?P<unit>\w+)?$", line)
            if match:
                nutrient = {
                    "Name": match.group("name"),
                    "Amount": float(match.group("amount")),
                    "Unit": match.group("unit")
                }
                nutrients.append(nutrient)
    return serving, nutrients


async def extract_nutrition_details_from_product_page(page):
    nutrition_section = await page.query_selector('#maincontent > section > main > div.flex.undefined.flex-column.h-100 > div:nth-child(2) > div > div.w_aoqv.w_wRee.w_p0Zv > div > div > section:nth-child(4) > section > div.w_rNem.expand-collapse-content > div')
    nutrition_text = await nutrition_section.text_content() if nutrition_section else None
    serving, nutrients = parse_nutrition_details(nutrition_text)
    return {
        "Servings": serving,
        "Nutrition": {
            "Nutrients": nutrients
        }
    }


async def extract_product_urls(page):
    product_elements = await page.query_selector_all('div.mb0.ph1')
    urls = []

    # New print statement
    print(f"Found {len(product_elements)} product elements...")

    for product in product_elements[:LIMIT_PRODUCTS]:
        product_link = await product.query_selector('a')
        if product_link:
            product_url = await product_link.get_attribute('href')
            urls.append(product_url)

    print(f"Extracted {len(urls)} product URLs...")  # New print statement

    return urls


async def extract_product_details_from_url(page, url):
    print(f'Extracting details for: {url}')
    await page.goto(url, timeout=2*60_000)

    details = {}

    # Identify the <script> tag containing the JSON-LD content
    script_content = await page.query_selector('script[type="application/ld+json"]')
    if script_content:
        json_ld_data = json.loads(await script_content.text_content())
        details['UPC'] = json_ld_data.get("gtin13", None)
        details['Name'] = json_ld_data.get("name", "")
        details['Brand'] = json_ld_data.get("brand", {}).get("name", None)
        details['Image'] = json_ld_data.get("image", None)
        details['Description'] = json_ld_data.get("description", None)

    product_name = await page.query_selector('h1.prod-ProductTitle.prod-productTitle-buyBox.font-bold')
    details['Name'] = await product_name.text_content() if product_name else ""

    product_price = await page.query_selector('span.price-group span.price-characteristic')
    details['Price'] = await product_price.text_content() if product_price else None

    nutrition_details = await extract_nutrition_details_from_product_page(page)

    # Identify the table containing the nutrition facts
    nutrition_table = await page.query_selector('//div[contains(@class, "w_wOcC w_EjQC")]/section/table')
    if nutrition_table:
        nutrition_data = {}
        rows = await nutrition_table.query_selector_all('.//tr')
        for row in rows:
            key_elements = await row.query_selector_all('.//td[1]')
            value_elements = await row.query_selector_all('.//td[2]')
            if key_elements and value_elements:
                key = await key_elements[0].text_content()
                value = await value_elements[0].text_content()
                nutrition_data[key.strip()] = value.strip()
        details['Nutrition'] = nutrition_data

    details.update(nutrition_details)

    return details


async def save_product_details_to_file(details):
    output_dir = "Walmart"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    product_name = details.get('Name', 'Unknown_Product').replace(
        " ", "_").replace("/", "_")
    output_file_path = os.path.join(output_dir, f"{product_name}.json")

    with open(output_file_path, 'w') as file:
        json.dump(details, file)


def extract_actual_url(tracking_url):
    """
    Extract the actual product URL from the tracking URL.
    """
    match = re.search(
        r'rd=(https%3A%2F%2Fwww\.walmart\.com%2Fip%2F[^&]+)', tracking_url)
    if match:
        return match.group(1).replace('%3A', ':').replace('%2F', '/')
    return None


async def run(playwright):
    browser = await playwright.chromium.connect_over_cdp(SBR_WS_CDP)

    try:
        page = await browser.new_page()
        print('Navigating to Walmart search page...')
        await page.goto('https://www.walmart.com/search?q=food', timeout=2*60_000)

        urls = await extract_product_urls(page)

        # Extract actual product URLs from the tracking URLs
        urls = [extract_actual_url(url)
                for url in urls if extract_actual_url(url)]

        # Updated print statement to display the extracted product URLs
        print(f"Extracted product URLs: {urls}")

        print(f"Processing {len(urls)} valid product URLs...")

        for url in urls:
            product_details = await extract_product_details_from_url(page, url)

            print(f'Saving details for {product_details["Name"]} to file...')
            await save_product_details_to_file(product_details)
    except Exception as e:
        print(f'Error encountered during extraction: {e}')
    finally:
        await browser.close()


async def main():
    async with async_playwright() as playwright:
        await run(playwright)

if __name__ == '__main__':
    asyncio.run(main())
