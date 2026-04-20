"""
Парсер каталога HitePro - версия с точными селекторами
https://www.hite-pro.ru
"""

import requests
from bs4 import BeautifulSoup
import time
import random
import re
from typing import List, Dict, Optional
import json
from urllib.parse import urljoin

class HiteProParser:
    def __init__(self):
        self.base_url = "https://www.hite-pro.ru"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.google.com/',
            'Connection': 'keep-alive'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def get_page(self, url: str) -> Optional[str]:
        try:
            response = self.session.get(url, timeout=15)
            if response.status_code == 200:
                return response.text
            else:
                print(f"Ошибка {response.status_code} при доступе к {url}")
                return None
        except Exception as e:
            print(f"Ошибка соединения: {e}")
            return None

    def parse_category(self, category_url: str, max_pages: int = 5) -> List[Dict]:
        products = []
        current_url = category_url
        page_count = 0
        
        while current_url and page_count < max_pages and self.is_running:
            print(f"Парсинг HitePro: {current_url}")
            html = self.get_page(current_url)
            if not html:
                break
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Точный селектор для карточек товаров HitePro
            product_cards = soup.find_all('div', class_='product-grid-item')
            
            if not product_cards:
                print("Не удалось найти карточки товаров на странице.")
                break

            for card in product_cards:
                if not self.is_running:
                    break
                data = self.extract_product_data(card, current_url)
                if data:
                    products.append(data)

            # Поиск следующей страницы
            next_btn = soup.find('a', class_='next')
            if not next_btn:
                next_btn = soup.find('li', class_='next').find('a') if soup.find('li', class_='next') else None
            
            if next_btn and next_btn.get('href'):
                href = next_btn['href']
                if href.startswith('http'):
                    current_url = href
                else:
                    current_url = urljoin(category_url, href)
                page_count += 1
                time.sleep(random.uniform(1.5, 2.5))
            else:
                break
                
        return products

    def extract_product_data(self, card, page_url) -> Optional[Dict]:
        try:
            # Извлечение названия - точный селектор
            title_el = card.find('h3', class_='wd-entities-title').find('a') if card.find('h3', class_='wd-entities-title') else None
            
            if not title_el:
                return None
                
            title = title_el.get_text(strip=True)
            link = title_el.get('href', '')
            
            if link and not link.startswith('http'):
                link = urljoin(page_url, link)

            # Извлечение цены - точный селектор
            price_el = card.find('span', class_='woocommerce-Price-amount')
            price_str = "0"
            if price_el:
                raw_price = price_el.get_text(strip=True)
                nums = re.findall(r'\d+', raw_price.replace(' ', ''))
                if nums:
                    price_str = nums[0]
            
            # Извлечение SKU из data-атрибутов или кнопки
            sku = "N/A"
            if card.get('data-id'):
                sku = str(card.get('data-id'))
            else:
                # Пробуем найти SKU в кнопке "В корзину"
                add_to_cart_btn = card.find('a', class_='add_to_cart_button')
                if add_to_cart_btn and add_to_cart_btn.get('data-product_sku'):
                    sku = add_to_cart_btn.get('data-product_sku')

            return {
                "name": title,
                "price": price_str,
                "url": link,
                "sku": sku,
                "source": "HitePro"
            }
        except Exception as e:
            print(f"Ошибка обработки карточки: {e}")
            return None

    def save_to_json(self, data: List[Dict], filename: str):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Сохранено {len(data)} товаров в {filename}")

if __name__ == "__main__":
    parser = HiteProParser()
    parser.is_running = True
    url = "https://www.hite-pro.ru/shop/c/besprovodnoj-umnyj-dom/bloki-upravleniya"
    items = parser.parse_category(url, max_pages=2)
    if items:
        parser.save_to_json(items, "hitepro_test.json")
    else:
        print("Товары не найдены.")
