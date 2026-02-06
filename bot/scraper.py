# -*- coding: utf-8 -*-
"""
Scraper for Fab.com - Seller and Product pages
"""
import random
import asyncio
import re
import os
from datetime import datetime
from typing import Optional

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import json
from loguru import logger

# pyvirtualdisplay only on Linux
IS_WINDOWS = os.name == 'nt'
if not IS_WINDOWS:
    try:
        from pyvirtualdisplay import Display
    except ImportError:
        Display = None
else:
    Display = None

from .config import (
    FAB_BASE_URL,
    SCRAPE_RETRY_COUNT,
    SCRAPE_DELAY_MIN,
    SCRAPE_DELAY_MAX,
    PAGE_LOAD_TIMEOUT,
    SCROLL_DELAY,
    DEFAULT_CURRENCY,
    CURRENCY_LOCALES
)


def _clean_text(s: str) -> str:
    """Cleans text by removing multiple spaces."""
    return re.sub(r"\s+", " ", s or "").strip()


async def _random_delay():
    """Random delay between requests to avoid rate limiting."""
    await asyncio.sleep(random.uniform(SCRAPE_DELAY_MIN, SCRAPE_DELAY_MAX))


async def get_seller_products_list(seller_url: str, retries: int = SCRAPE_RETRY_COUNT, currency: str = DEFAULT_CURRENCY) -> Optional[list[dict]]:
    """
    Scrapes the seller page to get the list of products.
    
    Args:
        seller_url: Seller page URL (e.g. https://fab.com/sellers/GameAssetFactory)
        retries: Number of retries on failure
        
    Returns:
        List of dictionaries with {name, price, url, image} or None on error
    """
    # Display only on Linux without DISPLAY
    display = None
    if Display and not IS_WINDOWS and not os.getenv("DISPLAY"):
        try:
            display = Display()
            display.start()
        except Exception:
            display = None
    
    try:
        for attempt in range(1, retries + 1):
            try:
                async with async_playwright() as p:
                    # Set locale based on currency
                    currency_settings = CURRENCY_LOCALES.get(currency, CURRENCY_LOCALES[DEFAULT_CURRENCY])
                    
                    browser = await p.firefox.launch(
                        headless=True,
                        args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
                    )
                    
                    context = await browser.new_context(
                        locale=currency_settings["locale"],
                        timezone_id=currency_settings["timezone"]
                    )
                    page = await context.new_page()
                    
                    logger.info(f"Loading seller page: {seller_url}")
                    await page.goto(seller_url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
                    await asyncio.sleep(2.0)
                    
                    # Scroll to load all products (dynamic infinite scroll)
                    previous_height = 0
                    
                    while True:
                        current_height = await page.evaluate("document.body.scrollHeight")
                        if current_height == previous_height:
                            break
                        previous_height = current_height
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await asyncio.sleep(SCROLL_DELAY)
                    
                    content = await page.content()
                    soup = BeautifulSoup(content, "html.parser")
                    
                    products = []
                    seen_urls = set()
                    
                    # Search for product cards in the grid
                    # Structure: <a> with href="/listings/..." containing image and text
                    for link in soup.find_all("a", href=lambda h: h and h.startswith("/listings/")):
                        product_url = FAB_BASE_URL + link["href"]
                        
                        if product_url in seen_urls:
                            continue
                        seen_urls.add(product_url)
                        
                        # Extract product ID from URL
                        product_id = link["href"].replace("/listings/", "").split("?")[0]
                        
                        # Search for card parent container
                        card = link.find_parent("li") or link.find_parent("div")
                        
                        # Product Name
                        name = None
                        # Search in text elements of the card
                        for text_elem in (card or link).find_all(["h2", "h3", "h4", "span", "p", "div"]):
                            text = _clean_text(text_elem.get_text())
                            # Ignore prices and short texts
                            if text and len(text) > 3 and not text.startswith("From") and not text.startswith("€") and not text.startswith("$"):
                                if not any(c.isdigit() for c in text[:3]):  # Avoid prices
                                    name = text
                                    break
                        
                        if not name:
                            name = _clean_text(link.get_text(" ", strip=True)) or None
                        
                        # Price
                        price = None
                        price_pattern = re.compile(r"From\s*[€$£]?\s*[\d.,]+", re.IGNORECASE)
                        for text_elem in (card or link).find_all(text=True):
                            text = str(text_elem).strip()
                            if price_pattern.search(text) or text.startswith("€") or text.startswith("$"):
                                price = _clean_text(text)
                                break
                        
                        # Image
                        img_tag = (card or link).find("img")
                        image = None
                        if img_tag:
                            image = img_tag.get("src") or img_tag.get("data-src")
                            if image:
                                if image.startswith("//"):
                                    image = "https:" + image
                                elif image.startswith("/"):
                                    image = FAB_BASE_URL + image
                        
                        products.append({
                            "id": product_id,
                            "name": name,
                            "price": price,  # None if not available
                            "url": product_url,
                            "image": image
                        })
                    
                    await browser.close()
                    
                    if not products:
                        logger.warning(f"No products found on {seller_url}")
                        return []
                    
                    logger.info(f"Found {len(products)} products on {seller_url}")
                    return products
                    
            except Exception as e:
                logger.error(f"Seller scraping error (attempt {attempt}/{retries}): {e}")
                await asyncio.sleep(random.uniform(5, 10))
        
        logger.error(f"Seller scraping failed after {retries} attempts")
        return None
        
    finally:
        if display:
            display.stop()


async def get_product_details(product_url: str, retries: int = SCRAPE_RETRY_COUNT) -> Optional[dict]:
    """
    Visits the product page to retrieve details.
    
    Args:
        product_url: Product URL (e.g. https://fab.com/listings/xxx)
        retries: Number of retries on failure
        
    Returns:
        Dictionary with {last_update, description, reviews_count} or None
    """
    # Display only on Linux without DISPLAY
    display = None
    if Display and not IS_WINDOWS and not os.getenv("DISPLAY"):
        try:
            display = Display()
            display.start()
        except Exception:
            display = None
    
    try:
        for attempt in range(1, retries + 1):
            try:
                async with async_playwright() as p:
                    browser = await p.firefox.launch(
                        headless=True,
                        args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
                    )
                    page = await browser.new_page()
                    
                    logger.info(f"Loading product page: {product_url}")
                    await page.goto(product_url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
                    await asyncio.sleep(2.0)
                    
                    # Scroll to bottom to trigger lazy loading
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1.0)
                    
                    content = await page.content()
                    soup = BeautifulSoup(content, "html.parser")
                    
                    details = {
                        "last_update": None,
                        "published": None,
                        "description": None,
                        "reviews_count": 0,
                        "image": None,
                        "price": None
                    }
                    
                    # Search for main product image
                    # Method 1: meta og:image
                    og_image = soup.find("meta", property="og:image")
                    if og_image and og_image.get("content"):
                        details["image"] = og_image["content"]
                    
                    # Method 2: Search in carousel/gallery images
                    if not details["image"]:
                        for img in soup.find_all("img"):
                            src = img.get("src") or img.get("data-src")
                            if src and ("cdn" in src or "fab.com" in src) and not "avatar" in src.lower():
                                if src.startswith("//"):
                                    src = "https:" + src
                                details["image"] = src
                                break
                    
                    # Search for price
                    # Method 1: JSON Data (most reliable for licensed products)
                    # Extract product ID from URL
                    product_id = product_url.split("/listings/")[-1].split("?")[0]
                    
                    for script in soup.find_all("script"):
                        if not script.string:
                            continue
                        try:
                            data = json.loads(script.string)
                            # Navigate to entities -> listings -> ID -> startingPrice
                            # Possible paths: .initialState.entities... or just root
                            
                            entities = data.get("initialState", {}).get("entities", {}) or data.get("entities", {})
                            listing = entities.get("listings", {}).get(product_id, {})
                            
                            if listing:
                                # Check for multiple licenses
                                licenses = listing.get("licenses", [])
                                if licenses and len(licenses) > 1:
                                    price_parts = []
                                    for lic in licenses:
                                        name = lic.get("name")
                                        price_val = lic.get("priceTier", {}).get("price")
                                        currency = lic.get("priceTier", {}).get("currencyCode", "USD")
                                        if name and price_val is not None:
                                            symbol = "€" if currency == "EUR" else "$"
                                            price_parts.append(f"{name}: {price_val}{symbol}")
                                    
                                    if price_parts:
                                        details["price"] = "\n".join(price_parts)
                                        break

                                # Fallback to startingPrice
                                starting_price = listing.get("startingPrice")
                                if starting_price and starting_price.get("price") is not None:
                                    currency = starting_price.get("currencyCode", "USD")
                                    symbol = "€" if currency == "EUR" else "$"
                                    details["price"] = f"{starting_price['price']}{symbol}"
                                    break
                                
                                # Try price (simple)
                                if listing.get("price") is not None:
                                    details["price"] = f"{listing.get('price')}$" # Default symbol if currency missing
                                    break

                        except json.JSONDecodeError:
                            continue

                    # Method 2: meta og:price (fallback)
                    if not details["price"]:
                        og_price = soup.find("meta", property="product:price:amount")
                        if og_price and og_price.get("content"):
                            currency = soup.find("meta", property="product:price:currency")
                            currency_symbol = "€" if currency and currency.get("content") == "EUR" else "$"
                            details["price"] = f"{og_price['content']}{currency_symbol}"
                    
                    # Get page text for other extractions
                    page_text = soup.get_text()
                    
                    # Method 2: Search for price text in page
                    if not details["price"]:
                        price_match = re.search(r"[€$][\d.,]+", page_text)
                        if price_match:
                            val = price_match.group(0)
                            if val.startswith("€") or val.startswith("$"):
                                val = val[1:] + val[0]
                            details["price"] = val
                    
                    # Last update pattern: "Last update" followed by a date
                    last_update_match = re.search(
                        r"Last\s+update\s*[:\s]*([A-Za-z]+\s+\d{1,2},?\s*\d{4})",
                        page_text,
                        re.IGNORECASE
                    )
                    if last_update_match:
                        details["last_update"] = last_update_match.group(1).strip()
                    
                    # Published date
                    published_match = re.search(
                        r"Published\s*[:\s]*([A-Za-z]+\s+\d{1,2},?\s*\d{4})",
                        page_text,
                        re.IGNORECASE
                    )
                    if published_match:
                        details["published"] = published_match.group(1).strip()
                    
                    
                    # Description (Overview tab)
                    description_section = soup.find("h2", string=re.compile(r"description", re.IGNORECASE))
                    if description_section:
                        desc_parent = description_section.find_parent("div") or description_section.find_parent("section")
                        if desc_parent:
                            details["description"] = _clean_text(desc_parent.get_text(" ", strip=True))[:1000]
                    else:
                        # Search directly for description text
                        for div in soup.find_all("div"):
                            text = _clean_text(div.get_text())
                            if len(text) > 100 and "set" in text.lower() or "pack" in text.lower():
                                details["description"] = text[:1000]
                                break
                    
                    # Reviews count and rating - format: "Average rating X.X out of 5, total ratings N"
                    # Extract rating (note sur 5)
                    rating_match = re.search(r"Average rating\s*([\d.]+)\s*out of 5", page_text, re.IGNORECASE)
                    if rating_match:
                        details["rating"] = float(rating_match.group(1))
                    else:
                        details["rating"] = None
                    
                    # Extract reviews count
                    reviews_match = re.search(r"total ratings?\s*(\d+)", page_text, re.IGNORECASE)
                    if reviews_match:
                        details["reviews_count"] = int(reviews_match.group(1))
                    else:
                        # Fallback: try other patterns
                        reviews_match2 = re.search(r"(\d+)\s*review", page_text, re.IGNORECASE)
                        if reviews_match2:
                            details["reviews_count"] = int(reviews_match2.group(1))
                        elif "No reviews yet" in page_text or "No rating yet" in page_text:
                            details["reviews_count"] = 0
                    
                    await browser.close()
                    
                    logger.info(f"Details retrieved for {product_url}: last_update={details['last_update']}")
                    return details
                    
            except Exception as e:
                logger.error(f"Product scraping error (attempt {attempt}/{retries}): {e}")
                await asyncio.sleep(random.uniform(5, 10))
        
        logger.error(f"Product scraping failed after {retries} attempts")
        return None
        
    finally:
        if display:
            display.stop()


def detect_changes(old_products: list, new_products: list) -> dict:
    """
    Compares old and new products to detect changes.
    
    Args:
        old_products: List of cached products
        new_products: List of newly scraped products
        
    Returns:
        Dict with "new" (new products) and "updated" (updated products)
    """
    changes = {
        "new": [],
        "updated": []
    }
    
    # Create dict of old products by ID
    old_by_id = {p["id"]: p for p in (old_products or [])}
    
    for new_product in (new_products or []):
        product_id = new_product.get("id")
        
        if product_id not in old_by_id:
            # New product
            changes["new"].append(new_product)
        else:
            # Check if product updated
            old_product = old_by_id[product_id]
            
            # Compare last_update
            old_update = old_product.get("last_update")
            new_update = new_product.get("last_update")
            
            if new_update and old_update != new_update:
                changes["updated"].append({
                    **new_product,
                    "previous_update": old_update
                })
            # Compare price too
            elif old_product.get("price") != new_product.get("price"):
                changes["updated"].append({
                    **new_product,
                    "previous_price": old_product.get("price")
                })
    
    return changes


async def scrape_seller_with_details(seller_url: str, existing_products: list = None, progress_callback=None, currency: str = DEFAULT_CURRENCY) -> Optional[dict]:
    """
    Complete seller scraping: product list + details for each product.
    
    Args:
        seller_url: Seller URL
        existing_products: List of existing cached products (for optimization)
        progress_callback: Async function(current, total, product_name) to report progress
        currency: Currency code (USD, EUR, GBP)
        
    Returns:
        Dict with "products" and "changes" or None on error
    """
    # Phase 1: Get product list
    products = await get_seller_products_list(seller_url, currency=currency)
    
    if products is None:
        return None
    
    if not products:
        return {"products": [], "changes": {"new": [], "updated": []}}
    
    # Create dict of existing products by ID
    existing_by_id = {p["id"]: p for p in (existing_products or [])}
    
    # Phase 2: Get details for each product (only if new or potentially modified)
    enriched_products = []
    
    total_products = len(products)
    
    for i, product in enumerate(products, 1):
        if progress_callback:
            try:
                await progress_callback(i, total_products, product["name"])
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")

        product_id = product["id"]
        existing = existing_by_id.get(product_id)
        
        # If product already exists and has basic info, reuse details
        if existing and existing.get("last_update"):
            # Still get details to check for updates? 
            # Ideally we'd optimize here, but 'Last update' is on the detail page.
            pass
        
        await _random_delay()
        
        details = await get_product_details(product["url"])
        
        if details:
            enriched_product = {
                **product,
                "image": details.get("image") or product.get("image"),
                "price": details.get("price") or product.get("price"),
                "last_update": details.get("last_update"),
                "published": details.get("published"),
                "description": details.get("description"),
                "reviews_count": details.get("reviews_count", 0),
                "rating": details.get("rating"),
                "last_seen": datetime.now().isoformat(),
                "first_seen": existing.get("first_seen") if existing else datetime.now().isoformat()
            }
        else:
            # Keep existing info if scraping fails
            enriched_product = {
                **product,
                **product,
                "price": product.get("price"),
                **(existing or {}),
                "last_seen": datetime.now().isoformat(),
                "first_seen": existing.get("first_seen") if existing else datetime.now().isoformat()
            }
        
        enriched_products.append(enriched_product)
    
    # Detect changes
    changes = detect_changes(existing_products, enriched_products)
    
    return {
        "products": enriched_products,
        "changes": changes
    }
