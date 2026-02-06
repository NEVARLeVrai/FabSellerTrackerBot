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
                    
                    # Launch Browser with Stealth args
                    args = [
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-infobars"
                    ]
                    # Note: Headless might need to be False for some CF challenges, but let's try True with stealth first
                    # or keep it consistent with the user's manual test which used headless=False?
                    # The user manual test used headless=False. Let's stick to headless=True for a bot, but with args.
                    # If it fails, we might need headless=False (virtual display on linux).
                    
                    browser = await p.firefox.launch(
                        headless=True,
                        args=args
                    )
                    
                    context = await browser.new_context(
                        locale=currency_settings["locale"],
                        timezone_id=currency_settings["timezone"],
                        # Add stealth user agent
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                        viewport={"width": 1920, "height": 1080}
                    )
                    
                    # Apply Stealth
                    try:
                        from playwright_stealth import Stealth
                        page = await context.new_page()
                        stealth = Stealth()
                        await stealth.apply_stealth_async(page)
                    except Exception as e:
                        logger.warning(f"Failed to apply stealth: {e}")
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
        Dictionary with {last_update, description, reviews_count, ...} or None
    """
    return await get_product_details_with_currency(product_url, currency=DEFAULT_CURRENCY, retries=retries)

async def get_product_details_with_currency(product_url: str, currency: str = DEFAULT_CURRENCY, retries: int = SCRAPE_RETRY_COUNT) -> Optional[dict]:
    """
    Visits the product page with specific currency/regional settings.
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
                    # Launch Browser with Stealth args
                    args = [
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-infobars"
                    ]
                    browser = await p.firefox.launch(
                        headless=True,
                        args=args
                    )
                    
                    # Set locale based on currency
                    currency_settings = CURRENCY_LOCALES.get(currency, CURRENCY_LOCALES[DEFAULT_CURRENCY])
                    
                    context = await browser.new_context(
                         locale=currency_settings["locale"],
                         timezone_id=currency_settings["timezone"],
                         user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                         viewport={"width": 1920, "height": 1080}
                    )
                    
                    # Apply Stealth
                    try:
                        from playwright_stealth import Stealth
                        page = await context.new_page()
                        stealth = Stealth()
                        await stealth.apply_stealth_async(page)
                    except Exception as e:
                        logger.warning(f"Failed to apply stealth: {e}")
                        page = await context.new_page()
                    
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
                        "price": {} # Changed to dict for dual currency
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
                            entities = data.get("initialState", {}).get("entities", {}) or data.get("entities", {})
                            listing = entities.get("listings", {}).get(product_id, {})
                            
                            if listing:
                                # Helper to get prices from priceTier object
                                def get_prices_from_tier(tier):
                                    res = {}
                                    price_val = tier.get("price")
                                    curr_code = tier.get("currencyCode", "USD")
                                    
                                    # Base price (often local)
                                    symbol = "€" if curr_code == "EUR" else ("£" if curr_code == "GBP" else "$")
                                    res[curr_code] = f"{price_val}{symbol}"
                                    
                                    # Always try USD from ID if available
                                    price_tier_id = tier.get("priceTierId", "")
                                    usd_match = re.search(r"_USD_(\d+)_", price_tier_id)
                                    if usd_match:
                                        try:
                                            usd_val = int(usd_match.group(1)) / 100.0
                                            res["USD"] = f"{usd_val}$"
                                        except (ValueError, TypeError):
                                            pass
                                    return res

                                # Check for multiple licenses
                                licenses = listing.get("licenses", [])
                                if licenses and len(licenses) > 0:
                                    multi_prices = {}
                                    for lic in licenses:
                                        name = lic.get("name")
                                        tier = lic.get("priceTier", {})
                                        if name and tier:
                                            tiers = get_prices_from_tier(tier)
                                            for c, p in tiers.items():
                                                if c not in multi_prices: multi_prices[c] = []
                                                multi_prices[c].append(f"{name}: {p}")
                                    
                                    if multi_prices:
                                        details["price"] = {c: "\n".join(p) for c, p in multi_prices.items()}
                                        break

                                # Fallback to startingPrice
                                starting_price = listing.get("startingPrice")
                                if starting_price and starting_price.get("price") is not None:
                                    details["price"] = get_prices_from_tier(starting_price)
                                    break
                                
                                # Try price (simple)
                                if listing.get("price") is not None:
                                    details["price"] = {"USD": f"{listing.get('price')}$"}
                                    break

                        except json.JSONDecodeError:
                            continue

                    # Method 2: meta og:price (fallback)
                    if not details["price"]:
                        og_price = soup.find("meta", property="product:price:amount")
                        if og_price and og_price.get("content"):
                            p_curr = soup.find("meta", property="product:price:currency")
                            curr_code = p_curr.get("content") if p_curr else "USD"
                            symbol = "€" if curr_code == "EUR" else "$"
                            details["price"] = {curr_code: f"{og_price['content']}{symbol}"}
                    
                    # Get page text for other extractions
                    page_text = soup.get_text()
                    
                    # Method 3: Search for price text in page
                    if not details["price"]:
                        price_match = re.search(r"[€$][\d.,]+", page_text)
                        if price_match:
                            val = price_match.group(0)
                            if val.startswith("€") or val.startswith("$"):
                                symbol = val[0]
                                code = "EUR" if symbol == "€" else "USD"
                                details["price"] = {code: val[1:] + symbol}
                    
                    # ... (rest of extraction logic remains same)
                    
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

                    # Extract Supported Unreal Engine Versions
                    # Search for text "Supported Unreal Engine Versions"
                    ue_label = soup.find(string=lambda t: t and "Supported Unreal Engine Versions" in t)
                    if ue_label:
                        # Try to find value in siblings of parent, or parent's parent
                        ue_parent = ue_label.parent
                        for _ in range(3): # Traverse up 3 levels max
                            if not ue_parent: break
                            
                            # Check next sibling div
                            ue_value_div = ue_parent.find_next_sibling("div")
                            if ue_value_div:
                                val = _clean_text(ue_value_div.get_text())
                                # Validate it looks like versions (digits and dots)
                                if any(c.isdigit() for c in val):
                                    details["ue_versions"] = val
                                    break
                            
                            ue_parent = ue_parent.parent
                    
                    # Fallback search if direct sibling fails (sometimes structure varies)
                    if not details.get("ue_versions"):
                         # Try searching by text in the whole page text using regex
                         # Pattern: "Supported Unreal Engine Versions" followed by versions (digits, dots, dashes, "and")
                         # Example: "Supported Unreal Engine Versions 4.22 – 4.27 and 5.0 – 5.7"
                         # Note: get_text might collapse newlines to spaces
                         
                         # Look for line starting with Supported...
                         ue_fallback = re.search(r"Supported Unreal Engine Versions\s*([\d.\s\–\-and]+)", page_text, re.IGNORECASE)
                         if ue_fallback:
                             cand = ue_fallback.group(1).strip()
                             if len(cand) > 3 and any(c.isdigit() for c in cand) and len(cand) < 50:
                                 details["ue_versions"] = cand
                    
                    # Extract Changelog
                    try:
                        # Find Changelog button/tab - usually "Changelog" text
                        # Use Playwright locators for interaction
                        changelog_btn = page.get_by_text("Changelog", exact=False)
                        if await changelog_btn.count() > 0:
                            # Click the first one
                            await changelog_btn.first.click()
                            
                            # Wait for modal to appear
                            try:
                                modal = page.locator(".fabkit-Modal-content")
                                await modal.wait_for(state="visible", timeout=3000)
                                
                                # Parse modal content
                                modal_html = await modal.inner_html()
                                modal_soup = BeautifulSoup(modal_html, "html.parser")
                                
                                entries = []
                                # Items are in stacked divs
                                for stack_item in modal_soup.find_all("div", class_="fabkit-Stack-root fabkit-Stack--column", recursive=True):
                                    date_tag = stack_item.find("h3")
                                    content_div = stack_item.find("div", class_="fabkit-RichContent-root")
                                    
                                    if date_tag and content_div:
                                        date_str = _clean_text(date_tag.get_text())
                                        notes = _clean_text(content_div.get_text())
                                        
                                        # Filter empty notes if desired, or keep them
                                        if "No notes provided" in notes:
                                            entries.append(f"**{date_str}**: No notes")
                                        else:
                                            # Truncate notes if too long
                                            if len(notes) > 200:
                                                notes = notes[:200] + "..."
                                            entries.append(f"**{date_str}**\n{notes}")
                                        
                                        if len(entries) >= 3: # Keep top 3
                                            break
                                
                                if entries:
                                    details["changelog"] = "\n\n".join(entries)
                                    
                            except Exception as e:
                                # Modal didn't appear or timeout
                                logger.debug(f"Changelog modal issue: {e}")
                                
                    except Exception as e:
                        logger.warning(f"Error extracting changelog: {e}")

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


