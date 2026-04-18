"""
Парсер каталога Shelly (надёжная версия с обработкой ошибок)
https://www.shelly.com/collections/all-products
"""

import asyncio
import json
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Set
from pathlib import Path

from playwright.async_api import async_playwright, Page, Browser, Error as PlaywrightError


class ShellyParser:
    """Надёжный парсер каталога Shelly"""
    
    BASE_URL = "https://www.shelly.com"
    CATALOG_URL = f"{BASE_URL}/collections/all-products"
    
    # Селекторы для поиска товаров (несколько вариантов на случай изменения сайта)
    PRODUCT_SELECTORS = [
        'div.product-item',
        'div.product-card',
        'div[class*="product"]',
        'li[class*="product"]',
        'article[class*="product"]'
    ]
    
    LINK_SELECTORS = [
        'a[href*="/products/"]',
        'a[href*="/collections/"]',
        'div.product-item a',
        'div.product-card a'
    ]
    
    TITLE_SELECTORS = [
        '[class*="title"]',
        '[class*="name"]',
        'h3', 'h4', 'h5',
        '[class*="heading"]',
        'span[class*="product"]'
    ]
    
    PRICE_SELECTORS = [
        '[class*="price"]',
        '[class*="Price"]',
        '[data-price]',
        'span.money'
    ]
    
    def __init__(self, output_dir: str = "parsed_data"):
        self.products: List[Dict] = []
        self.seen_urls: Set[str] = set()
        self.errors: List[Dict] = []
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
    async def run(self) -> List[Dict]:
        """Запуск парсинга с сохранением промежуточных результатов"""
        print("=" * 60)
        print("Shelly Parser v1.0")
        print(f"Старт: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        browser = None
        try:
            async with async_playwright() as p:
                # Запускаем браузер с настройками для стабильности
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--no-sandbox',
                        '--disable-dev-shm-usage'
                    ]
                )
                
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    ignore_https_errors=True
                )
                
                page = await context.new_page()
                
                # Настройка таймаутов
                page.set_default_timeout(30000)
                page.set_default_navigation_timeout(45000)
                
                # Загружаем главную страницу
                print(f"\n[1/4] Загрузка каталога: {self.CATALOG_URL}")
                await self._safe_goto(page, self.CATALOG_URL)
                
                # Ожидаем загрузки контента
                print("[2/4] Ожидание загрузки товаров...")
                await self._wait_for_content(page)
                
                # Прокручиваем для загрузки всех товаров
                print("[3/4] Прокрутка страницы для загрузки всех товаров...")
                await self._smart_scroll(page)
                
                # Извлекаем ссылки на товары
                print("[4/4] Извлечение и обработка товаров...")
                product_urls = await self._extract_product_urls(page)
                print(f"Найдено {len(product_urls)} уникальных товаров")
                
                # Сохраняем список URL для отладки
                self._save_urls(product_urls)
                
                # Обрабатываем каждый товар
                for idx, url in enumerate(product_urls, 1):
                    print(f"\n  Обработка {idx}/{len(product_urls)}: {url.split('/')[-1]}")
                    
                    product_data = await self._get_product_with_retry(page, url)
                    
                    if product_data:
                        self.products.append(product_data)
                    
                    # Сохраняем промежуточный результат каждые 10 товаров
                    if idx % 10 == 0:
                        self._save_intermediate()
                        print(f"  [Сохранено {len(self.products)} товаров]")
                    
                    # Задержка между запросами
                    await asyncio.sleep(0.5 + idx * 0.05)  # Увеличиваем задержку для тяжёлых страниц
                
                await browser.close()
                
        except Exception as e:
            print(f"\n!!! КРИТИЧЕСКАЯ ОШИБКА: {e}")
            self.errors.append({
                'timestamp': datetime.now().isoformat(),
                'error': str(e),
                'type': type(e).__name__
            })
        finally:
            if browser:
                await browser.close()
        
        # Финальное сохранение
        self._save_final()
        self._print_statistics()
        
        return self.products
    
    async def _safe_goto(self, page: Page, url: str, max_retries: int = 3) -> bool:
        """Безопасный переход по URL с повторными попытками"""
        for attempt in range(max_retries):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)
                return True
            except Exception as e:
                print(f"    Попытка {attempt + 1}/{max_retries} не удалась: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(3)
        return False
    
    async def _wait_for_content(self, page: Page, max_wait: int = 15) -> bool:
        """Ожидание появления контента на странице"""
        start_time = time.time()
        while time.time() - start_time < max_wait:
            # Проверяем наличие товаров
            has_products = await page.evaluate('''
                () => {
                    const selectors = ['div.product-item', 'div.product-card', '[class*="product"]'];
                    for (const sel of selectors) {
                        if (document.querySelector(sel)) return true;
                    }
                    return false;
                }
            ''')
            if has_products:
                print("    Контент загружен")
                return True
            await asyncio.sleep(1)
        
        print("    ВНИМАНИЕ: Контент не загружен за отведённое время")
        return False
    
    async def _smart_scroll(self, page: Page, max_scrolls: int = 20) -> None:
        """Умная прокрутка с отслеживанием новых элементов"""
        previous_count = 0
        no_change_count = 0
        
        for scroll_num in range(max_scrolls):
            # Получаем текущее количество товаров
            current_count = await page.evaluate('''
                () => document.querySelectorAll('div.product-item, div.product-card, a[href*="/products/"]').length
            ''')
            
            print(f"    Прокрутка {scroll_num + 1}/{max_scrolls}, товаров: {current_count}")
            
            if current_count == previous_count:
                no_change_count += 1
                if no_change_count >= 3:
                    print("    Новые товары не загружаются, завершаем прокрутку")
                    break
            else:
                no_change_count = 0
                previous_count = current_count
            
            # Прокручиваем
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)
            
            # Пробуем нажать кнопку "Загрузить ещё", если есть
            await page.evaluate('''
                () => {
                    const loadMore = document.querySelector('[class*="load-more"], [class*="LoadMore"], button:has-text("Load more")');
                    if (loadMore) loadMore.click();
                }
            ''')
            await asyncio.sleep(1)
    
    async def _extract_product_urls(self, page: Page) -> List[str]:
        """Извлечение уникальных URL товаров"""
        urls = await page.evaluate('''
            () => {
                const urls = new Set();
                
                // Поиск по всем возможным ссылкам
                const links = document.querySelectorAll('a[href*="/products/"], a[href*="/collections/"]');
                
                for (const link of links) {
                    let href = link.href;
                    // Очищаем URL от параметров
                    href = href.split('?')[0].split('#')[0];
                    
                    // Оставляем только ссылки на товары
                    if (href.includes('/products/') && !href.includes('/collections/')) {
                        urls.add(href);
                    }
                }
                
                return Array.from(urls);
            }
        ''')
        
        # Дедупликация и фильтрация
        valid_urls = []
        for url in urls:
            if url not in self.seen_urls and self.BASE_URL in url:
                self.seen_urls.add(url)
                valid_urls.append(url)
        
        return valid_urls
    
    async def _get_product_with_retry(self, page: Page, url: str, max_retries: int = 2) -> Optional[Dict]:
        """Получение данных товара с повторными попытками"""
        for attempt in range(max_retries):
            try:
                return await self._get_product_details(page, url)
            except Exception as e:
                print(f"      Ошибка (попытка {attempt + 1}): {str(e)[:100]}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    # Обновляем страницу перед повторной попыткой
                    await page.reload(wait_until="domcontentloaded")
                    await asyncio.sleep(1)
        
        self.errors.append({
            'url': url,
            'timestamp': datetime.now().isoformat(),
            'error': f'Не удалось обработать после {max_retries} попыток'
        })
        return None
    
    async def _get_product_details(self, page: Page, url: str) -> Dict:
        """Получение детальной информации о товаре"""
        await self._safe_goto(page, url)
        await asyncio.sleep(1.5)
        
        # Извлекаем данные
        data = await page.evaluate('''
            () => {
                const data = {
                    url: window.location.href,
                    title: '',
                    price: '',
                    in_stock: true,
                    tags: [],
                    description: '',
                    specifications: {},
                    has_alice: false,
                    dimmable: false,
                    voltage: null,
                    max_power: null,
                    generation: null
                };
                
                // Полный текст страницы для поиска
                const fullText = document.body.innerText || '';
                
                // Название
                const titleEl = document.querySelector('h1, [class*="title"], [class*="name"]');
                if (titleEl) data.title = titleEl.innerText.trim();
                
                // Цена
                const priceEl = document.querySelector('[class*="price"], [data-price], span.money');
                if (priceEl) data.price = priceEl.innerText.trim();
                
                // Наличие
                const stockEl = document.querySelector('[class*="stock"], [class*="inventory"], [class*="availability"]');
                if (stockEl) {
                    const stockText = stockEl.innerText.toLowerCase();
                    data.in_stock = !stockText.includes('out of stock') && !stockText.includes('sold out');
                }
                
                // Описание
                const descEl = document.querySelector('[class*="description"], [class*="desc"], [class*="product-info"]');
                if (descEl) data.description = descEl.innerText.trim();
                
                // Характеристики
                const specTables = document.querySelectorAll('table, [class*="specs"], [class*="details"]');
                for (const table of specTables) {
                    const rows = table.querySelectorAll('tr, [class*="row"]');
                    for (const row of rows) {
                        const key = row.querySelector('th, [class*="label"]')?.innerText?.trim();
                        const val = row.querySelector('td, [class*="value"]')?.innerText?.trim();
                        if (key && val) {
                            data.specifications[key] = val;
                        }
                    }
                }
                
                // Поиск по тексту
                const searchText = (data.description + ' ' + JSON.stringify(data.specifications) + ' ' + fullText).toLowerCase();
                
                // Поддержка Алисы
                data.has_alice = /алис|alice|яндекс|yandex|voice|голос/i.test(searchText);
                
                // Диммируемость
                data.dimmable = /диммир|dim|dimmable|brightness|яркость/i.test(searchText);
                
                // Поколение
                const genMatch = searchText.match(/gen(\\d+)|generation\\s+(\\d+)/i);
                if (genMatch) {
                    data.generation = genMatch[1] || genMatch[2];
                }
                
                // Напряжение
                const voltageMatch = searchText.match(/(\\d+)[-–]?(\\d+)?\\s*[vв]/i);
                if (voltageMatch) data.voltage = voltageMatch[0];
                
                // Мощность
                const powerMatch = searchText.match(/(\\d+)[-–]?(\\d+)?\\s*[wвт]/i);
                if (powerMatch) data.max_power = powerMatch[0];
                
                return data;
            }
        ''')
        
        return data
    
    def _save_urls(self, urls: List[str]) -> None:
        """Сохранение списка URL для отладки"""
        filepath = self.output_dir / "shelly_urls.json"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                'total': len(urls),
                'urls': urls,
                'timestamp': datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
        print(f"  URL сохранены в {filepath}")
    
    def _save_intermediate(self) -> None:
        """Сохранение промежуточных результатов"""
        filepath = self.output_dir / "shelly_intermediate.json"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                'products': self.products,
                'count': len(self.products),
                'timestamp': datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
    
    def _save_final(self) -> None:
        """Финальное сохранение"""
        filepath = self.output_dir / "shelly_products.json"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                'brand': 'Shelly',
                'total_count': len(self.products),
                'products': self.products,
                'errors': self.errors,
                'parsed_at': datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
        
        # Также сохраняем упрощённую версию для БД
        simple_path = self.output_dir / "shelly_simple.json"
        simple_products = []
        for p in self.products:
            simple_products.append({
                'id': p.get('url', '').split('/')[-1].replace('-', '_'),
                'brand': 'Shelly',
                'model': p.get('title', ''),
                'url': p.get('url', ''),
                'price': p.get('price', ''),
                'in_stock': p.get('in_stock', True),
                'has_alice': p.get('has_alice', False),
                'dimmable': p.get('dimmable', False),
                'generation': p.get('generation'),
                'voltage': p.get('voltage'),
                'max_power': p.get('max_power')
            })
        
        with open(simple_path, 'w', encoding='utf-8') as f:
            json.dump(simple_products, f, ensure_ascii=False, indent=2)
        
        print(f"\n  Финальные данные сохранены в {filepath}")
        print(f"Упрощённая версия в {simple_path}")
    
    def _print_statistics(self) -> None:
        """Вывод статистики"""
        print("\n" + "=" * 60)
        print("СТАТИСТИКА ПАРСИНГА")
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
            
            # Поколения
            gens = {}
            for p in self.products:
                gen = p.get('generation')
                if gen:
                    gens[gen] = gens.get(gen, 0) + 1
            if gens:
                print(f"\nПоколения: {gens}")
        
        print(f"\nЗавершено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)


async def main():
    """Основная функция"""
    parser = ShellyParser(output_dir="parsed_data")
    products = await parser.run()
    
    if products:
        print(f"\n✅ Парсинг успешно завершён! Обработано {len(products)} товаров.")
    else:
        print("\n⚠️ Внимание! Не удалось получить данные. Проверьте подключение к интернету.")
        print("   Если сайт изменил структуру, может потребоваться обновление селекторов.")


if __name__ == "__main__":
    asyncio.run(main())