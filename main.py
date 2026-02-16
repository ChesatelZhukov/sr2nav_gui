#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Точка входа в приложение SR2NAV Studio.
Корректно работает как в режиме скрипта, так и в скомпилированном EXE.
"""
import sys
import os
from pathlib import Path

# Скрываем консольное окно при запуске GUI
if sys.platform == 'win32' and not getattr(sys, 'frozen', False):
    try:
        import ctypes
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            user32.ShowWindow(hwnd, 0)  # 0 = SW_HIDE
    except Exception:
        pass

# Добавляем корневую директорию в PATH для корректного импорта при компиляции
current_dir = Path(__file__).parent.absolute()
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# Импортируем контекст приложения для проверки
from core.app_context import APP_CONTEXT


def main() -> None:
    """
    Главная функция запуска приложения.
    """
    print("=" * 60)
    print("🚀 SR2NAV Studio v2.0.0")
    print("=" * 60)
    print(f"📁 Рабочая директория: {APP_CONTEXT.working_dir}")
    print(f"📁 Результаты: {APP_CONTEXT.results_dir}")
    print(f"📁 TBL файлы: {APP_CONTEXT.tbl_dir}")
    print("=" * 60)
    print()
    
    try:
        # Импортируем контроллер и запускаем приложение
        from controller.app_controller import ApplicationController
        
        app = ApplicationController()
        app.run()
        
    except KeyboardInterrupt:
        print("\n👋 Программа завершена пользователем")
        sys.exit(0)
        
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
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
        except:
            pass
        
        sys.exit(1)


if __name__ == "__main__":
    main()