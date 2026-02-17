#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Главное окно приложения (View в паттерне MVC).

Отвечает за:
    - Отображение всех элементов интерфейса
    - Получение пользовательского ввода
    - Отправку событий в контроллер
    - Обновление UI по командам контроллера
    - Отображение сообщений из очереди

Архитектурные принципы:
    - НИКАКОЙ бизнес-логики - все проверки и операции в контроллере
    - НИКАКИХ проверок существования файлов - это ответственность контроллера
    - Все события UI преобразуются в вызовы методов контроллера
    - Сообщения получаются из очереди и отображаются с цветовой подсветкой

Взаимодействие с контроллером:
    - Контроллер передаётся в __init__ и вызывается для всех событий
    - Контроллер может обновлять UI через публичные методы (update_*, set_*)
    - Контроллер публикует сообщения в очередь, которую окно периодически опрашивает
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
from view.persistence import UIPersistence  # Сохранение состояния UI


class MainWindow:
    """
    Главное окно приложения - центральный элемент пользовательского интерфейса.

    Содержит все виджеты для работы с файлами, параметрами обработки
    и отображения результатов. Не содержит бизнес-логики - все действия
    делегируются контроллеру.

    Зоны ответственности:
        1. Отрисовка UI и управление виджетами
        2. Получение ввода пользователя и вызов методов контроллера
        3. Обновление UI по команде контроллера
        4. Отображение сообщений из очереди с цветовой подсветкой

    Важные архитектурные решения:
        - Класс НЕ ПРОВЕРЯЕТ существование файлов - это ответственность контроллера
        - Все колбэки от виджетов вызывают методы контроллера (on_*)
        - Контроллер обновляет UI через публичные методы (update_*, set_*)
        - Сообщения получаются через периодический опрос очереди

    Attributes:
        _controller: Экземпляр контроллера приложения
        _file_widgets: Словарь виджетов выбора файлов {ключ: FileEntryWidget}
        _entry_start/end: Поля ввода временного интервала
        _entry_angle: Поле ввода угла отсечения
        _btn_terminate: Кнопка остановки процесса
        _progress_bar: Индикатор выполнения
        _status_var: Переменная статусной строки
        _output_text: Текстовое поле для вывода сообщений
        _interval_mode_label: Метка режима интервала (авто/ручной)
        _TAGS: Конфигурация цветовых тегов для подсветки сообщений
    """

    def __init__(self, controller):
        """
        Инициализация главного окна.

        Args:
            controller: Контроллер приложения для обработки событий.
                       Все пользовательские действия будут вызывать его методы.
        """
        self._controller = controller
        self._current_stitch_target = "rover"

        # UI элементы (будут созданы в _create_widgets)
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

        # Конфигурация тегов для подсветки текста в консоли вывода
        self._TAGS = {
            'debug': Theme.DEBUG,      # Отладочные сообщения
            'info': Theme.INFO,        # Информационные сообщения
            'success': Theme.SUCCESS,  # Сообщения об успехе
            'warning': Theme.WARNING,  # Предупреждения
            'error': Theme.ERROR,      # Ошибки
            'header': Theme.ACCENT_BLUE,  # Заголовки
        }

    # ==================== ПУБЛИЧНЫЙ API ДЛЯ КОНТРОЛЛЕРА ====================
    # Эти методы вызываются контроллером для обновления UI

    def run(self) -> None:
        """Запускает главное окно и входит в главный цикл обработки событий."""
        self._create_window()
        self._create_menu()
        self._create_widgets()
        self._setup_styles()
        self._auto_fill_standard_files()

        self._poll_message_queue()  # Начинаем опрос очереди сообщений
        self._root.mainloop()

    def quit_application(self) -> None:
        """Корректно завершает приложение (вызывается из контроллера)."""
        if self._root:
            self._root.quit()

    def update_window_title(self, rover_name: str) -> None:
        """
        Обновляет заголовок окна с именем файла ровера.

        Args:
            rover_name: Имя файла ровера (без пути и расширения)
        """
        if self._root:
            if rover_name and rover_name.strip():
                self._root.title(f"SR2NAV GUI — {rover_name} — Обработка GNSS данных")
            else:
                self._root.title("SR2NAV GUI — Обработка GNSS данных")

    def get_all_file_paths(self) -> Dict[str, str]:
        """
        Возвращает словарь всех путей из UI.

        Returns:
            Словарь {тип_файла: путь} для виджетов, где путь не пустой
        """
        paths = {}
        for key, widget in self._file_widgets.items():
            value = widget.get_value()
            if value:
                paths[key] = value
        return paths

    def get_sr2nav_path(self) -> str:
        """Возвращает путь к SR2Nav.exe из UI."""
        widget = self._file_widgets.get('sr2nav')
        return widget.get_value() if widget else ""

    def get_rover_path(self) -> str:
        """Возвращает путь к файлу ровера из UI."""
        widget = self._file_widgets.get('rover')
        return widget.get_value() if widget else ""

    def set_file_path(self, key: str, path: str) -> None:
        """
        Устанавливает путь в конкретный виджет.

        Используется для начальной загрузки из хранилища и после операции сшивки.

        Args:
            key: Тип файла (rover, base1, sr2nav, ...)
            path: Путь к файлу
        """
        if key in self._file_widgets and path:
            self._file_widgets[key].set_value(path)

    def get_cutoff_angle(self) -> float:
        """
        Возвращает угол отсечения из UI.

        Returns:
            Значение угла в градусах (по умолчанию 7.0 при ошибке)
        """
        try:
            return float(self._entry_angle.get()) if self._entry_angle else 7.0
        except (ValueError, AttributeError):
            return 7.0

    def update_time_interval(self, start: str, end: str, is_manual: bool = False) -> None:
        """
        Обновляет поля временного интервала и индикатор режима.

        Args:
            start: Начало интервала в формате "HH:MM:SS"
            end: Конец интервала в формате "HH:MM:SS"
            is_manual: True если интервал установлен вручную, False если из Interval.exe
        """
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
        """
        Устанавливает состояние обработки (индикация выполнения).

        Args:
            is_processing: True если идёт обработка, False если остановлено
        """
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
        """
        Устанавливает текст в статусной строке.

        Args:
            message: Текст статуса
        """
        if self._status_var:
            self._status_var.set(message)

    def clear_output(self) -> None:
        """Очищает консоль вывода и показывает приветственное сообщение."""
        if self._output_text:
            self._output_text.delete(1.0, tk.END)
            self._print_welcome()
            self.set_status("🧹 Вывод очищен")
            self._root.after(2000, lambda: self.set_status("✅ Готов к работе"))

    def show_error(self, title: str, message: str):
        """
        Показывает модальное сообщение об ошибке.

        Args:
            title: Заголовок окна
            message: Текст ошибки
        """
        messagebox.showerror(title, message, parent=self._root)

    @property
    def window(self) -> tk.Tk:
        """Возвращает корневое окно Tkinter для использования в диалогах."""
        return self._root

    # ==================== ПРИВАТНЫЕ МЕТОДЫ СОЗДАНИЯ UI ====================

    def _create_window(self) -> None:
        """Создаёт главное окно с базовыми параметрами."""
        self._root = tk.Tk()
        self._root.title("SR2NAV GUI — Обработка GNSS данных")
        self._root.geometry("1400x850")
        self._root.minsize(1400, 850)
        self._root.configure(bg=Theme.BG_PRIMARY)

        self._center_window()
        self._root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _center_window(self) -> None:
        """Центрирует окно на экране."""
        self._root.update_idletasks()
        width = self._root.winfo_width()
        height = self._root.winfo_height()
        x = (self._root.winfo_screenwidth() // 2) - (width // 2)
        y = (self._root.winfo_screenheight() // 2) - (height // 2)
        self._root.geometry(f'{width}x{height}+{x}+{y}')

    def _on_closing(self):
        """Обработчик закрытия окна - делегирует контроллеру."""
        self._controller.on_app_closing()

    def _setup_styles(self) -> None:
        """Настраивает стили ttk для прогресс-бара."""
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(
            'Accent.Horizontal.TProgressbar',
            background=Theme.ACCENT_BLUE,
            troughcolor=Theme.BORDER,
            bordercolor=Theme.BORDER,
        )

    def _create_menu(self) -> None:
        """Создаёт главное меню приложения."""
        menubar = tk.Menu(self._root)
        self._root.config(menu=menubar)

        # Меню "Файл"
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="📁  Файл", menu=file_menu)
        file_menu.add_command(label="📂     Открыть рабочий каталог", command=self._on_open_working_dir)
        file_menu.add_separator()
        file_menu.add_command(label="🚪     Выход", command=self._on_exit)

        # Меню "Анализ"
        analysis_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="📊  Анализ", menu=analysis_menu)
        analysis_menu.add_command(
            label="📈     Анализ скоростей (VEL)",
            command=self._controller.on_analyze_velocities
        )
        analysis_menu.add_command(
            label="🛰️Анализ GPS созвездия",
            command=self._controller.on_analyze_gps_constellation
        )

        # Меню "Инструменты"
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="🔧 Инструменты", menu=tools_menu)
        tools_menu.add_command(
            label="🔄     Трансформация в TBL",
            command=self._on_show_transform_dialog
        )
        tools_menu.add_command(
            label="🚫     Исключение спутников",
            command=self._controller.on_show_gps_exclusion_dialog
        )
        tools_menu.add_separator()
        tools_menu.add_command(
            label="🧹     Очистить рабочую директорию",
            command=self._controller.on_cleanup_working_directory
        )

        # Меню "Вид"
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="👁️  Вид", menu=view_menu)
        #view_menu.add_command(label="🧹     Очистить вывод", command=self.clear_output)

        # Меню "Справка"
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="❓ Справка", menu=help_menu)
        help_menu.add_command(label="ℹ️ О программе", command=self._on_about)

    def _on_exit(self):
        """Обработчик выхода из меню."""
        self._on_closing()

    def _create_widgets(self) -> None:
        """Создаёт все виджеты главного окна."""
        main = tk.Frame(self._root, bg=Theme.BG_PRIMARY)
        main.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        self._create_top_panel(main)

        content = tk.Frame(main, bg=Theme.BG_PRIMARY)
        content.pack(fill=tk.BOTH, expand=True, pady=12)

        left = tk.Frame(content, bg=Theme.BG_PRIMARY, width=650)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        left.pack_propagate(False)

        self._create_files_panel(left)      # здесь создаются _file_widgets
        self._create_params_panel(left)

        right = tk.Frame(content, bg=Theme.BG_PRIMARY)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(6, 0))

        self._create_output_panel(right)

        self._create_status_panel(main)

        # ВЫЗЫВАЕМ КОНТРОЛЛЕР ПОСЛЕ СОЗДАНИЯ ВСЕХ ВИДЖЕТОВ
        self._controller.on_window_ready()

    def _create_top_panel(self, parent) -> None:
        """Создаёт верхнюю панель с заголовком и кнопками действий."""
        frame = tk.Frame(parent, bg=Theme.BG_SECONDARY, height=70)
        frame.pack(fill=tk.X)
        frame.pack_propagate(False)

        self._create_title_section(frame)
        self._create_action_buttons(frame)

    def _create_title_section(self, parent) -> None:
        """Создаёт секцию с заголовком приложения."""
        title_frame = tk.Frame(parent, bg=Theme.BG_SECONDARY)
        title_frame.pack(side=tk.LEFT, padx=20)

        tk.Label(
            title_frame,
            text="🚀 SR2NAV GUI",
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
        """Создаёт кнопки основных действий."""
        btn_frame = tk.Frame(parent, bg=Theme.BG_SECONDARY)
        btn_frame.pack(side=tk.RIGHT, padx=20)

        self._btn_terminate = ModernButton(
            btn_frame,
            text="⏹ Стоп",
            bg=Theme.ACCENT_RED,
            fg="white",
            state="disabled",
            command=self._on_terminate_with_confirmation,
            font=("Segoe UI", 11),
            padx=12,
            pady=4,
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
            pady=6,
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
            pady=6,
        ).pack(side=tk.RIGHT, padx=4)

    def _create_files_panel(self, parent) -> None:
        """Создаёт панель выбора файлов."""
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
        """Создаёт панель параметров обработки."""
        frame = CollapsibleFrame(parent, title="⚙️ Параметры обработки")
        frame.pack(fill=tk.X, pady=(0, 10))

        content = tk.Frame(frame.content, bg=Theme.BG_PRIMARY)
        content.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self._create_time_interval_section(content)
        self._create_angle_section(content)

    def _create_time_interval_section(self, parent):
        """Создаёт секцию временного интервала с полями ввода и кнопкой подтверждения."""
        time_frame = tk.Frame(parent, bg=Theme.BG_PRIMARY)
        time_frame.pack(fill=tk.X, pady=8)

        tk.Label(
            time_frame,
            text="⏰",
            font=("Segoe UI", 11, "bold"),
            bg=Theme.BG_PRIMARY,
            width=2,
            anchor="w",
        ).pack(side=tk.LEFT)

        tk.Label(
            time_frame,
            text="Начало:",
            font=("Segoe UI", 10),
            bg=Theme.BG_PRIMARY
        ).pack(side=tk.LEFT, padx=(0, 1))

        self._entry_start = tk.Entry(
            time_frame,
            width=21,
            font=("Consolas", 11),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY,
            bd=1,
            relief=tk.SOLID,
        )
        self._entry_start.pack(side=tk.LEFT, padx=(0, 12))
        # Убираем привязку событий к клавишам и фокусу
        # self._entry_start.bind('<KeyRelease>', self._on_interval_changed)
        # self._entry_start.bind('<FocusOut>', self._on_interval_changed)

        tk.Label(
            time_frame,
            text="Конец:",
            font=("Segoe UI", 10),
            bg=Theme.BG_PRIMARY
        ).pack(side=tk.LEFT, padx=(0, 1))

        self._entry_end = tk.Entry(
            time_frame,
            width=21,
            font=("Consolas", 11),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY,
            bd=1,
            relief=tk.SOLID,
        )
        self._entry_end.pack(side=tk.LEFT, padx=(0, 10))
        # Убираем привязку событий к клавишам и фокусу
        # self._entry_end.bind('<KeyRelease>', self._on_interval_changed)
        # self._entry_end.bind('<FocusOut>', self._on_interval_changed)

        # Кнопка подтверждения ручного ввода (дискета)
        self._btn_interval_confirm = ModernButton(
            time_frame,
            text="💾",
            width=3,
            bg=Theme.ACCENT_BLUE,
            fg="white",
            command=self._on_interval_confirm,
            font=("Segoe UI", 10),
            padx=8,
            pady=2,
        )
        self._btn_interval_confirm.pack(side=tk.LEFT, padx=(0, 5))

        self._interval_mode_label = tk.Label(
            time_frame,
            text="⚡ авто",
            font=("Segoe UI", 9),
            bg=Theme.BG_PRIMARY,
            fg=Theme.FG_SECONDARY,
        )
        self._interval_mode_label.pack(side=tk.LEFT, padx=(0, 0))

        tk.Frame(parent, height=1, bg=Theme.BORDER).pack(fill=tk.X, pady=12)

    def _on_interval_confirm(self):
        """
        Обработчик кнопки подтверждения ручного ввода интервала.
        Вызывается только при явном нажатии на кнопку с дискетой.
        Поддерживает формат GPS времени: YYYY:MM:DD:HH:MM:SS.f
        """
        if not self._entry_start or not self._entry_end:
            return

        start = self._entry_start.get().strip()
        end = self._entry_end.get().strip()

        # Валидация формата GPS времени
        if start and end:
            # Паттерн для GPS времени: YYYY:MM:DD:HH:MM:SS.0 (или с другим числом после точки)
            # Год: 4 цифры, месяц: 2, день: 2, часы: 2, минуты: 2, секунды: 2, точка, дробная часть
            import re
            # Более строгий паттерн
            gps_time_pattern = r'^\d{4}:\d{2}:\d{2}:\d{2}:\d{2}:\d{2}\.\d+$'
            # Или более мягкий паттерн, который допускает разные варианты
            gps_time_pattern_loose = r'^\d{4}:\d{2}:\d{2}:\d{2}:\d{2}:\d{2}(\.\d+)?$'
            
            if not re.match(gps_time_pattern, start):
                self._append_output(
                    f"⚠️ Неверный формат начала: {start}\n"
                    f"   Ожидается формат GPS времени: YYYY:MM:DD:HH:MM:SS.f\n"
                    f"   Например: 2024:09:22:00:30:01.0", 
                    "warning"
                )
                return
            
            if not re.match(gps_time_pattern, end):
                self._append_output(
                    f"⚠️ Неверный формат конца: {end}\n"
                    f"   Ожидается формат GPS времени: YYYY:MM:DD:HH:MM:SS.f\n"
                    f"   Например: 2024:09:22:01:30:01.0", 
                    "warning"
                )
                return

        # Передаём в контроллер
        self._controller.on_interval_manually_changed(start, end)
        
        # Визуальная обратная связь - мигание кнопки
        self._btn_interval_confirm.config(bg=Theme.ACCENT_GREEN)
        self._root.after(200, lambda: self._btn_interval_confirm.config(bg=Theme.ACCENT_BLUE))
        
        # Показываем подтверждение в консоли
        self._append_output(f"💾 Интервал сохранён: {start} - {end}", "success")

    def _create_angle_section(self, parent):
        """Создаёт секцию угла отсечения с кнопкой исключения спутников."""
        angle_frame = tk.Frame(parent, bg=Theme.BG_PRIMARY)
        angle_frame.pack(fill=tk.X, pady=8)

        tk.Label(
            angle_frame,
            text="📐 Угол отсечения:",
            font=("Segoe UI", 11, "bold"),
            bg=Theme.BG_PRIMARY,
            width=18,
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
        """Создаёт панель вывода сообщений с заголовком и кнопками."""
        frame = tk.Frame(parent, bg=Theme.BG_SECONDARY, bd=1, relief=tk.SOLID)
        frame.pack(fill=tk.BOTH, expand=True)

        self._create_output_header(frame)
        self._create_output_text_area(frame)
        self._print_welcome()

    def _create_output_header(self, parent):
        """Создаёт заголовок панели вывода с кнопками."""
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
        """Создаёт текстовую область для вывода с прокруткой."""
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

        # Настройка тегов для подсветки разных типов сообщений
        for tag_name, color in self._TAGS.items():
            if tag_name == 'error':
                self._output_text.tag_config(tag_name, foreground=color, font=("Consolas", 11, "bold"))
            elif tag_name == 'header':
                self._output_text.tag_config(tag_name, foreground=color, font=("Consolas", 11, "bold"))
            else:
                self._output_text.tag_config(tag_name, foreground=color)

    def _create_status_panel(self, parent) -> None:
        """Создаёт нижнюю панель статуса с прогресс-баром."""
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
    # Эти методы вызываются виджетами и делегируют действия контроллеру

    def _on_browse_file(self, key: str, extension: str) -> str:
        """
        Открывает диалог выбора файла и ВОЗВРАЩАЕТ путь.

        Args:
            key: Тип файла (rover, base1, sr2nav, ...)
            extension: Ожидаемое расширение файла

        Returns:
            Выбранный путь или пустая строка
        """
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
        """
        Обработчик сшивания JPS файлов.

        Args:
            source_key: Ключ поля, куда установить результат (rover/base1/base2)
        """
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
                target_key=source_key
            )

    def _on_open_working_dir(self) -> None:
        """Открывает рабочий каталог в системном файловом менеджере."""
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
        """Показывает диалог 'О программе' с информацией о версии."""
        from core.app_context import APP_CONTEXT

        about_text = f"""
╔══════════════════════════════════════╗
            🚀 SR2NAV GUI v1              
          Обработка GNSS данных           
╚══════════════════════════════════════╝

📁 Рабочая директория:
{APP_CONTEXT.working_dir}

👨‍💻 kurakov@aerogeo.ru
📅 © 2026

⚙️ Версия ядра: 1.0.0
🎨 Версия UI: 1.0.0
        """

        messagebox.showinfo(
            "О программе",
            about_text.strip(),
            parent=self._root
        )

    def _on_interval_changed(self, event=None):
        """
        Вызывается при изменении полей интервала пользователем.
        Передаёт новые значения в контроллер ТОЛЬКО если они реально изменились.
        """
        if not self._entry_start or not self._entry_end:
            return

        new_start = self._entry_start.get().strip()
        new_end = self._entry_end.get().strip()

        # Получаем текущие значения, которые хранятся в контроллере через FileManager
        # Это более надежный способ, чем хранить их в самом виджете.
        # Для этого нужно будет добавить метод в контроллер, но чтобы не усложнять,
        # будем считать, что если поля пустые, то это сброс.
        # В качестве простого решения для предотвращения ложных срабатываний,
        # будем использовать атрибуты самого виджета для хранения предыдущего значения.
        if not hasattr(self, '_last_interval_start'):
            self._last_interval_start = ""
            self._last_interval_end = ""

        # Проверяем, изменилось ли значение
        if new_start == self._last_interval_start and new_end == self._last_interval_end:
            # Значение не изменилось, игнорируем событие
            return

        # Обновляем сохраненные значения
        self._last_interval_start = new_start
        self._last_interval_end = new_end

        # Передаем в контроллер только при реальном изменении
        self._controller.on_interval_manually_changed(new_start, new_end)

    def _on_terminate_with_confirmation(self):
        """Останавливает текущий процесс с подтверждением пользователя."""
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
            self.set_status("⏹ Остановка процесса...")
            self._controller.on_terminate_process()

    def _copy_output(self) -> None:
        """Копирует содержимое консоли вывода в буфер обмена."""
        if self._output_text:
            content = self._output_text.get(1.0, tk.END)
            self._root.clipboard_clear()
            self._root.clipboard_append(content)
            self.set_status("📋 Скопировано")
            self._root.after(2000, lambda: self.set_status("✅ Готов к работе"))

    # ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================

    def _auto_fill_standard_files(self) -> None:
        """Автоматически заполняет стандартные файлы, если они существуют в рабочей директории."""
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
        """
        Периодически опрашивает очередь сообщений контроллера.

        Извлекает сообщения из очереди и отображает их в консоли вывода
        с соответствующей цветовой подсветкой. Обрабатывает до 20 сообщений
        за один цикл, чтобы не блокировать UI.
        """
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
        """
        Добавляет текст в консоль вывода с указанным тегом подсветки.

        Args:
            text: Текст для добавления
            tag: Тег подсветки (debug, info, success, warning, error, header)
        """
        if self._output_text:
            self._output_text.insert(tk.END, text + "\n", tag if tag else ())
            self._output_text.see(tk.END)

    def _print_welcome(self) -> None:
        """Выводит приветственное сообщение в консоль при запуске."""
        from core.app_context import APP_CONTEXT

        welcome = f"""
{'═'*80}
🚀 SR2NAV GUI v1
📅 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
📁 {APP_CONTEXT.working_dir}
{'═'*80}

✅ Система готова к работе
        """
        self._append_output(welcome.strip(), "header")