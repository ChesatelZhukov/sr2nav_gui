#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Точка входа в приложение SR2NAV Studio.
"""
import sys
import os
from pathlib import Path

def hide_console() -> None:
    """Скрывает консольное окно при запуске GUI в Windows."""
    if sys.platform == 'win32' and not getattr(sys, 'frozen', False):
        try:
            import ctypes
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            hwnd = kernel32.GetConsoleWindow()
            if hwnd:
                user32.ShowWindow(hwnd, 0)
        except Exception:
            pass

def setup_python_path() -> None:
    """Добавляет корневую директорию в sys.path для корректного импорта."""
    current_dir = Path(__file__).parent.absolute()
    if str(current_dir) not in sys.path:
        sys.path.insert(0, str(current_dir))

def safe_print(*args, **kwargs) -> None:
    """Безопасный вывод в консоль, не вызывающий ошибок при отсутствии stdout."""
    try:
        print(*args, **kwargs)
    except (IOError, OSError, AttributeError):
        pass

def initialize_persistence() -> None:
    """
    Инициализирует систему персистентности UI.
    
    Создаёт директорию для конфигурационных файлов и загружает
    сохранённые настройки.
    """
    from core.app_context import APP_CONTEXT
    from view.persistence import UIPersistence
    
    # Используем рабочую директорию для хранения конфигов
    config_dir = APP_CONTEXT.working_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    
    UIPersistence.initialize(config_dir)
    safe_print(f"📁 Конфигурация UI загружена из: {config_dir}")

def main() -> None:
    """Главная функция запуска приложения."""
    # Шаг 1: Настраиваем пути ДО любых импортов проекта
    setup_python_path()
    
    # Шаг 2: Скрываем консоль
    hide_console()
    
    # Шаг 3: Инициализируем систему персистентности
    try:
        initialize_persistence()
    except Exception as e:
        safe_print(f"⚠️ Предупреждение: не удалось загрузить настройки UI: {e}")
    
    # Шаг 4: Импортируем контекст для получения информации о путях
    try:
        from core.app_context import APP_CONTEXT
    except ImportError as e:
        safe_print(f"❌ Критическая ошибка импорта: {e}")
        safe_print(f"📁 Текущая директория: {Path(__file__).parent}")
        safe_print(f"📁 sys.path: {sys.path}")
        input("Нажмите Enter для выхода...")
        sys.exit(1)
    
    # Шаг 5: Выводим информацию о запуске
    try:
        safe_print("=" * 60)
        safe_print("🚀 SR2NAV Studio v2.0.0")
        safe_print("=" * 60)
        safe_print(f"📁 Рабочая директория: {APP_CONTEXT.working_dir}")
        safe_print(f"📁 Результаты: {APP_CONTEXT.results_dir}")
        safe_print(f"📁 TBL файлы: {APP_CONTEXT.tbl_dir}")
        safe_print("=" * 60)
        safe_print()
    except Exception:
        pass
    
    # Шаг 6: Запуск основного приложения
    try:
        from controller.app_controller import ApplicationController
        
        app = ApplicationController()
        app.run()
        
    except KeyboardInterrupt:
        safe_print("\n👋 Программа завершена пользователем")
        sys.exit(0)
        
    except Exception as e:
        safe_print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        
        # Пытаемся показать ошибку в GUI-диалоге
        try:
            import tkinter as tk
            from tkinter import messagebox
            
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Критическая ошибка",
                f"Программа завершилась с ошибкой:\n\n{str(e)}\n\n"
                f"Подробности в консоли."
            )
            root.destroy()
        except Exception:
            input("\nНажмите Enter для выхода...")
        
        sys.exit(1)

if __name__ == "__main__":
    main()