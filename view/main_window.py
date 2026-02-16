#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЧИСТОЕ ПРЕДСТАВЛЕНИЕ - Главное окно приложения.
ТОЛЬКО UI, НИКАКИХ ПРОВЕРОК СУЩЕСТВОВАНИЯ ФАЙЛОВ!
Все события передаются в контроллер.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Dict, Optional, List, Tuple, Callable
from datetime import datetime
import os
import sys
import subprocess

from view.themes import Theme
from view.widgets import (
    ModernButton,
    FileEntryWidget,
    CollapsibleFrame,
)
from view.persistence import UIPersistence  # ИСПРАВЛЕНО: вынесли в отдельный модуль


class MainWindow:
    """
    ЧИСТОЕ ПРЕДСТАВЛЕНИЕ - Главное окно приложения.
    
    Зоны ответственности:
    1. Отрисовка UI
    2. Получение ввода пользователя
    3. Отправка событий в контроллер
    4. Обновление UI по команде контроллера
    
    НИКАКОЙ БИЗНЕС-ЛОГИКИ, НИКАКИХ ПРОВЕРОК ФАЙЛОВ!
    """
    
    def __init__(self, controller):
        """
        Инициализация главного окна.
        
        Args:
            controller: Контроллер приложения для обработки событий
        """
        self._controller = controller
        self._current_stitch_target = "rover"
        # UI элементы
        self._root: Optional[tk.Tk] = None
        self._file_widgets: Dict[str, FileEntryWidget] = {}
        self._entry_start: Optional[tk.Entry] = None
        self._entry_end: Optional[tk.Entry] = None
        self._entry_angle: Optional[tk.Entry] = None
        self._btn_terminate: Optional[ModernButton] = None
        self._progress_bar: Optional[ttk.Progressbar] = None
        self._status_var: Optional[tk.StringVar] = None
        self._output_text: Optional[tk.Text] = None
        self._interval_mode_label: Optional[tk.Label] = None
        
        # Конфигурация тегов для подсветки текста
        self._TAGS = {
            'debug': Theme.DEBUG,
            'info': Theme.INFO,
            'success': Theme.SUCCESS,  # ДОБАВЛЕНО
            'warning': Theme.WARNING,
            'error': Theme.ERROR,
            'header': Theme.ACCENT_BLUE,
        }
    
    # ==================== ПУБЛИЧНЫЙ API ====================
    
    def run(self) -> None:
        """Запуск главного окна."""
        self._create_window()
        self._create_menu()
        self._create_widgets()
        self._setup_styles()
        self._auto_fill_standard_files()
        
        self._poll_message_queue()
        self._root.mainloop()
    
    def quit_application(self) -> None:
        """Корректное завершение приложения (вызывается из контроллера)."""
        if self._root:
            self._root.quit()

    def update_window_title(self, rover_name: str) -> None:
        """Обновляет заголовок окна с именем ровера."""
        if self._root:
            if rover_name and rover_name.strip():
                self._root.title(f"SR2NAV Studio — {rover_name} — Обработка GNSS данных")
            else:
                self._root.title("SR2NAV Studio — Обработка GNSS данных")

    # ==================== МЕТОДЫ ДЛЯ КОНТРОЛЛЕРА ====================
    
    def get_all_file_paths(self) -> Dict[str, str]:
        """Возвращает словарь {тип_файла: путь} из UI."""
        paths = {}
        for key, widget in self._file_widgets.items():
            value = widget.get_value()
            if value:
                paths[key] = value
        return paths
    
    def get_sr2nav_path(self) -> str:
        """Возвращает путь к SR2Nav.exe."""
        widget = self._file_widgets.get('sr2nav')
        return widget.get_value() if widget else ""
    
    def get_rover_path(self) -> str:
        """Возвращает путь к файлу ровера."""
        widget = self._file_widgets.get('rover')
        return widget.get_value() if widget else ""
    
    def sync_file_paths(self, paths: Dict[str, str]) -> None:
        """Синхронизирует пути из бэкенда в UI."""
        for key, path in paths.items():
            if key in self._file_widgets and path:
                current = self._file_widgets[key].get_value()
                if current != path:
                    self._file_widgets[key].set_value(path)
    
    def set_file_path(self, key: str, path: str) -> None:
        """Устанавливает путь в конкретный виджет."""
        if key in self._file_widgets and path:
            self._file_widgets[key].set_value(path)
    
    def get_cutoff_angle(self) -> float:
        """Возвращает угол отсечения."""
        try:
            return float(self._entry_angle.get()) if self._entry_angle else 7.0
        except (ValueError, AttributeError):
            return 7.0
    
    def update_time_interval(self, start: str, end: str, is_manual: bool = False) -> None:
        """Обновляет поля временного интервала."""
        if self._entry_start:
            self._entry_start.delete(0, tk.END)
            self._entry_start.insert(0, start)
        if self._entry_end:
            self._entry_end.delete(0, tk.END)
            self._entry_end.insert(0, end)
        
        if self._interval_mode_label:
            if is_manual:
                self._interval_mode_label.config(
                    text="✏️ ручной",
                    fg=Theme.ACCENT_ORANGE
                )
                self._append_output(f"⏱ Интервал (ручной): {start} - {end}", "info")
            else:
                self._interval_mode_label.config(
                    text="⚡ авто",
                    fg=Theme.FG_SECONDARY
                )
                self._append_output(f"⏱ Интервал (авто): {start} - {end}", "info")
    
    def set_processing_state(self, is_processing: bool) -> None:
        """Устанавливает состояние обработки (индикация)."""
        if is_processing:
            self._status_var.set("⏳ Выполнение операции...")
            self._progress_bar.start(10)
            if self._btn_terminate:
                self._btn_terminate.config(state="normal")
        else:
            self._status_var.set("✅ Готов к работе")
            self._progress_bar.stop()
            if self._btn_terminate:
                self._btn_terminate.config(state="disabled")
    
    def set_status(self, message: str):
        """Устанавливает текст статуса."""
        if self._status_var:
            self._status_var.set(message)
    
    def clear_output(self) -> None:
        """Очищает консоль вывода."""
        if self._output_text:
            self._output_text.delete(1.0, tk.END)
            self._print_welcome()
            self.set_status("🧹 Вывод очищен")
            self._root.after(2000, lambda: self.set_status("✅ Готов к работе"))
    
    def show_error(self, title: str, message: str):
        """Показывает сообщение об ошибке (для контроллера)."""
        messagebox.showerror(title, message, parent=self._root)
    
    @property
    def window(self) -> tk.Tk:
        """Возвращает корневое окно Tkinter."""
        return self._root
    
    # ==================== ПРИВАТНЫЕ МЕТОДЫ СОЗДАНИЯ UI ====================
    
    def _create_window(self) -> None:
        """Создание главного окна."""
        self._root = tk.Tk()
        self._root.title("SR2NAV Studio — Обработка GNSS данных")
        self._root.geometry("1400x850")
        self._root.minsize(1400, 850)
        self._root.configure(bg=Theme.BG_PRIMARY)
        
        self._center_window()
        self._root.protocol("WM_DELETE_WINDOW", self._on_closing)
    
    def _center_window(self) -> None:
        """Центрирование окна на экране."""
        self._root.update_idletasks()
        width = self._root.winfo_width()
        height = self._root.winfo_height()
        x = (self._root.winfo_screenwidth() // 2) - (width // 2)
        y = (self._root.winfo_screenheight() // 2) - (height // 2)
        self._root.geometry(f'{width}x{height}+{x}+{y}')
    
    def _on_closing(self):
        """Закрытие окна - передаём управление контроллеру."""
        self._controller.on_app_closing()
    
    def _setup_styles(self) -> None:
        """Настройка стилей ttk."""
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(
            'Accent.Horizontal.TProgressbar',
            background=Theme.ACCENT_BLUE,
            troughcolor=Theme.BORDER,
            bordercolor=Theme.BORDER,
        )
    
    def _create_menu(self) -> None:
        """Создание меню приложения."""
        menubar = tk.Menu(self._root)
        self._root.config(menu=menubar)
        
        # Файл
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="📁 Файл", menu=file_menu)
        file_menu.add_command(label="📂 Открыть рабочий каталог", command=self._on_open_working_dir)
        file_menu.add_separator()
        file_menu.add_command(label="🚪 Выход", command=self._on_exit)
        
        # Анализ
        analysis_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="📊 Анализ", menu=analysis_menu)
        analysis_menu.add_command(
            label="📈 Анализ скоростей (VEL)",
            command=self._controller.on_analyze_velocities
        )
        analysis_menu.add_command(
            label="🛰️ Анализ GPS созвездия",
            command=self._controller.on_analyze_gps_constellation
        )
        
        # Инструменты
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="🔧 Инструменты", menu=tools_menu)
        tools_menu.add_command(
            label="🔄 Трансформация в TBL",
            command=self._on_show_transform_dialog
        )
        tools_menu.add_command(
            label="🚫 Исключение спутников",
            command=self._controller.on_show_gps_exclusion_dialog
        )
        # НОВЫЙ ПУНКТ МЕНЮ
        tools_menu.add_separator()
        tools_menu.add_command(
            label="🧹 Очистить рабочую директорию",
            command=self._controller.on_cleanup_working_directory
        )
        
        # Вид
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="👁️ Вид", menu=view_menu)
        view_menu.add_command(label="🧹 Очистить вывод", command=self.clear_output)
        
        # Справка
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="❓ Справка", menu=help_menu)
        help_menu.add_command(label="ℹ️ О программе", command=self._on_about)
    
    def _on_exit(self):
        """Обработчик выхода из меню."""
        self._on_closing()
    
    def _create_widgets(self) -> None:
        """Создание виджетов главного окна."""
        main = tk.Frame(self._root, bg=Theme.BG_PRIMARY)
        main.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        
        self._create_top_panel(main)
        
        content = tk.Frame(main, bg=Theme.BG_PRIMARY)
        content.pack(fill=tk.BOTH, expand=True, pady=12)
        
        left = tk.Frame(content, bg=Theme.BG_PRIMARY, width=650)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        left.pack_propagate(False)
        
        self._create_files_panel(left)
        self._create_params_panel(left)
        
        right = tk.Frame(content, bg=Theme.BG_PRIMARY)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(6, 0))
        
        self._create_output_panel(right)
        
        self._create_status_panel(main)
    
    def _create_top_panel(self, parent) -> None:
        """Верхняя панель с заголовком и кнопками."""
        frame = tk.Frame(parent, bg=Theme.BG_SECONDARY, height=70)
        frame.pack(fill=tk.X)
        frame.pack_propagate(False)
        
        self._create_title_section(frame)
        self._create_action_buttons(frame)
    
    def _create_title_section(self, parent) -> None:
        """Создает секцию с заголовком."""
        title_frame = tk.Frame(parent, bg=Theme.BG_SECONDARY)
        title_frame.pack(side=tk.LEFT, padx=20)
        
        tk.Label(
            title_frame,
            text="🚀 SR2NAV Studio",
            font=("Segoe UI", 20, "bold"),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY,
        ).pack(anchor="w")
        
        tk.Label(
            title_frame,
            text="Обработка GNSS данных",
            font=("Segoe UI", 11),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_SECONDARY,
        ).pack(anchor="w")
    
    def _create_action_buttons(self, parent) -> None:
        """Создает кнопки действий."""
        btn_frame = tk.Frame(parent, bg=Theme.BG_SECONDARY)
        btn_frame.pack(side=tk.RIGHT, padx=20)
        
        self._btn_terminate = ModernButton(
            btn_frame,
            text="⏹ Остановить",
            bg=Theme.ACCENT_RED,
            fg="white",
            state="disabled",
            command=self._on_terminate_with_confirmation,
            font=("Segoe UI", 11),
            padx=16,
            pady=8,
        )
        self._btn_terminate.pack(side=tk.RIGHT, padx=4)
        
        ModernButton(
            btn_frame,
            text="▶ SR2Nav",
            bg=Theme.ACCENT_BLUE,
            fg="white",
            command=self._controller.on_run_sr2nav,
            font=("Segoe UI", 11),
            padx=16,
            pady=8,
        ).pack(side=tk.RIGHT, padx=4)
        
        ModernButton(
            btn_frame,
            text="▶▶ Полный цикл",
            bg=Theme.ACCENT_GREEN,
            fg="white",
            font=("Segoe UI", 11, "bold"),
            command=self._controller.on_run_full_cycle,
            padx=20,
            pady=8,
        ).pack(side=tk.RIGHT, padx=4)
        
        ModernButton(
            btn_frame,
            text="⏱ Интервал",
            bg=Theme.ACCENT_ORANGE,
            fg="white",
            command=self._controller.on_run_interval,
            font=("Segoe UI", 11),
            padx=16,
            pady=8,
        ).pack(side=tk.RIGHT, padx=4)
    
    def _create_files_panel(self, parent) -> None:
        """Панель выбора файлов."""
        frame = CollapsibleFrame(parent, title="📁 Входные файлы")
        frame.pack(fill=tk.X, pady=(0, 10))
        
        frame._header.children['!label'].configure(font=("Segoe UI", 12, "bold"))
        
        content = tk.Frame(frame.content, bg=Theme.BG_PRIMARY)
        content.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        
        files = [
            ("📦 SR2Nav (exe)", "sr2nav", ".exe", False, True),
            ("🚙 Ровер (JPS)", "rover", ".jps", True, False),
            ("🏠 База 1 (JPS)", "base1", ".jps", True, False),
            ("🏠 База 2 (JPS)", "base2", ".jps", True, False),
            ("📍 POS базы 1", "pos1", ".pos", False, False),
            ("📍 POS базы 2", "pos2", ".pos", False, False),
            ("⚙️ Конфиг (cfg)", "cfg", ".cfg", False, False),
            ("🌍 Гравика (air)", "air", ".air", False, False),
        ]
        
        for label, key, ext, can_stitch, is_exe in files:
            widget = FileEntryWidget(
                content,
                label_text=label,
                browse_callback=lambda k=key, e=ext: self._on_browse_file(k, e),
                open_callback=self._controller.on_open_file,
                stitch_callback=self._on_stitch_files if can_stitch else None,
                expected_extension=ext,
                file_key=key,
            )
            widget.pack(fill=tk.X, pady=3)
            self._file_widgets[key] = widget
    
    def _create_params_panel(self, parent):
        """Панель параметров обработки."""
        frame = CollapsibleFrame(parent, title="⚙️ Параметры обработки")
        frame.pack(fill=tk.X, pady=(0, 10))
        
        content = tk.Frame(frame.content, bg=Theme.BG_PRIMARY)
        content.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        
        self._create_time_interval_section(content)
        self._create_angle_section(content)
    
    def _create_time_interval_section(self, parent):
        """Создает секцию временного интервала."""
        time_frame = tk.Frame(parent, bg=Theme.BG_PRIMARY)
        time_frame.pack(fill=tk.X, pady=8)
        
        tk.Label(
            time_frame,
            text="⏰ Интервал:",
            font=("Segoe UI", 11, "bold"),
            bg=Theme.BG_PRIMARY,
            width=12,
            anchor="w",
        ).pack(side=tk.LEFT)
        
        tk.Label(
            time_frame, 
            text="Начало:", 
            font=("Segoe UI", 10),
            bg=Theme.BG_PRIMARY
        ).pack(side=tk.LEFT, padx=(5, 2))
        
        self._entry_start = tk.Entry(
            time_frame, 
            width=18, 
            font=("Consolas", 11),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY,
            bd=1,
            relief=tk.SOLID,
        )
        self._entry_start.pack(side=tk.LEFT, padx=(0, 12))
        self._entry_start.bind('<KeyRelease>', self._on_interval_changed)
        self._entry_start.bind('<FocusOut>', self._on_interval_changed)
        
        tk.Label(
            time_frame, 
            text="Конец:", 
            font=("Segoe UI", 10),
            bg=Theme.BG_PRIMARY
        ).pack(side=tk.LEFT, padx=(5, 2))
        
        self._entry_end = tk.Entry(
            time_frame, 
            width=18, 
            font=("Consolas", 11),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY,
            bd=1,
            relief=tk.SOLID,
        )
        self._entry_end.pack(side=tk.LEFT, padx=(0, 10))
        self._entry_end.bind('<KeyRelease>', self._on_interval_changed)
        self._entry_end.bind('<FocusOut>', self._on_interval_changed)
        
        self._interval_mode_label = tk.Label(
            time_frame,
            text="⚡ авто",
            font=("Segoe UI", 9),
            bg=Theme.BG_PRIMARY,
            fg=Theme.FG_SECONDARY,
        )
        self._interval_mode_label.pack(side=tk.LEFT, padx=(10, 0))
        
        tk.Frame(parent, height=1, bg=Theme.BORDER).pack(fill=tk.X, pady=12)
    
    def _create_angle_section(self, parent):
        """Создает секцию угла отсечения."""
        angle_frame = tk.Frame(parent, bg=Theme.BG_PRIMARY)
        angle_frame.pack(fill=tk.X, pady=8)
        
        tk.Label(
            angle_frame,
            text="📐 Угол:",
            font=("Segoe UI", 11, "bold"),
            bg=Theme.BG_PRIMARY,
            width=12,
            anchor="w",
        ).pack(side=tk.LEFT)
        
        self._entry_angle = tk.Entry(
            angle_frame, 
            width=6, 
            font=("Consolas", 12, "bold"), 
            justify="center",
            bg=Theme.BG_SECONDARY,
            fg=Theme.ACCENT_BLUE,
            bd=1,
            relief=tk.SOLID,
        )
        self._entry_angle.pack(side=tk.LEFT, padx=(0, 5))
        self._entry_angle.insert(0, "7.0")
        
        tk.Label(
            angle_frame, 
            text="°", 
            font=("Segoe UI", 12, "bold"),
            bg=Theme.BG_PRIMARY,
            fg=Theme.FG_PRIMARY
        ).pack(side=tk.LEFT, padx=(0, 20))
        
        ModernButton(
            angle_frame,
            text="🚫 Исключить спутники",
            bg=Theme.ACCENT_PURPLE,
            fg="white",
            command=self._controller.on_show_gps_exclusion_dialog,
            font=("Segoe UI", 10),
            padx=16,
            pady=6,
        ).pack(side=tk.LEFT)
    
    def _create_output_panel(self, parent) -> None:
        """Панель вывода сообщений."""
        frame = tk.Frame(parent, bg=Theme.BG_SECONDARY, bd=1, relief=tk.SOLID)
        frame.pack(fill=tk.BOTH, expand=True)
        
        self._create_output_header(frame)
        self._create_output_text_area(frame)
        self._print_welcome()
    
    def _create_output_header(self, parent):
        """Создает заголовок панели вывода."""
        header = tk.Frame(parent, bg=Theme.BG_SECONDARY)
        header.pack(fill=tk.X, padx=12, pady=8)
        
        tk.Label(
            header,
            text="📋 Консоль вывода",
            font=("Segoe UI", 13, "bold"),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY,
        ).pack(side=tk.LEFT)
        
        ModernButton(
            header,
            text="🧹 Очистить",
            command=self.clear_output,
            padx=12,
            pady=4,
            font=("Segoe UI", 10),
        ).pack(side=tk.RIGHT, padx=2)
        
        ModernButton(
            header,
            text="📋 Копировать",
            command=self._copy_output,
            padx=12,
            pady=4,
            font=("Segoe UI", 10),
        ).pack(side=tk.RIGHT, padx=2)
    
    def _create_output_text_area(self, parent):
        """Создает текстовую область для вывода."""
        self._output_text = tk.Text(
            parent,
            wrap=tk.WORD,
            font=("Consolas", 11),
            bg="white",
            fg=Theme.FG_PRIMARY,
            relief=tk.FLAT,
            padx=12,
            pady=12,
        )
        
        scrollbar = tk.Scrollbar(parent, command=self._output_text.yview)
        self._output_text.configure(yscrollcommand=scrollbar.set)
        
        self._output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Настройка тегов для подсветки
        for tag_name, color in self._TAGS.items():
            if tag_name == 'error':
                self._output_text.tag_config(tag_name, foreground=color, font=("Consolas", 11, "bold"))
            elif tag_name == 'header':
                self._output_text.tag_config(tag_name, foreground=color, font=("Consolas", 11, "bold"))
            else:
                self._output_text.tag_config(tag_name, foreground=color)
    
    def _create_status_panel(self, parent) -> None:
        """Нижняя панель статуса."""
        frame = tk.Frame(parent, bg=Theme.BG_SECONDARY, height=32)
        frame.pack(fill=tk.X)
        frame.pack_propagate(False)
        
        self._progress_bar = ttk.Progressbar(
            frame,
            mode='indeterminate',
            style='Accent.Horizontal.TProgressbar',
            length=220,
        )
        self._progress_bar.pack(side=tk.LEFT, padx=15, pady=5)
        
        self._status_var = tk.StringVar(value="✅ Готов к работе")
        
        tk.Label(
            frame,
            textvariable=self._status_var,
            font=("Segoe UI", 10),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_SECONDARY,
        ).pack(side=tk.RIGHT, padx=20)
    
    # ==================== ОБРАБОТЧИКИ СОБЫТИЙ UI ====================
    
    def _on_browse_file(self, key: str, extension: str) -> str:
        """Открывает диалог выбора файла и ВОЗВРАЩАЕТ путь."""
        initial_dir = UIPersistence.get_last_dir()
        if not initial_dir:
            initial_dir = self._controller.script_dir
        
        path = filedialog.askopenfilename(
            title=f"Выберите файл - {key}",
            filetypes=[(f"{extension} файлы", f"*{extension}"), ("Все файлы", "*.*")],
            initialdir=initial_dir,
        )
        
        if path:
            UIPersistence.set_last_dir(path)
            self._controller.on_file_selected(key, path)
        
        return path or ""
    
    def _on_stitch_files(self, source_key: str = "rover") -> None:
        """Обработчик сшивания JPS файлов."""
        self._current_stitch_target = source_key
        
        initial_dir = UIPersistence.get_last_dir()
        if not initial_dir:
            initial_dir = self._controller.script_dir
        
        input_files = filedialog.askopenfilenames(
            title="Выберите JPS файлы для сшивания",
            filetypes=[("JPS файлы", "*.jps"), ("Все файлы", "*.*")],
            initialdir=initial_dir,
        )
        
        if not input_files or len(input_files) < 2:
            messagebox.showwarning(
                "Внимание",
                "Необходимо выбрать минимум 2 файла",
                parent=self._root
            )
            return
        
        UIPersistence.set_last_dir(input_files[0])
        
        output_file = filedialog.asksaveasfilename(
            title="Сохранить сшитый JPS файл как",
            defaultextension=".jps",
            filetypes=[("JPS файлы", "*.jps"), ("Все файлы", "*.*")],
            initialdir=UIPersistence.get_last_dir(),
            initialfile="merged.jps",
        )
        
        if output_file:
            UIPersistence.set_last_dir(output_file)
            self._controller.on_stitch_jps(
                list(input_files), 
                output_file,
                target_key=source_key  # ИСПРАВЛЕНО: теперь используется
            )
    
    def _on_open_working_dir(self) -> None:
        """Открывает рабочий каталог в проводнике."""
        path = self._controller.script_dir
        
        if not os.path.exists(path):
            self.show_error("Ошибка", f"Папка не найдена:\n{path}")
            return
        
        try:
            if sys.platform == 'win32':
                subprocess.Popen(['explorer', path], shell=False)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', path])
            else:
                subprocess.Popen(['xdg-open', path])
        except Exception as e:
            self._append_output(f"❌ Ошибка открытия папки: {e}", "error")
    
    def _on_show_transform_dialog(self) -> None:
        """Показывает диалог трансформации файлов."""
        from view.dialogs import TransformFileDialog
        
        # Используем последнюю использованную папку или рабочую директорию
        initial_dir = UIPersistence.get_last_dir()
        if not initial_dir:
            from core.app_context import APP_CONTEXT
            initial_dir = str(APP_CONTEXT.working_dir)
        
        dialog = TransformFileDialog(
            self._root,
            initial_dir,
            self._controller.on_transform_files,
        )
        dialog.show()
    
    def _on_about(self) -> None:
        """Показывает диалог 'О программе'."""
        from core.app_context import APP_CONTEXT
        
        about_text = f"""
╔══════════════════════════════════════╗
║        🚀 SR2NAV Studio v2.0         ║
║     Обработка GNSS данных           ║
╚══════════════════════════════════════╝

📁 Рабочая директория:
{APP_CONTEXT.working_dir}

👨‍💻 Разработчик: kurakov@aerogeo.ru
📅 © 2024

⚙️ Версия ядра: 2.0.0
🎨 Версия UI: 2.0.0
        """
        
        messagebox.showinfo(
            "О программе",
            about_text.strip(),
            parent=self._root
        )
    
    def _on_interval_changed(self, event=None):
        """Вызывается при изменении полей интервала пользователем."""
        if not self._entry_start or not self._entry_end:
            return
        
        start = self._entry_start.get().strip()
        end = self._entry_end.get().strip()
        
        if start and end:
            self._controller.on_interval_manually_changed(start, end)
            if self._interval_mode_label:
                self._interval_mode_label.config(
                    text="✏️ ручной",
                    fg=Theme.ACCENT_ORANGE
                )
        else:
            if self._interval_mode_label:
                self._interval_mode_label.config(
                    text="⚡ авто",
                    fg=Theme.FG_SECONDARY
                )
    
    def _on_terminate_with_confirmation(self):
        """Останавливает процесс с подтверждением."""
        result = messagebox.askyesno(
            "⏹ Подтверждение остановки",
            "Вы действительно хотите остановить текущий процесс?\n\n"
            "⚠️ ВНИМАНИЕ:\n"
            "• Все незавершенные расчеты будут прерваны\n"
            "• Результаты могут быть неполными\n\n"
            "Продолжить?",
            parent=self._root,
            icon='warning'
        )
        
        if result:
            self.set_status("⏹ Остановка процесса...")  # ИСПРАВЛЕНО: убран is_warning
            self._controller.on_terminate_process()
    
    def _copy_output(self) -> None:
        """Копирует вывод в буфер обмена."""
        if self._output_text:
            content = self._output_text.get(1.0, tk.END)
            self._root.clipboard_clear()
            self._root.clipboard_append(content)
            self.set_status("📋 Скопировано")
            self._root.after(2000, lambda: self.set_status("✅ Готов к работе"))
    
    # ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================
    
    def _auto_fill_standard_files(self) -> None:
        """Автозаполнение стандартных файлов."""
        from core.app_context import APP_CONTEXT
        
        auto_map = {
            'pos1': APP_CONTEXT.working_dir / "Base.pos",
            'pos2': APP_CONTEXT.working_dir / "Base2.pos",
            'cfg': APP_CONTEXT.working_dir / "SR2Nav.cfg",
        }
        
        for key, path in auto_map.items():
            if path.exists() and key in self._file_widgets:
                self._file_widgets[key].set_value(str(path))
                self._controller.on_file_selected(key, str(path))
                UIPersistence.update_from_path(str(path))
    
    def _poll_message_queue(self) -> None:
        """Опрашивает очередь сообщений и обновляет вывод."""
        try:
            queue = self._controller.message_queue
            processed = 0
            
            while not queue.empty() and processed < 20:
                try:
                    msg = queue.get_nowait()
                    self._append_output(msg.formatted, msg.level.tk_tag)
                    processed += 1
                except queue.Empty:
                    break
        except Exception as e:
            print(f"Ошибка в poll_message_queue: {e}")
        
        self._root.after(100, self._poll_message_queue)
    
    def _append_output(self, text: str, tag: str = None) -> None:
        """Добавляет текст в консоль вывода."""
        if self._output_text:
            self._output_text.insert(tk.END, text + "\n", tag if tag else ())
            self._output_text.see(tk.END)
    
    def _print_welcome(self) -> None:
        """Выводит приветственное сообщение."""
        from core.app_context import APP_CONTEXT
        
        welcome = f"""
{'═'*80}
🚀 SR2NAV Studio v2.0.0
📅 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
📁 {APP_CONTEXT.working_dir}
{'═'*80}

✅ Система готова к работе
        """
        self._append_output(welcome.strip(), "header")