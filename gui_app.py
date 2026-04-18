"""
GUI интерфейс для парсеров Shelly и Hite Pro
"""

import asyncio
import json
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog

# Добавляем текущую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from shelly_parser import ShellyParser
from hitepro_parser import HiteProParser


class ParserGUI:
    """GUI приложение для запуска парсеров"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Parser Shelly & HitePro v2.0.0")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)
        
        # Переменные
        self.shelly_products: List[Dict] = []
        self.hitepro_products: List[Dict] = []
        self.is_running = False
        
        # Настройка стилей
        self.setup_styles()
        
        # Создание интерфейса
        self.create_widgets()
        
    def setup_styles(self):
        """Настройка стилей приложения"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Цветовая схема
        style.configure('Title.TLabel', font=('Arial', 16, 'bold'), foreground='#2c3e50')
        style.configure('Status.TLabel', font=('Arial', 10), foreground='#7f8c8d')
        style.configure('Success.TLabel', foreground='#27ae60')
        style.configure('Error.TLabel', foreground='#e74c3c')
        style.configure('Info.TLabel', foreground='#3498db')
        
        # Кнопки
        style.configure('Start.TButton', font=('Arial', 11, 'bold'), padding=10)
        style.configure('Stop.TButton', font=('Arial', 11), padding=10)
        
    def create_widgets(self):
        """Создание элементов интерфейса"""
        # Основной контейнер
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Настройка растягивания
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)
        
        # Заголовок
        title_label = ttk.Label(
            main_frame, 
            text="🚀 Parser Shelly & HitePro", 
            style='Title.TLabel'
        )
        title_label.grid(row=0, column=0, pady=(0, 10))
        
        # Статус бар
        self.status_var = tk.StringVar(value="Готов к работе")
        status_label = ttk.Label(
            main_frame, 
            textvariable=self.status_var, 
            style='Status.TLabel'
        )
        status_label.grid(row=1, column=0, pady=(0, 10), sticky=tk.W)
        
        # Фрейм настроек
        settings_frame = ttk.LabelFrame(main_frame, text="Настройки", padding="10")
        settings_frame.grid(row=2, column=0, pady=(0, 10), sticky=(tk.W, tk.E))
        settings_frame.columnconfigure(1, weight=1)
        
        # Выбор парсеров
        ttk.Label(settings_frame, text="Парсеры:").grid(row=0, column=0, sticky=tk.W)
        
        self.shelly_var = tk.BooleanVar(value=True)
        self.hitepro_var = tk.BooleanVar(value=True)
        
        ttk.Checkbutton(settings_frame, text="Shelly", variable=self.shelly_var).grid(row=0, column=1, sticky=tk.W, padx=10)
        ttk.Checkbutton(settings_frame, text="HitePro", variable=self.hitepro_var).grid(row=0, column=2, sticky=tk.W, padx=10)
        
        # Директория сохранения
        ttk.Label(settings_frame, text="Папка сохранения:").grid(row=1, column=0, sticky=tk.W, pady=(10, 0))
        
        self.output_dir_var = tk.StringVar(value="parsed_data")
        output_entry = ttk.Entry(settings_frame, textvariable=self.output_dir_var, width=50)
        output_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=(10, 0), padx=(10, 0))
        
        ttk.Button(settings_frame, text="Обзор...", command=self.browse_folder).grid(row=1, column=2, pady=(10, 0), padx=(10, 0))
        
        # Фрейм прогресса
        progress_frame = ttk.LabelFrame(main_frame, text="Прогресс", padding="10")
        progress_frame.grid(row=3, column=0, pady=(0, 10), sticky=(tk.W, tk.E, tk.N, tk.S))
        progress_frame.columnconfigure(0, weight=1)
        progress_frame.rowconfigure(2, weight=1)
        
        # Прогресс бары
        ttk.Label(progress_frame, text="Shelly:").grid(row=0, column=0, sticky=tk.W)
        self.shelly_progress = ttk.Progressbar(progress_frame, mode='indeterminate', length=400)
        self.shelly_progress.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(10, 0))
        
        ttk.Label(progress_frame, text="HitePro:").grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        self.hitepro_progress = ttk.Progressbar(progress_frame, mode='indeterminate', length=400)
        self.hitepro_progress.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=(5, 0))
        
        # Лог
        ttk.Label(progress_frame, text="Лог операций:").grid(row=2, column=0, sticky=tk.W, pady=(10, 0))
        self.log_text = scrolledtext.ScrolledText(
            progress_frame, 
            height=15, 
            wrap=tk.WORD, 
            font=('Consolas', 9),
            bg='#f8f9fa'
        )
        self.log_text.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(5, 0))
        
        # Фрейм статистики
        stats_frame = ttk.LabelFrame(main_frame, text="Статистика", padding="10")
        stats_frame.grid(row=4, column=0, pady=(0, 10), sticky=(tk.W, tk.E))
        stats_frame.columnconfigure(1, weight=1)
        
        self.shelly_count_var = tk.StringVar(value="Shelly: 0 товаров")
        self.hitepro_count_var = tk.StringVar(value="HitePro: 0 товаров")
        self.total_count_var = tk.StringVar(value="Всего: 0 товаров")
        
        ttk.Label(stats_frame, textvariable=self.shelly_count_var).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(stats_frame, textvariable=self.hitepro_count_var).grid(row=0, column=1, sticky=tk.W)
        ttk.Label(stats_frame, textvariable=self.total_count_var, style='Info.TLabel').grid(row=0, column=2, sticky=tk.W)
        
        # Кнопки управления
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=5, column=0, pady=(10, 0))
        
        self.start_button = ttk.Button(
            button_frame, 
            text="▶️ Запустить парсинг", 
            command=self.start_parsing,
            style='Start.TButton'
        )
        self.start_button.grid(row=0, column=0, padx=(0, 10))
        
        self.stop_button = ttk.Button(
            button_frame, 
            text="⏹️ Остановить", 
            command=self.stop_parsing,
            state=tk.DISABLED,
            style='Stop.TButton'
        )
        self.stop_button.grid(row=0, column=1, padx=(0, 10))
        
        ttk.Button(
            button_frame, 
            text="📂 Открыть папку", 
            command=self.open_output_folder
        ).grid(row=0, column=2, padx=(0, 10))
        
        ttk.Button(
            button_frame, 
            text="❌ Выход", 
            command=self.root.quit
        ).grid(row=0, column=3)
        
    def browse_folder(self):
        """Выбор папки для сохранения"""
        folder = filedialog.askdirectory(initialdir=".")
        if folder:
            self.output_dir_var.set(folder)
            
    def open_output_folder(self):
        """Открытие папки с результатами"""
        output_dir = Path(self.output_dir_var.get())
        if output_dir.exists():
            import os
            if sys.platform == 'win32':
                os.startfile(output_dir)
            elif sys.platform == 'darwin':
                os.system(f'open "{output_dir}"')
            else:
                os.system(f'xdg-open "{output_dir}"')
        else:
            messagebox.showwarning("Предупреждение", f"Папка {output_dir} не существует")
            
    def log(self, message: str, level: str = "info"):
        """Добавление сообщения в лог"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        prefix = {
            "info": "ℹ️",
            "success": "✅",
            "error": "❌",
            "warning": "⚠️"
        }.get(level, "ℹ️")
        
        log_message = f"[{timestamp}] {prefix} {message}\n"
        self.log_text.insert(tk.END, log_message)
        self.log_text.see(tk.END)
        self.root.update_idletasks()
        
    def update_status(self, message: str, level: str = "info"):
        """Обновление статуса"""
        self.status_var.set(message)
        style_map = {
            "info": "Status.TLabel",
            "success": "Success.TLabel",
            "error": "Error.TLabel",
            "warning": "Error.TLabel"
        }
        # Примечание: динамическое изменение стиля требует дополнительной работы
        
    async def run_parsers_async(self):
        """Асинхронный запуск парсеров"""
        output_dir = self.output_dir_var.get()
        
        try:
            self.is_running = True
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            
            # Запуск Shelly
            if self.shelly_var.get():
                self.log("Запуск парсера Shelly...", "info")
                self.shelly_progress.start()
                self.update_status("Парсинг Shelly...")
                
                shelly_parser = ShellyParser(output_dir=output_dir)
                self.shelly_products = await shelly_parser.run()
                
                self.shelly_progress.stop()
                self.shelly_count_var.set(f"Shelly: {len(self.shelly_products)} товаров")
                self.log(f"Shelly завершён: {len(self.shelly_products)} товаров", "success")
                
            # Запуск HitePro
            if self.hitepro_var.get():
                self.log("Запуск парсера HitePro...", "info")
                self.hitepro_progress.start()
                self.update_status("Парсинг HitePro...")
                
                hitepro_parser = HiteProParser(output_dir=output_dir)
                self.hitepro_products = await hitepro_parser.run()
                
                self.hitepro_progress.stop()
                self.hitepro_count_var.set(f"HitePro: {len(self.hitepro_products)} товаров")
                self.log(f"HitePro завершён: {len(self.hitepro_products)} товаров", "success")
                
            # Создание единой БД
            if self.shelly_products or self.hitepro_products:
                self.log("Создание единой базы данных...", "info")
                await self.create_unified_db()
                
            total = len(self.shelly_products) + len(self.hitepro_products)
            self.total_count_var.set(f"Всего: {total} товаров")
            self.update_status(f"Завершено! Обработано {total} товаров", "success")
            self.log(f"✅ Парсинг завершён! Всего товаров: {total}", "success")
            
            messagebox.showinfo("Готово", f"Парсинг завершён!\n\nShelly: {len(self.shelly_products)}\nHitePro: {len(self.hitepro_products)}\nВсего: {total}")
            
        except Exception as e:
            self.log(f"Ошибка: {str(e)}", "error")
            self.update_status(f"Ошибка: {str(e)}", "error")
            messagebox.showerror("Ошибка", f"Произошла ошибка:\n{str(e)}")
            
        finally:
            self.is_running = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.shelly_progress.stop()
            self.hitepro_progress.stop()
            
    async def create_unified_db(self):
        """Создание единой базы данных"""
        unified = {
            'brands': {
                'Shelly': {
                    'count': len(self.shelly_products),
                    'products': self.shelly_products
                },
                'HitePro': {
                    'count': len(self.hitepro_products),
                    'products': self.hitepro_products
                }
            },
            'total_count': len(self.shelly_products) + len(self.hitepro_products),
            'created_at': datetime.now().isoformat()
        }
        
        output_dir = Path(self.output_dir_var.get())
        output_dir.mkdir(exist_ok=True)
        
        filepath = output_dir / "unified_database.json"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(unified, f, ensure_ascii=False, indent=2)
        
        self.log(f"Единая БД сохранена в {filepath}", "success")
        
    def start_parsing(self):
        """Запуск парсинга в отдельном потоке"""
        if not self.shelly_var.get() and not self.hitepro_var.get():
            messagebox.showwarning("Предупреждение", "Выберите хотя бы один парсер")
            return
            
        # Запуск в отдельном потоке
        thread = threading.Thread(target=self._run_in_thread, daemon=True)
        thread.start()
        
    def _run_in_thread(self):
        """Запуск асинхронного кода в потоке"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.run_parsers_async())
        loop.close()
        
    def stop_parsing(self):
        """Остановка парсинга"""
        if messagebox.askyesno("Подтверждение", "Вы уверены, что хотите остановить парсинг?"):
            self.is_running = False
            self.log("Остановка парсинга...", "warning")
            # Примечание: полная остановка требует доработки парсеров


def main():
    """Точка входа приложения"""
    root = tk.Tk()
    app = ParserGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
