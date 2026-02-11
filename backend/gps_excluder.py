#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Управление исключением спутников GPS.
Создание и чтение файла Exclude.svs.
"""
from pathlib import Path
from typing import Set, Optional, List
import tkinter as tk
from tkinter import ttk

from core.app_context import APP_CONTEXT, AppContext
from core.message_system import AppMessage


class GPSExcluder:
    """
    Менеджер исключения спутников GPS.
    
    Позволяет:
        - Загружать список исключённых спутников из Exclude.svs
        - Сохранять список в Exclude.svs
        - Отображать диалог выбора спутников
    """
    
    # Все 32 спутника GPS
    ALL_SATELLITES = [f"G{i:02d}" for i in range(1, 33)]
    
    def __init__(self, context: AppContext):
        """
        :param context: Контекст приложения
        """
        self._ctx = context
        self._exclude_file = self._ctx.exclude_svs
    
    def load_excluded(self) -> Set[str]:
        """
        Загружает список исключённых спутников из файла.
        
        Returns:
            Множество имён спутников (например, {'G01', 'G05'})
        """
        excluded = set()
        
        if not self._exclude_file.exists():
            return excluded
        
        try:
            content = self._exclude_file.read_text(encoding='utf-8')
            for line in content.splitlines():
                sat = line.strip()
                if sat in self.ALL_SATELLITES:
                    excluded.add(sat)
        except Exception as e:
            print(f"Ошибка загрузки Exclude.svs: {e}")
        
        return excluded
    
    def save_excluded(self, excluded: Set[str]) -> bool:
        """
        Сохраняет список исключённых спутников в файл.
        
        Args:
            excluded: Множество имён спутников
            
        Returns:
            True если успешно
        """
        try:
            # Сортируем по номеру
            sorted_sats = sorted(excluded, key=lambda x: int(x[1:]))
            content = "\n".join(sorted_sats)
            
            self._exclude_file.write_text(content, encoding='utf-8')
            return True
            
        except Exception as e:
            print(f"Ошибка сохранения Exclude.svs: {e}")
            return False
    
    def show_dialog(self, parent: tk.Tk) -> Optional[Set[str]]:
        """
        Показывает диалог выбора исключаемых спутников.
        
        Args:
            parent: Родительское окно Tkinter
            
        Returns:
            Множество исключённых спутников или None если отменено
        """
        dialog = _GPSExclusionDialog(parent, self)
        return dialog.result


class _GPSExclusionDialog:
    """
    Внутренний класс диалога выбора спутников.
    """
    
    def __init__(self, parent: tk.Tk, excluder: GPSExcluder):
        self._excluder = excluder
        self._current_excluded = excluder.load_excluded()
        self._result: Optional[Set[str]] = None
        
        self._create_dialog(parent)
    
    def _create_dialog(self, parent: tk.Tk) -> None:
        """Создаёт диалоговое окно."""
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Исключение спутников GPS")
        self.dialog.geometry("550x600")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Центрируем
        self.dialog.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - 550) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - 600) // 2
        self.dialog.geometry(f"+{x}+{y}")
        
        self._create_widgets()
        
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_cancel)
        parent.wait_window(self.dialog)
    
    def _create_widgets(self) -> None:
        """Создаёт виджеты."""
        from frontend.themes import Theme
        
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
        
        canvas = tk.Canvas(container, bg=Theme.BG_PRIMARY, highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable = tk.Frame(canvas, bg=Theme.BG_PRIMARY)
        
        scrollable.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Создаём чекбоксы
        self._vars = {}
        
        # Располагаем по 5 в ряд
        for i, sat in enumerate(self._excluder.ALL_SATELLITES):
            row = i // 5
            col = i % 5
            
            if col == 0:
                row_frame = tk.Frame(scrollable, bg=Theme.BG_PRIMARY)
                row_frame.grid(row=row, column=0, sticky="w", pady=2)
            
            var = tk.BooleanVar(value=sat not in self._current_excluded)
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
        
        from frontend.widgets import ModernButton
        
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
    
    def _select_all(self) -> None:
        """Выбирает все спутники (включает)."""
        for var in self._vars.values():
            var.set(True)
    
    def _deselect_all(self) -> None:
        """Сбрасывает все спутники (исключает)."""
        for var in self._vars.values():
            var.set(False)
    
    def _on_save(self) -> None:
        """Сохраняет выбор."""
        excluded = {
            sat for sat, var in self._vars.items()
            if not var.get()  # Если галочка снята - исключаем
        }
        
        if self._excluder.save_excluded(excluded):
            self._result = excluded
            self.dialog.destroy()
    
    def _on_cancel(self) -> None:
        """Отменяет выбор."""
        self._result = None
        self.dialog.destroy()
    
    @property
    def result(self) -> Optional[Set[str]]:
        return self._result