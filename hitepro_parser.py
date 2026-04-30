"""
HitePro parser — WP REST API (список) + HTML (характеристики).
Без Playwright. Зависимости: requests, beautifulsoup4.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://www.hite-pro.ru"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
SLEEP = 0.4

# Категории умного дома (без расходников)
SMART_HOME_CATEGORIES = [
    ("bloki-upravleniya",   "Блоки управления"),
    ("datchiki",            "Датчики"),
    ("radiovyklyuchateli",  "Радиовыключатели"),
    ("server-umnogo-doma",  "Сервер УД"),
    ("komplekty",           "Комплекты"),
]
CATEGORY_URL = f"{BASE}/shop/c/besprovodnoj-umnyj-dom"


class HiteProParser:
    def __init__(self, output_dir: str = "parsed_data"):
        self.products: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    # ── список товаров через crawl категорий УД ─────────────────
    def _fetch_index(self) -> list[dict[str, Any]]:
        """Возвращает список словарей {url, slug, category} из категорий смарт-хома."""
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        url_re = re.compile(r'href="(https://www\.hite-pro\.ru/shop/goods/[a-z0-9-]+)/?"')

        for slug, label in SMART_HOME_CATEGORIES:
            url = f"{CATEGORY_URL}/{slug}/"
            r = self.session.get(url, timeout=20)
            r.raise_for_status()
            urls = sorted(set(url_re.findall(r.text)))
            new = 0
            for u in urls:
                if u in seen:
                    continue
                seen.add(u)
                items.append({"link": u, "slug": u.rstrip("/").rsplit("/", 1)[-1], "category": label})
                new += 1
            print(f"  {label}: {len(urls)} товаров (+{new} новых)")
            time.sleep(SLEEP)
        return items

    # ── разбор HTML карточки ────────────────────────────────────
    def _parse_card(self, html: str, url: str) -> dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")

        title = soup.select_one("h1.product_title, h1.entry-title")
        sku = soup.select_one(".sku")
        # Цена не сохраняется (по требованию проекта)

        # Категории
        cats = [a.get_text(strip=True) for a in soup.select(".posted_in a, .product_meta a[rel=tag]")]

        # Характеристики
        attrs: dict[str, str] = {}
        for tr in soup.select("table.woocommerce-product-attributes tr"):
            th = tr.find("th")
            td = tr.find("td")
            if th and td:
                key = th.get_text(" ", strip=True)
                val = td.get_text(" ", strip=True)
                if key and val:
                    attrs[key] = val

        # Описания
        short_desc_el = soup.select_one(".woocommerce-product-details__short-description, .product-short-description")
        desc_el = soup.select_one("#tab-description, .woocommerce-Tabs-panel--description, .product-description")

        full_text = " ".join([
            title.get_text(" ", strip=True) if title else "",
            short_desc_el.get_text(" ", strip=True) if short_desc_el else "",
            desc_el.get_text(" ", strip=True) if desc_el else "",
            json.dumps(attrs, ensure_ascii=False),
        ]).lower()

        v_match = re.search(r"(\d{2,3})\s*(?:[-–]\s*\d{2,3}\s*)?в(?:ольт)?\b", full_text)
        p_match = re.search(r"(\d+(?:[.,]\d+)?)\s*вт\b", full_text)

        return {
            "url": url,
            "title": title.get_text(" ", strip=True) if title else "",
            "sku": sku.get_text(strip=True) if sku else "",
            "categories": cats,
            "attributes": attrs,
            "short_description": short_desc_el.get_text(" ", strip=True) if short_desc_el else "",
            "has_alice": bool(re.search(r"алис|alice|яндекс|yandex", full_text, re.I)),
            "dimmable": bool(re.search(r"диммир|регулир\w* ярк|brightness|dimm", full_text, re.I)),
            "voltage": v_match.group(0) if v_match else None,
            "power": p_match.group(0) if p_match else None,
        }

    # ── основной цикл ───────────────────────────────────────────
    def run(self) -> list[dict[str, Any]]:
        print("=" * 60)
        print(f"HitePro Parser v2 (REST + bs4)  старт {datetime.now():%H:%M:%S}")
        print("=" * 60)

        print("[1/2] Получаю индекс через WP REST API...")
        index = self._fetch_index()
        print(f"  Всего товаров: {len(index)}")

        print(f"[2/2] Парсинг карточек (sleep={SLEEP}s)...")
        for i, item in enumerate(index, 1):
            url = item.get("link", "")
            slug = item.get("slug") or urlparse(url).path.rstrip("/").split("/")[-1]
            try:
                r = self.session.get(url, timeout=20)
                r.raise_for_status()
                data = self._parse_card(r.text, url)
                data["slug"] = slug
                data["category"] = item.get("category", "")
                self.products.append(data)
            except Exception as e:
                self.errors.append({"url": url, "error": str(e)})
                print(f"  [ERR {i}/{len(index)}] {slug}: {e}")
                continue

            if i % 20 == 0:
                self._save("hitepro_intermediate.json")
                print(f"  {i}/{len(index)}  ({len(self.products)} ok / {len(self.errors)} err)")
            time.sleep(SLEEP)

        self._save("hitepro_products.json", final=True)
        self._stats()
        return self.products

    def _save(self, name: str, final: bool = False) -> None:
        path = self.output_dir / name
        payload: dict[str, Any] = {
            "brand": "HitePro",
            "total_count": len(self.products),
            "products": self.products,
            "parsed_at": datetime.now().isoformat(timespec="seconds"),
        }
        if final:
            payload["errors"] = self.errors
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if final:
            print(f"\nСохранено: {path}")

    def _stats(self) -> None:
        n = len(self.products)
        if not n:
            return
        with_attrs = sum(1 for p in self.products if p["attributes"])
        with_alice = sum(1 for p in self.products if p["has_alice"])
        dimmable = sum(1 for p in self.products if p["dimmable"])
        print("\nСТАТИСТИКА")
        print(f"  товаров:             {n}")
        print(f"  с характеристиками:  {with_attrs} ({with_attrs/n*100:.1f}%)")
        print(f"  поддержка Алисы:     {with_alice}")
        print(f"  диммируемые:         {dimmable}")
        print(f"  ошибок:              {len(self.errors)}")


if __name__ == "__main__":
    HiteProParser().run()
