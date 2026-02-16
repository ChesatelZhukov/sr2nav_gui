#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Точка входа в приложение SR2NAV Studio.
Корректно работает как в режиме скрипта, так и в скомпилированном EXE.
"""
import sys
import os
from pathlib import Path


def hide_console() -> None:
    """
    Скрывает консольное окно при запуске GUI в Windows.
    Безопасно обрабатывает ситуацию, если консоль отсутствует.
    """
    if sys.platform == 'win32' and not getattr(sys, 'frozen', False):
        try:
            import ctypes
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            hwnd = kernel32.GetConsoleWindow()
            if hwnd:
                user32.ShowWindow(hwnd, 0)  # 0 = SW_HIDE
        except Exception:
            pass  # Игнорируем ошибки скрытия консоли


def setup_python_path() -> None:
    """
    Добавляет корневую директорию в sys.path для корректного импорта.
    Это критически важно для скомпилированного EXE.
    """
    current_dir = Path(__file__).parent.absolute()
    if str(current_dir) not in sys.path:
        sys.path.insert(0, str(current_dir))


def safe_print(*args, **kwargs) -> None:
    """
    Безопасный print, который не падает, если stdout отсутствует.
    """
    try:
        print(*args, **kwargs)
    except (IOError, OSError, AttributeError):
        pass  # Консоль может быть скрыта или отсутствовать


def main() -> None:
    """
    Главная функция запуска приложения.
    """
    # 1. Настраиваем пути ДО любых импортов
    setup_python_path()
    
    # 2. Скрываем консоль (только после настройки путей)
    hide_console()
    
    # 3. Теперь безопасно импортируем контекст
    try:
        from core.app_context import APP_CONTEXT
    except ImportError as e:
        safe_print(f"❌ Критическая ошибка импорта: {e}")
        safe_print(f"📁 Текущая директория: {Path(__file__).parent}")
        safe_print(f"📁 sys.path: {sys.path}")
        input("Нажмите Enter для выхода...")
        sys.exit(1)
    
    # 4. Выводим информацию о запуске (только если есть консоль)
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
        pass  # Игнорируем ошибки вывода
    
    try:
        # Импортируем контроллер и запускаем приложение
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
        
        # Пытаемся показать ошибку в GUI, если tkinter доступен
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