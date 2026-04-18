"""
Парсер каталога Hite Pro (WooCommerce)
https://www.hite-pro.ru/shop
"""

import asyncio
import json
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Set
from pathlib import Path

from playwright.async_api import async_playwright, Page


class HiteProParser:
    """Парсер каталога Hite Pro (WooCommerce)"""
    
    BASE_URL = "https://www.hite-pro.ru"
    CATALOG_URL = f"{BASE_URL}/shop"
    
    def __init__(self, output_dir: str = "parsed_data"):
        self.products: List[Dict] = []
        self.seen_urls: Set[str] = set()
        self.errors: List[Dict] = []
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
    async def run(self) -> List[Dict]:
        """Запуск парсинга"""
        print("=" * 60)
        print("HitePro Parser v1.0 (WooCommerce)")
        print(f"Старт: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()
            
            print(f"\n[1/3] Загрузка каталога: {self.CATALOG_URL}")
            await page.goto(self.CATALOG_URL, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)
            
            print("[2/3] Извлечение ссылок на товары...")
            product_urls = await self._extract_product_urls(page)
            print(f"Найдено {len(product_urls)} товаров")
            
            print("[3/3] Обработка товаров...")
            for idx, url in enumerate(product_urls, 1):
                print(f"  {idx}/{len(product_urls)}: {url.split('/')[-2]}")
                
                product_data = await self._get_product_details(page, url)
                if product_data:
                    self.products.append(product_data)
                
                if idx % 20 == 0:
                    self._save_intermediate()
                
                await asyncio.sleep(0.5)
            
            await browser.close()
        
        self._save_final()
        self._print_statistics()
        
        return self.products
    
    async def _extract_product_urls(self, page: Page) -> List[str]:
        """Извлечение URL товаров из каталога WooCommerce"""
        urls = await page.evaluate('''
            () => {
                const urls = new Set();
                
                // WooCommerce классы для товаров
                const productLinks = document.querySelectorAll(
                    'a.woocommerce-LoopProduct-link, ' +
                    'a.product_type_simple, ' +
                    'div.product a, ' +
                    'li.product a'
                );
                
                for (const link of productLinks) {
                    let href = link.href;
                    if (href && href.includes('/product/')) {
                        href = href.split('?')[0].split('#')[0];
                        urls.add(href);
                    }
                }
                
                return Array.from(urls);
            }
        ''')
        
        valid_urls = []
        for url in urls:
            if url not in self.seen_urls and self.BASE_URL in url:
                self.seen_urls.add(url)
                valid_urls.append(url)
        
        return valid_urls
    
    async def _get_product_details(self, page: Page, url: str) -> Optional[Dict]:
        """Получение детальной информации о товаре Hite Pro"""
        try:
            await page.goto(url, wait_until="networkidle", timeout=15000)
            await asyncio.sleep(1)
            
            data = await page.evaluate('''
                () => {
                    const data = {
                        url: window.location.href,
                        title: '',
                        sku: '',
                        price: '',
                        in_stock: true,
                        categories: [],
                        description: '',
                        short_description: '',
                        attributes: {},
                        has_alice: false,
                        dimmable: false,
                        voltage: null,
                        power: null,
                        product_type: null
                    };
                    
                    // Название
                    const titleEl = document.querySelector('h1.product_title, h1.entry-title');
                    if (titleEl) data.title = titleEl.innerText.trim();
                    
                    // Артикул (SKU)
                    const skuEl = document.querySelector('.sku, [class*="sku"]');
                    if (skuEl) data.sku = skuEl.innerText.trim();
                    
                    // Цена
                    const priceEl = document.querySelector('.price, [class*="price"]');
                    if (priceEl) data.price = priceEl.innerText.trim();
                    
                    // Наличие
                    const stockEl = document.querySelector('.stock, [class*="stock"], .in-stock, .out-of-stock');
                    if (stockEl) {
                        const stockText = stockEl.innerText.toLowerCase();
                        data.in_stock = stockText.includes('in stock') || stockText.includes('в наличии');
                    }
                    
                    // Категории
                    const catEls = document.querySelectorAll('.posted_in a, .product_meta a[rel="tag"]');
                    for (const el of catEls) {
                        data.categories.push(el.innerText.trim());
                    }
                    
                    // Описание
                    const descEl = document.querySelector('.woocommerce-product-details__description, .product-description, [class*="description"]');
                    if (descEl) data.description = descEl.innerText.trim();
                    
                    // Короткое описание
                    const shortDescEl = document.querySelector('.woocommerce-product-details__short-description, .product-short-description');
                    if (shortDescEl) data.short_description = shortDescEl.innerText.trim();
                    
                    // Характеристики (WooCommerce attributes)
                    const attrTable = document.querySelector('table.woocommerce-product-attributes, .attributes_table');
                    if (attrTable) {
                        const rows = attrTable.querySelectorAll('tr');
                        for (const row of rows) {
                            const key = row.querySelector('th')?.innerText?.trim();
                            const val = row.querySelector('td')?.innerText?.trim();
                            if (key && val) {
                                data.attributes[key] = val;
                                
                                // Определяем тип продукта
                                if (key.toLowerCase().includes('тип') || key.toLowerCase().includes('type')) {
                                    data.product_type = val;
                                }
                            }
                        }
                    }
                    
                    // Поиск по тексту
                    const fullText = (data.title + ' ' + data.description + ' ' + data.short_description + ' ' + JSON.stringify(data.attributes)).toLowerCase();
                    
                    // Поддержка Алисы
                    data.has_alice = /алис|alice|яндекс|yandex|голос|voice/i.test(fullText);
                    
                    // Диммируемость
                    data.dimmable = /диммир|dim|dimmable|регулир|brightness/i.test(fullText);
                    
                    // Напряжение
                    const voltageMatch = fullText.match(/(\\d+)[-–]?(\\d+)?\\s*[вv]/i);
                    if (voltageMatch) data.voltage = voltageMatch[0];
                    
                    // Мощность
                    const powerMatch = fullText.match(/(\\d+)[-–]?(\\d+)?\\s*[втw]/i);
                    if (powerMatch) data.power = powerMatch[0];
                    
                    return data;
                }
            ''')
            
            return data
            
        except Exception as e:
            self.errors.append({'url': url, 'error': str(e)})
            return None
    
    def _save_intermediate(self) -> None:
        """Сохранение промежуточных результатов"""
        filepath = self.output_dir / "hitepro_intermediate.json"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                'products': self.products,
                'count': len(self.products),
                'timestamp': datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
    
    def _save_final(self) -> None:
        """Финальное сохранение"""
        filepath = self.output_dir / "hitepro_products.json"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                'brand': 'HitePro',
                'total_count': len(self.products),
                'products': self.products,
                'errors': self.errors,
                'parsed_at': datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
    
    def _print_statistics(self) -> None:
        """Вывод статистики"""
        print("\n" + "=" * 60)
        print("СТАТИСТИКА ПАРСИНГА HitePro")
        print("=" * 60)
        print(f"Всего товаров: {len(self.products)}")
        print(f"Ошибок: {len(self.errors)}")
        
        if self.products:
            with_alice = sum(1 for p in self.products if p.get('has_alice'))
            dimmable = sum(1 for p in self.products if p.get('dimmable'))
            in_stock = sum(1 for p in self.products if p.get('in_stock', True))
            
            print(f"\nПоддерживают Алису: {with_alice} ({with_alice/len(self.products)*100:.1f}%)")
            print(f"Диммируемые: {dimmable} ({dimmable/len(self.products)*100:.1f}%)")
            print(f"В наличии: {in_stock} ({in_stock/len(self.products)*100:.1f}%)")
            
            # Категории
            all_cats = []
            for p in self.products:
                all_cats.extend(p.get('categories', []))
            if all_cats:
                from collections import Counter
                print(f"\nПопулярные категории: {dict(Counter(all_cats).most_common(5))}")


async def main():
    parser = HiteProParser()
    products = await parser.run()
    print(f"\n✅ Завершено! Обработано {len(products)} товаров.")


if __name__ == "__main__":
    asyncio.run(main())