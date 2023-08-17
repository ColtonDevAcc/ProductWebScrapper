
import asyncio
import os
import json
import re
from playwright.async_api import async_playwright

SBR_WS_CDP = 'wss://brd-customer-hl_d949117f-zone-scraping_browser:dktuknhdre03@brd.superproxy.io:9222'
LIMIT_PRODUCTS = 10


def parse_nutrition_details(text):
    nutrients = []
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
    serving, nutrients = parse_nutrition_details(
        nutrition_text) if nutrition_text else None, None
    return {
        "Servings": serving,
        "Nutrition": {
            "Nutrients": nutrients
        }
    }


async def extract_product_urls(page):
    product_elements = await page.query_selector_all('div.mb0.ph1')
    urls = []

    for product in product_elements[:LIMIT_PRODUCTS]:
        product_link = await product.query_selector('a')
        if product_link:
            product_url = await product_link.get_attribute('href')
            urls.append(product_url)

    return urls


async def extract_product_details_from_url(page, url):
    await page.goto(url, timeout=2*60_000)
    details = {}

    product_name = await page.query_selector('h1.prod-ProductTitle.prod-productTitle-buyBox.font-bold')
    details['Name'] = await product_name.text_content() if product_name else None

    product_price = await page.query_selector('span.price-group span.price-characteristic')
    details['Price'] = await product_price.text_content() if product_price else None

    nutrition_details = await extract_nutrition_details_from_product_page(page)
    details.update(nutrition_details)

    return details


async def save_product_details_to_file(details):
    output_dir = "Walmart"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    product_name = details['Name'].replace(" ", "_").replace("/", "_")
    output_file_path = os.path.join(output_dir, f"{product_name}.json")

    with open(output_file_path, 'w') as file:
        json.dump(details, file)


async def run(playwright):
    browser = await playwright.chromium.connect_over_cdp(SBR_WS_CDP)
    try:
        page = await browser.new_page()
        await page.goto('https://www.walmart.com/search?q=food', timeout=2*60_000)

        urls = await extract_product_urls(page)
        for url in urls:
            product_details = await extract_product_details_from_url(page, url)
            await save_product_details_to_file(product_details)

    finally:
        await browser.close()


async def main():
    async with async_playwright() as playwright:
        await run(playwright)

if __name__ == '__main__':
    asyncio.run(main())
