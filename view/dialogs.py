# Путь: view/dialogs.py

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЧИСТОЕ ПРЕДСТАВЛЕНИЕ - Все диалоговые окна приложения.
НИКАКОЙ БИЗНЕС-ЛОГИКИ, только UI и вызовы контроллера!
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Callable, Optional, Dict, List, Any, Set
import os

from view.themes import Theme
from view.widgets import ModernButton

# Импортируем UIPersistence для сохранения последней папки
from view.main_window import UIPersistence


class GPSExclusionDialog:
    """
    Диалог выбора исключаемых спутников GPS.
    ТОЛЬКО UI, вся логика в контроллере!
    """
    
    ALL_SATELLITES = [f"G{i:02d}" for i in range(1, 33)]
    
    def __init__(
        self, 
        parent: tk.Tk, 
        current_excluded: Set[str],
        on_save_callback: Callable[[Set[str]], None]
    ):
        """
        Args:
            parent: Родительское окно
            current_excluded: Текущие исключённые спутники
            on_save_callback: Функция для сохранения (вызов контроллера)
        """
        self.parent = parent
        self.current_excluded = current_excluded
        self.on_save_callback = on_save_callback
        self._vars: Dict[str, tk.BooleanVar] = {}
        self.result: Optional[Set[str]] = None
        
        self._create_dialog()
    
    def _create_dialog(self):
        """Создаёт диалоговое окно."""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Исключение спутников GPS")
        self.dialog.geometry("550x600")
        self.dialog.resizable(False, False)
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        self.dialog.configure(bg=Theme.BG_PRIMARY)
        
        # Центрируем
        self.dialog.update_idletasks()
        x = self.parent.winfo_rootx() + (self.parent.winfo_width() - 550) // 2
        y = self.parent.winfo_rooty() + (self.parent.winfo_height() - 600) // 2
        self.dialog.geometry(f"+{x}+{y}")
        
        self._create_widgets()
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_cancel)
    
    def _create_widgets(self):
        """Создаёт виджеты."""
        main = tk.Frame(self.dialog, bg=Theme.BG_PRIMARY, padx=20, pady=20)
        main.pack(fill=tk.BOTH, expand=True)
        
        # Заголовок
        tk.Label(
            main,
            text="Выберите спутники для ИСКЛЮЧЕНИЯ",
            font=("Segoe UI", 12, "bold"),
            bg=Theme.BG_PRIMARY,
            fg=Theme.FG_PRIMARY,
        ).pack(pady=(0, 10))
        
        # Инструкция
        tk.Label(
            main,
            text="Снимите галочку, чтобы исключить спутник из обработки",
            font=("Segoe UI", 9),
            bg=Theme.BG_PRIMARY,
            fg=Theme.FG_SECONDARY,
        ).pack(pady=(0, 15))
        
        # Фрейм с прокруткой
        container = tk.Frame(main, bg=Theme.BG_PRIMARY)
        container.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(
            container, 
            bg=Theme.BG_PRIMARY, 
            highlightthickness=0
        )
        scrollbar = tk.Scrollbar(
            container, 
            orient="vertical", 
            command=canvas.yview
        )
        scrollable = tk.Frame(canvas, bg=Theme.BG_PRIMARY)
        
        scrollable.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Создаём чекбоксы - по 5 в ряд
        for i, sat in enumerate(self.ALL_SATELLITES):
            row = i // 5
            col = i % 5
            
            if col == 0:
                row_frame = tk.Frame(scrollable, bg=Theme.BG_PRIMARY)
                row_frame.grid(row=row, column=0, sticky="w", pady=2)
            
            # True = включён (не исключён), False = исключён
            var = tk.BooleanVar(value=sat not in self.current_excluded)
            self._vars[sat] = var
            
            cb = tk.Checkbutton(
                row_frame if col == 0 else row_frame,
                text=sat,
                variable=var,
                bg=Theme.BG_PRIMARY,
                fg=Theme.FG_PRIMARY,
                activebackground=Theme.HOVER,
                selectcolor="white",
                font=("Consolas", 10),
            )
            cb.grid(row=0, column=col, padx=10, pady=2)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Кнопки
        btn_frame = tk.Frame(main, bg=Theme.BG_PRIMARY)
        btn_frame.pack(fill=tk.X, pady=(15, 0))
        
        ModernButton(
            btn_frame,
            text="✓ Выбрать все",
            command=self._select_all,
            width=12,
        ).pack(side="left", padx=(0, 5))
        
        ModernButton(
            btn_frame,
            text="✗ Сбросить все",
            command=self._deselect_all,
            width=12,
        ).pack(side="left")
        
        ModernButton(
            btn_frame,
            text="Отмена",
            command=self._on_cancel,
            width=12,
        ).pack(side="right", padx=(5, 0))
        
        ModernButton(
            btn_frame,
            text="Сохранить",
            command=self._on_save,
            width=12,
            bg=Theme.ACCENT_BLUE,
            fg="white",
        ).pack(side="right")
    
    def _select_all(self):
        """Выбирает все спутники (включает)."""
        for var in self._vars.values():
            var.set(True)
    
    def _deselect_all(self):
        """Сбрасывает все спутники (исключает)."""
        for var in self._vars.values():
            var.set(False)
    
    def _on_save(self):
        """Сохраняет выбор и вызывает контроллер."""
        excluded = {
            sat for sat, var in self._vars.items()
            if not var.get()  # Если галочка снята - исключаем
        }
        
        self.result = excluded
        self.on_save_callback(excluded)  # Вызов контроллера!
        self.dialog.destroy()
    
    def _on_cancel(self):
        """Отменяет выбор."""
        self.result = None
        self.dialog.destroy()
    
    def show(self) -> Optional[Set[str]]:
        """Показывает диалог и возвращает результат."""
        self.parent.wait_window(self.dialog)
        return self.result


