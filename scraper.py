# -*- coding: utf-8 -*-
"""
Scraper pour Fab.com - Seller et Product pages
"""
import random
import asyncio
import re
import os
from datetime import datetime
from typing import Optional

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from loguru import logger

# pyvirtualdisplay uniquement sur Linux
IS_WINDOWS = os.name == 'nt'
if not IS_WINDOWS:
    try:
        from pyvirtualdisplay import Display
    except ImportError:
        Display = None
else:
    Display = None

from config import (
    FAB_BASE_URL,
    SCRAPE_RETRY_COUNT,
    SCRAPE_DELAY_MIN,
    SCRAPE_DELAY_MAX,
    PAGE_LOAD_TIMEOUT,
    SCROLL_DELAY
)


def _clean_text(s: str) -> str:
    """Nettoie le texte en supprimant les espaces multiples."""
    return re.sub(r"\s+", " ", s or "").strip()


async def _random_delay():
    """Délai aléatoire entre les requêtes pour éviter le rate limiting."""
    await asyncio.sleep(random.uniform(SCRAPE_DELAY_MIN, SCRAPE_DELAY_MAX))


async def get_seller_products_list(seller_url: str, retries: int = SCRAPE_RETRY_COUNT) -> Optional[list[dict]]:
    """
    Scrape la page seller pour obtenir la liste des produits.
    
    Args:
        seller_url: URL de la page seller (ex: https://fab.com/sellers/GameAssetFactory)
        retries: Nombre de tentatives en cas d'échec
        
    Returns:
        Liste de dictionnaires avec {name, price, url, image} ou None en cas d'erreur
    """
    # Display uniquement sur Linux sans DISPLAY
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
                    
                    logger.info(f"Chargement de la page seller: {seller_url}")
                    await page.goto(seller_url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
                    await asyncio.sleep(2.0)
                    
                    # Scroll pour charger tous les produits (lazy loading)
                    previous_height = 0
                    scroll_attempts = 0
                    max_scrolls = 20
                    
                    while scroll_attempts < max_scrolls:
                        current_height = await page.evaluate("document.body.scrollHeight")
                        if current_height == previous_height:
                            break
                        previous_height = current_height
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await asyncio.sleep(SCROLL_DELAY)
                        scroll_attempts += 1
                    
                    content = await page.content()
                    soup = BeautifulSoup(content, "html.parser")
                    
                    products = []
                    seen_urls = set()
                    
                    # Chercher les cartes produit dans la grille
                    # Structure: <a> avec href="/listings/..." contenant image et texte
                    for link in soup.find_all("a", href=lambda h: h and h.startswith("/listings/")):
                        product_url = FAB_BASE_URL + link["href"]
                        
                        if product_url in seen_urls:
                            continue
                        seen_urls.add(product_url)
                        
                        # Extraire l'ID du produit depuis l'URL
                        product_id = link["href"].replace("/listings/", "").split("?")[0]
                        
                        # Chercher le conteneur parent de la carte
                        card = link.find_parent("li") or link.find_parent("div")
                        
                        # Nom du produit
                        name = None
                        # Chercher dans les éléments texte de la carte
                        for text_elem in (card or link).find_all(["h2", "h3", "h4", "span", "p", "div"]):
                            text = _clean_text(text_elem.get_text())
                            # Ignorer les prix et textes courts
                            if text and len(text) > 3 and not text.startswith("From") and not text.startswith("€") and not text.startswith("$"):
                                if not any(c.isdigit() for c in text[:3]):  # Éviter les prix
                                    name = text
                                    break
                        
                        if not name:
                            name = _clean_text(link.get_text(" ", strip=True)) or "Produit sans nom"
                        
                        # Prix
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
                            "price": price or "Prix non disponible",
                            "url": product_url,
                            "image": image
                        })
                    
                    await browser.close()
                    
                    if not products:
                        logger.warning(f"Aucun produit trouvé sur {seller_url}")
                        return []
                    
                    logger.info(f"Trouvé {len(products)} produits sur {seller_url}")
                    return products
                    
            except Exception as e:
                logger.error(f"Erreur scraping seller (tentative {attempt}/{retries}): {e}")
                await asyncio.sleep(random.uniform(5, 10))
        
        logger.error(f"Échec du scraping seller après {retries} tentatives")
        return None
        
    finally:
        if display:
            display.stop()