def detect_changes(old_products: list, new_products: list, currency: str = "USD") -> dict:
    """
    Compares old and new products to detect changes.
    
    Args:
        old_products: List of cached products
        new_products: List of newly scraped products
        currency: The currency to compare for price updates
        
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
            else:
                # Compare price for requested currency
                old_p = old_product.get("price")
                new_p = new_product.get("price")
                
                price_updated = False
                prev_price = None
                
                # If new_p is dict, we check the requested currency
                if isinstance(new_p, dict):
                    new_val = new_p.get(currency)
                    if isinstance(old_p, dict):
                        old_val = old_p.get(currency)
                    else:
                        # Migration case: old_p is string
                        old_val = old_p
                    
                    if new_val and old_val != new_val:
                        price_updated = True
                        prev_price = old_val
                elif old_p != new_p:
                    # Fallback for simple strings
                    price_updated = True
                    prev_price = old_p
                
                if price_updated:
                    changes["updated"].append({
                        **new_product,
                        "previous_price": prev_price
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
        
        details = await get_product_details_with_currency(product["url"], currency=currency)
        
        if details:
            enriched_product = {
                **product,
                "image": details.get("image") or product.get("image"),
                "price": details.get("price") or product.get("price"),
                "ue_versions": details.get("ue_versions"),
                "last_update": details.get("last_update"),
                "published": details.get("published"),
                "changelog": details.get("changelog"),
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
    changes = detect_changes(existing_products, enriched_products, currency=currency)
    
    return {
        "products": enriched_products,
        "changes": changes
    }