class TransformFileDialog:
    """Диалог выбора файлов для трансформации в TBL."""
    
    def __init__(
        self, 
        parent, 
        results_dir: str, 
        on_transform_callback: Callable[[List[str]], None]
    ):
        """
        Args:
            parent: Родительское окно
            results_dir: Путь к папке results
            on_transform_callback: Функция для запуска трансформации
        """
        self.parent = parent
        self.results_dir = Path(results_dir)
        self.on_transform_callback = on_transform_callback
        self._vars: Dict[str, tk.BooleanVar] = {}
        self._checkboxes: Dict[str, tk.Checkbutton] = {}
        
        # Обновляем последнюю папку при открытии диалога
        UIPersistence.set_last_dir(str(self.results_dir))
        
        self._create_dialog()
    
    def _create_dialog(self):
        """Создаёт диалоговое окно."""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Трансформация в TBL")
        self.dialog.geometry("650x600")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        self.dialog.configure(bg=Theme.BG_PRIMARY)
        
        self.dialog.update_idletasks()
        x = self.parent.winfo_rootx() + 100
        y = self.parent.winfo_rooty() + 100
        self.dialog.geometry(f"+{x}+{y}")
        
        self._create_widgets()
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _create_widgets(self):
        """Создаёт виджеты."""
        main = tk.Frame(self.dialog, bg=Theme.BG_PRIMARY, padx=20, pady=20)
        main.pack(fill=tk.BOTH, expand=True)
        
        # Заголовок
        tk.Label(
            main,
            text="🔄 Трансформация файлов в формат TBL",
            font=("Segoe UI", 14, "bold"),
            bg=Theme.BG_PRIMARY,
            fg=Theme.FG_PRIMARY,
        ).pack(anchor="w", pady=(0, 10))
        
        # Путь
        tk.Label(
            main,
            text=f"📁 {self.results_dir}",
            font=("Consolas", 10),
            bg=Theme.BG_PRIMARY,
            fg=Theme.FG_SECONDARY,
            anchor="w",
        ).pack(anchor="w", pady=(0, 15))
        
        # Фрейм с прокруткой
        container = tk.Frame(main, bg=Theme.BG_PRIMARY)
        container.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(
            container,
            bg=Theme.BG_PRIMARY,
            highlightthickness=0,
        )
        scrollbar = tk.Scrollbar(
            container,
            orient="vertical",
            command=canvas.yview,
        )
        scrollable = tk.Frame(canvas, bg=Theme.BG_PRIMARY)
        
        scrollable.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Список файлов
        file_options = [
            ("Phase_L1.VEL", "ROVER_KIN", "📊 Фаза L1"),
            ("Phase_IO.VEL", "ROVER_KIN", "📊 Фаза IO"),
            ("PhaseIOS.VEL", "ROVER_KIN", "📊 Фаза IOS"),
            ("PhaseL1S.VEL", "ROVER_KIN", "📊 Фаза L1S"),
            ("Base_Std.QC", "BASE_STD", "🏠 Стандарт базы"),
            ("Rover_Std.QC", "ROVER_STD", "🚙 Стандарт ровера"),
        ]
        
        for filename, _, description in file_options:
            file_path = self.results_dir / filename
            exists = file_path.exists()
            
            var = tk.BooleanVar(value=exists and filename == "Phase_L1.VEL")
            self._vars[filename] = var
            
            row = tk.Frame(scrollable, bg=Theme.BG_PRIMARY)
            row.pack(fill=tk.X, pady=4)
            
            # Чекбокс
            cb = tk.Checkbutton(
                row,
                variable=var,
                bg=Theme.BG_PRIMARY,
                fg=Theme.FG_PRIMARY,
                activebackground=Theme.HOVER,
                selectcolor="white" if exists else Theme.BG_PRIMARY,
                state="normal" if exists else "disabled",
                font=("Segoe UI", 11),
            )
            cb.pack(side="left")
            self._checkboxes[filename] = cb
            
            # Информация
            info = tk.Frame(row, bg=Theme.BG_PRIMARY)
            info.pack(side="left", padx=(10, 0), fill=tk.X, expand=True)
            
            tk.Label(
                info,
                text=description,
                font=("Segoe UI", 11, "bold" if exists else "normal"),
                bg=Theme.BG_PRIMARY,
                fg=Theme.FG_PRIMARY if exists else Theme.FG_DISABLED,
                anchor="w",
            ).pack(anchor="w")
            
            tk.Label(
                info,
                text=filename,
                font=("Consolas", 9),
                bg=Theme.BG_PRIMARY,
                fg=Theme.FG_SECONDARY if exists else Theme.FG_DISABLED,
                anchor="w",
            ).pack(anchor="w")
            
            status_color = Theme.SUCCESS if exists else Theme.FG_DISABLED
            status_text = "✓ Доступен" if exists else "✗ Не найден"
            
            tk.Label(
                info,
                text=status_text,
                font=("Segoe UI", 9),
                bg=Theme.BG_PRIMARY,
                fg=status_color,
            ).pack(anchor="w")
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Кнопки
        btn_frame = tk.Frame(main, bg=Theme.BG_PRIMARY)
        btn_frame.pack(fill=tk.X, pady=(20, 0))
        
        ModernButton(
            btn_frame,
            text="✓ Выбрать все",
            command=self._select_all,
            width=12,
            font=("Segoe UI", 10),
            padx=12,
            pady=6,
        ).pack(side="left", padx=(0, 5))
        
        ModernButton(
            btn_frame,
            text="✗ Сбросить все",
            command=self._deselect_all,
            width=12,
            font=("Segoe UI", 10),
            padx=12,
            pady=6,
        ).pack(side="left")
        
        ModernButton(
            btn_frame,
            text="❌ Закрыть",
            command=self._on_close,
            width=10,
            font=("Segoe UI", 10),
            padx=12,
            pady=6,
        ).pack(side="right", padx=(5, 0))
        
        ModernButton(
            btn_frame,
            text="🔄 Трансформировать",
            bg=Theme.ACCENT_GREEN,
            fg="white",
            command=self._on_transform,
            width=18,
            font=("Segoe UI", 10, "bold"),
            padx=16,
            pady=6,
        ).pack(side="right", padx=(0, 5))
    
    def _select_all(self):
        """Выбирает все доступные файлы."""
        for filename, var in self._vars.items():
            cb = self._checkboxes.get(filename)
            if cb and cb.cget("state") == "normal":
                var.set(True)
    
    def _deselect_all(self):
        """Сбрасывает выбор всех файлов."""
        for var in self._vars.values():
            var.set(False)
    
    def _on_transform(self):
        """Запускает трансформацию через контроллер."""
        selected = [
            f for f, var in self._vars.items()
            if var.get()
        ]
        
        if not selected:
            messagebox.showwarning(
                "Внимание",
                "Не выбрано ни одного файла",
                parent=self.dialog
            )
            return
        
        self.on_transform_callback(selected)  # Вызов контроллера!
        self._on_close()
    
    def _on_close(self):
        """Закрывает диалог."""
        self.dialog.destroy()
    
    def show(self):
        """Показывает диалог."""
        self.dialog.wait_window()