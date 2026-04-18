"""
Запускатор парсеров Shelly и Hite Pro
"""

import asyncio
import sys
from pathlib import Path

# Добавляем текущую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from shelly_parser import ShellyParser
from hitepro_parser import HiteProParser


async def run_all():
    """Запуск обоих парсеров"""
    print("\n" + "🚀" * 30)
    print("ЗАПУСК ПАРСЕРОВ SHELLY И HITEPRO")
    print("🚀" * 30 + "\n")
    
    # Парсинг Shelly
    print("\n" + "=" * 60)
    print("📦 Shelly")
    print("=" * 60)
    shelly_parser = ShellyParser()
    shelly_products = await shelly_parser.run()
    
    # Парсинг HitePro
    print("\n" + "=" * 60)
    print("📦 HitePro")
    print("=" * 60)
    hitepro_parser = HiteProParser()
    hitepro_products = await hitepro_parser.run()
    
    # Итоговый отчёт
    print("\n" + "=" * 60)
    print("📊 ИТОГОВЫЙ ОТЧЁТ")
    print("=" * 60)
    print(f"Shelly:   {len(shelly_products)} товаров")
    print(f"HitePro:  {len(hitepro_products)} товаров")
    print(f"Всего:    {len(shelly_products) + len(hitepro_products)} товаров")
    
    # Создание единой БД
    await create_unified_db(shelly_products, hitepro_products)


async def create_unified_db(shelly_products, hitepro_products):
    """Создание единой базы данных из данных обоих парсеров"""
    unified = {
        'brands': {
            'Shelly': {
                'count': len(shelly_products),
                'products': shelly_products
            },
            'HitePro': {
                'count': len(hitepro_products),
                'products': hitepro_products
            }
        },
        'total_count': len(shelly_products) + len(hitepro_products),
        'created_at': __import__('datetime').datetime.now().isoformat()
    }
    
    output_dir = Path("parsed_data")
    output_dir.mkdir(exist_ok=True)
    
    filepath = output_dir / "unified_database.json"
    with open(filepath, 'w', encoding='utf-8') as f:
        __import__('json').dump(unified, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 Единая БД сохранена в {filepath}")
    print("\n✅ Готово! Данные можно использовать в GUI приложении.")


if __name__ == "__main__":
    asyncio.run(run_all())