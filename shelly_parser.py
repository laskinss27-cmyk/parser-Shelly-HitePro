"""
Парсер каталога Shelly - версия с точными селекторами
https://shelly.company
"""

import requests
from bs4 import BeautifulSoup
import time
import random
import re
from typing import List, Dict, Optional
import json
from urllib.parse import urljoin

class ShellyParser:
    def __init__(self):
        self.base_url = "https://shelly.company"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def get_page(self, url: str) -> Optional[str]:
        try:
            response = self.session.get(url, timeout=15)
            if response.status_code == 200:
                return response.text
            else:
                print(f"Ошибка доступа к {url}: Статус {response.status_code}")
                return None
        except requests.exceptions.RequestException as e:
            print(f"Ошибка сети при запросе {url}: {e}")
            return None

    def parse_category(self, category_url: str, max_pages: int = 5) -> List[Dict]:
        products = []
        current_url = category_url
        page_count = 0
        
        while current_url and page_count < max_pages and self.is_running:
            print(f"Парсинг страницы Shelly: {current_url}")
            html = self.get_page(current_url)
            if not html:
                break
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Точный селектор для карточек товаров Shelly
            product_cards = soup.find_all('div', class_='card--standard')
            
            if not product_cards:
                print("Не удалось найти карточки товаров на странице.")
                break

            for card in product_cards:
                if not self.is_running:
                    break
                try:
                    product_data = self.extract_product_data(card, current_url)
                    if product_data:
                        products.append(product_data)
                except Exception as e:
                    print(f"Ошибка извлечения данных: {e}")
                    continue

            # Поиск следующей страницы
            next_link = soup.find('a', rel='next')
            if next_link and next_link.get('href'):
                next_href = next_link['href']
                if next_href.startswith('http'):
                    current_url = next_href
                else:
                    current_url = urljoin(category_url, next_href)
                page_count += 1
                time.sleep(random.uniform(1.0, 2.0))
            else:
                break
        
        return products

    def extract_product_data(self, card, page_url) -> Optional[Dict]:
        try:
            # Извлечение названия - точный селектор
            title_tag = card.find('h2', class_='card__heading')
            if title_tag:
                title_tag = title_tag.find('a')
            
            if not title_tag:
                return None
                
            title = title_tag.get_text(strip=True)
            
            # Извлечение ссылки
            link = title_tag.get('href', '')
            if link and not link.startswith('http'):
                link = urljoin(page_url, link)

            # Извлечение цены - точный селектор
            price_container = card.find('div', class_='price__container')
            price = "0"
            if price_container:
                # Пробуем найти обычную цену или цену со скидкой
                price_item = price_container.find('span', class_='price-item--sale') or \
                            price_container.find('span', class_='price-item--regular')
                if price_item:
                    price_text = price_item.get_text(strip=True)
                    # Очищаем от валюты и пробелов, оставляем только цифры
                    price = re.sub(r'[^\d]', '', price_text)
            
            # Извлечение SKU из JSON скрипта
            sku = "N/A"
            script_tag = card.find('script', type='application/json', attrs={'data-selected-variant': ''})
            if script_tag and script_tag.string:
                try:
                    variant_data = json.loads(script_tag.string)
                    sku = variant_data.get('sku', 'N/A')
                except:
                    pass

            # Если SKU не найден в JSON, пробуем найти в тексте
            if sku == "N/A":
                sku_match = re.search(r'[\dA-Z]{8,}', card.get_text())
                if sku_match:
                    sku = sku_match.group()

            if title:
                return {
                    "name": title,
                    "price": price,
                    "url": link,
                    "sku": sku,
                    "source": "Shelly"
                }
        except Exception as e:
            print(f"Ошибка обработки карточки: {e}")
            return None
        return None

    def save_to_json(self, data: List[Dict], filename: str):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Сохранено {len(data)} товаров в {filename}")

if __name__ == "__main__":
    parser = ShellyParser()
    parser.is_running = True
    url = "https://shelly.company/collections/all"
    items = parser.parse_category(url, max_pages=2)
    if items:
        parser.save_to_json(items, "shelly_test.json")
    else:
        print("Товары не найдены.")