async def get_product_details(product_url: str, retries: int = SCRAPE_RETRY_COUNT) -> Optional[dict]:
    """
    Visite la page produit pour récupérer les détails.
    
    Args:
        product_url: URL du produit (ex: https://fab.com/listings/xxx)
        retries: Nombre de tentatives en cas d'échec
        
    Returns:
        Dictionnaire avec {last_update, changelog, description, reviews_count} ou None
    """
    # Display uniquement sur Linux sans DISPLAY
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
                    
                    logger.info(f"Chargement page produit: {product_url}")
                    await page.goto(product_url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
                    await asyncio.sleep(2.0)
                    
                    # Scroll pour charger le contenu
                    await page.evaluate("window.scrollTo(0, 500)")
                    await asyncio.sleep(1.0)
                    
                    content = await page.content()
                    soup = BeautifulSoup(content, "html.parser")
                    
                    details = {
                        "last_update": None,
                        "published": None,
                        "changelog": [],
                        "description": None,
                        "reviews_count": 0
                    }
                    
                    # Chercher "Last update" dans la section Details
                    page_text = soup.get_text()
                    
                    # Last update pattern: "Last update" suivi d'une date
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
                    
                    # Chercher le lien Changelog et essayer de l'ouvrir
                    changelog_link = soup.find("a", string=re.compile(r"changelog", re.IGNORECASE))
                    if changelog_link:
                        try:
                            # Cliquer sur le lien changelog
                            await page.click("text=Changelog")
                            await asyncio.sleep(1.5)
                            
                            # Récupérer le contenu du modal
                            modal_content = await page.content()
                            modal_soup = BeautifulSoup(modal_content, "html.parser")
                            
                            # Chercher les entrées de changelog (dates)
                            changelog_entries = []
                            date_pattern = re.compile(r"([A-Za-z]+\s+\d{1,2},?\s*\d{4})")
                            for text in modal_soup.find_all(text=date_pattern):
                                match = date_pattern.search(str(text))
                                if match:
                                    changelog_entries.append(match.group(1))
                            
                            details["changelog"] = changelog_entries[:10]  # Limiter à 10 entrées
                            
                            # Fermer le modal
                            await page.keyboard.press("Escape")
                            await asyncio.sleep(0.5)
                            
                        except Exception as e:
                            logger.warning(f"Impossible d'ouvrir le changelog: {e}")
                    
                    # Description (onglet Overview)
                    description_section = soup.find("h2", string=re.compile(r"description", re.IGNORECASE))
                    if description_section:
                        desc_parent = description_section.find_parent("div") or description_section.find_parent("section")
                        if desc_parent:
                            details["description"] = _clean_text(desc_parent.get_text(" ", strip=True))[:1000]
                    else:
                        # Chercher directement le texte de description
                        for div in soup.find_all("div"):
                            text = _clean_text(div.get_text())
                            if len(text) > 100 and "set" in text.lower() or "pack" in text.lower():
                                details["description"] = text[:1000]
                                break
                    
                    # Reviews count
                    reviews_match = re.search(r"(\d+)\s*review", page_text, re.IGNORECASE)
                    if reviews_match:
                        details["reviews_count"] = int(reviews_match.group(1))
                    elif "No reviews yet" in page_text:
                        details["reviews_count"] = 0
                    
                    await browser.close()
                    
                    logger.info(f"Détails récupérés pour {product_url}: last_update={details['last_update']}")
                    return details
                    
            except Exception as e:
                logger.error(f"Erreur scraping produit (tentative {attempt}/{retries}): {e}")
                await asyncio.sleep(random.uniform(5, 10))
        
        logger.error(f"Échec du scraping produit après {retries} tentatives")
        return None
        
    finally:
        if display:
            display.stop()


def detect_changes(old_products: list, new_products: list) -> dict:
    """
    Compare les anciens et nouveaux produits pour détecter les changements.
    
    Args:
        old_products: Liste des produits en cache
        new_products: Liste des nouveaux produits scrapés
        
    Returns:
        Dict avec "new" (nouveaux produits) et "updated" (produits mis à jour)
    """
    changes = {
        "new": [],
        "updated": []
    }
    
    # Créer un dict des anciens produits par ID
    old_by_id = {p["id"]: p for p in (old_products or [])}
    
    for new_product in (new_products or []):
        product_id = new_product.get("id")
        
        if product_id not in old_by_id:
            # Nouveau produit
            changes["new"].append(new_product)
        else:
            # Vérifier si le produit a été mis à jour
            old_product = old_by_id[product_id]
            
            # Comparer last_update
            old_update = old_product.get("last_update")
            new_update = new_product.get("last_update")
            
            if new_update and old_update != new_update:
                changes["updated"].append({
                    **new_product,
                    "previous_update": old_update
                })
            # Comparer le prix aussi
            elif old_product.get("price") != new_product.get("price"):
                changes["updated"].append({
                    **new_product,
                    "previous_price": old_product.get("price")
                })
    
    return changes


async def scrape_seller_with_details(seller_url: str, existing_products: list = None) -> Optional[dict]:
    """
    Scrape complet d'un seller: liste des produits + détails de chaque produit.
    
    Args:
        seller_url: URL du seller
        existing_products: Liste des produits existants en cache (pour optimisation)
        
    Returns:
        Dict avec "products" et "changes" ou None en cas d'erreur
    """
    # Phase 1: Récupérer la liste des produits
    products = await get_seller_products_list(seller_url)
    
    if products is None:
        return None
    
    if not products:
        return {"products": [], "changes": {"new": [], "updated": []}}
    
    # Créer un dict des produits existants par ID
    existing_by_id = {p["id"]: p for p in (existing_products or [])}
    
    # Phase 2: Récupérer les détails de chaque produit (seulement si nouveau ou potentiellement modifié)
    enriched_products = []
    
    for product in products:
        product_id = product["id"]
        existing = existing_by_id.get(product_id)
        
        # Si le produit existe déjà et a les mêmes infos de base, réutiliser les détails
        if existing and existing.get("last_update"):
            # Récupérer quand même les détails pour vérifier les mises à jour
            pass
        
        await _random_delay()
        
        details = await get_product_details(product["url"])
        
        if details:
            enriched_product = {
                **product,
                "last_update": details.get("last_update"),
                "published": details.get("published"),
                "changelog": details.get("changelog", []),
                "description": details.get("description"),
                "reviews_count": details.get("reviews_count", 0),
                "last_seen": datetime.now().isoformat(),
                "first_seen": existing.get("first_seen") if existing else datetime.now().isoformat()
            }
        else:
            # Garder les infos existantes si le scraping échoue
            enriched_product = {
                **product,
                **(existing or {}),
                "last_seen": datetime.now().isoformat(),
                "first_seen": existing.get("first_seen") if existing else datetime.now().isoformat()
            }
        
        enriched_products.append(enriched_product)
    
    # Détecter les changements
    changes = detect_changes(existing_products, enriched_products)
    
    return {
        "products": enriched_products,
        "changes": changes
    }
