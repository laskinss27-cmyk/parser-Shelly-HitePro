"""
Shelly parser — Shopify products.json (список) + HTML (характеристики).
Без Playwright. Зависимости: requests, beautifulsoup4.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

BASE = "https://www.shelly.com"
LIST_API = f"{BASE}/products.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
SLEEP = 0.8           # пауза между обычными запросами
RATE_LIMIT_PAUSE = 60 # пауза при 429
MAX_RETRIES = 4


class ShellyParser:
    def __init__(self, output_dir: str = "parsed_data", resume: bool = True):
        self.products: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.resume = resume
        self._existing_by_handle: dict[str, dict[str, Any]] = {}
        if resume:
            existing_path = self.output_dir / "shelly_products.json"
            if existing_path.exists():
                try:
                    payload = json.loads(existing_path.read_text(encoding="utf-8"))
                    for p in payload.get("products", []):
                        if p.get("handle") and p.get("attributes"):
                            self._existing_by_handle[p["handle"]] = p
                    print(f"  resume: переиспользую {len(self._existing_by_handle)} уже распарсенных")
                except Exception:
                    pass

    def _get_with_retry(self, url: str) -> requests.Response:
        """GET с обработкой 429 и сетевых ошибок."""
        for attempt in range(MAX_RETRIES):
            try:
                r = self.session.get(url, timeout=30)
                if r.status_code == 429:
                    wait = RATE_LIMIT_PAUSE * (attempt + 1)
                    print(f"    429: жду {wait}с (попытка {attempt + 1}/{MAX_RETRIES})")
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                return r
            except requests.exceptions.RequestException as e:
                if attempt == MAX_RETRIES - 1:
                    raise
                wait = 5 * (attempt + 1)
                print(f"    {type(e).__name__}: повтор через {wait}с")
                time.sleep(wait)
        raise RuntimeError(f"исчерпаны попытки для {url}")

    # ── список товаров через Shopify products.json ──────────────
    def _fetch_index(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            r = self._get_with_retry(f"{LIST_API}?limit=250&page={page}")
            chunk = r.json().get("products", [])
            if not chunk:
                break
            items.extend(chunk)
            print(f"  страница {page}: +{len(chunk)} (всего {len(items)})")
            if len(chunk) < 250:
                break
            page += 1
            time.sleep(SLEEP)
        return items

    # ── извлечение блока Specifications со страницы ─────────────
    @staticmethod
    def _extract_specs(soup: BeautifulSoup) -> dict[str, Any]:
        """Находим заголовок Specifications и парсим следующую таблицу.

        Структура: <h2 id="...-Specifications">Specifications</h2>
                   <div class="table-wrap"><table class="confluenceTable">...
        """
        spec_h2 = None
        for h in soup.find_all(["h2", "h3"]):
            txt = h.get_text(" ", strip=True).lower()
            if txt in {"specifications", "specification", "технические характеристики"}:
                spec_h2 = h
                break
        if not spec_h2:
            return {"groups": {}, "flat": {}}

        table = spec_h2.find_next("table")
        if not table:
            return {"groups": {}, "flat": {}}

        groups: dict[str, dict[str, str]] = {}
        flat: dict[str, str] = {}
        current_group = "General"

        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            # Заголовок группы — одна объединённая ячейка с жирным текстом
            if len(cells) == 1 or (len(cells) > 0 and cells[0].get("colspan") == "2"):
                text = cells[0].get_text(" ", strip=True)
                if text and (cells[0].find("strong") or cells[0].find("b")):
                    current_group = text
                    groups.setdefault(current_group, {})
                    continue
            if len(cells) >= 2:
                key = cells[0].get_text(" ", strip=True).rstrip(":")
                val = cells[1].get_text(" • ", strip=True)
                if key:
                    groups.setdefault(current_group, {})[key] = val
                    flat[key] = val
        return {"groups": groups, "flat": flat}

    # ── основной цикл ───────────────────────────────────────────
    def run(self) -> list[dict[str, Any]]:
        print("=" * 60)
        print(f"Shelly Parser v2 (Shopify API + bs4)  старт {datetime.now():%H:%M:%S}")
        print("=" * 60)

        print("[1/2] Получаю индекс через Shopify products.json...")
        index = self._fetch_index()
        print(f"  Всего товаров: {len(index)}")

        print(f"[2/2] Парсинг карточек (sleep={SLEEP}s)...")
        for i, item in enumerate(index, 1):
            handle = item.get("handle")
            url = f"{BASE}/products/{handle}"
            if handle in self._existing_by_handle:
                self.products.append(self._existing_by_handle[handle])
                continue
            try:
                r = self._get_with_retry(url)
                soup = BeautifulSoup(r.text, "html.parser")
                specs = self._extract_specs(soup)

                first_var = (item.get("variants") or [{}])[0]
                tags = item.get("tags") or []
                title = item.get("title", "")
                t_full = (title + " " + " ".join(tags)).lower()

                self.products.append({
                    "url": url,
                    "handle": handle,
                    "shopify_id": item.get("id"),
                    "title": title,
                    "vendor": item.get("vendor"),
                    "product_type": item.get("product_type"),
                    "tags": tags,
                    "sku": first_var.get("sku"),
                    "image": (item.get("images") or [{}])[0].get("src"),
                    "spec_groups": specs["groups"],
                    "attributes": specs["flat"],
                    "wifi": "wifi" in t_full,
                    "bluetooth": "bluetooth" in t_full,
                    "zwave": "z-wave" in t_full or "zwave" in t_full,
                    "matter": "matter" in t_full,
                    "dimmable": "dimmer" in t_full or "dimming" in t_full,
                    "relay": "relay" in t_full,
                })
            except Exception as e:
                self.errors.append({"url": url, "error": str(e)})
                print(f"  [ERR {i}/{len(index)}] {handle}: {e}")
                continue

            if i % 20 == 0:
                self._save("shelly_intermediate.json")
                print(f"  {i}/{len(index)}  ({len(self.products)} ok / {len(self.errors)} err)")
            time.sleep(SLEEP)

        self._save("shelly_products.json", final=True)
        self._stats()
        return self.products

    def _save(self, name: str, final: bool = False) -> None:
        path = self.output_dir / name
        payload: dict[str, Any] = {
            "brand": "Shelly",
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
        with_groups = sum(1 for p in self.products if p["spec_groups"])
        wifi = sum(1 for p in self.products if p["wifi"])
        bt = sum(1 for p in self.products if p["bluetooth"])
        zw = sum(1 for p in self.products if p["zwave"])
        dim = sum(1 for p in self.products if p["dimmable"])
        print("\nСТАТИСТИКА")
        print(f"  товаров:                {n}")
        print(f"  с характеристиками:     {with_attrs} ({with_attrs/n*100:.1f}%)")
        print(f"  с группированными spec: {with_groups}")
        print(f"  Wi-Fi: {wifi}   BT: {bt}   Z-Wave: {zw}   диммируемые: {dim}")
        print(f"  ошибок:                 {len(self.errors)}")


if __name__ == "__main__":
    ShellyParser().run()
