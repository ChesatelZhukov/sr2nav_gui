#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Окно анализа скоростей - визуализация VEL файлов.

Предоставляет графический интерфейс для просмотра результатов анализа
скоростных данных из VEL файлов, включая:
    - Пять синхронизированных графиков (V_E, V_N, V_UP, Hei, Hei 4th Diff)
    - Визуализация четвертой разности высоты для оценки резких скачков
    - Выбор отображаемых файлов через чекбоксы
    - Таблицу с результатами анализа, включая max 4th diff высоты
    - Сводную статистику по всем файлам
    - Экспорт результатов в CSV

Архитектурные принципы:
    - Только отображение данных, никаких вычислений
    - Универсальная обработка данных (поддержка dict и объектов)
    - Все операции делегируются контроллеру
    - Состояние UI сохраняется через UIPersistence
    - Все цвета берутся из централизованной темы (themes.py)
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
from pathlib import Path
import pyperclip
import math
import gc
import weakref
import logging

from view.themes import Theme
from view.widgets import ModernButton, InteractiveZoom
from core.app_context import APP_CONTEXT

logger = logging.getLogger(__name__)


class InstanceCounter:
    """
    Класс-помощник для подсчета экземпляров и отслеживания утечек памяти.
    """
    _instances = weakref.WeakSet()
    _count = 0
    
    def __init__(self):
        self.__class__._count += 1
        self.instance_id = self.__class__._count
        self.__class__._instances.add(self)
        logger.debug(f"[{self.__class__.__name__}] Создан экземпляр #{self.instance_id}. Активных: {self.get_instance_count()}, Всего создано: {self.get_total_created()}")
    
    def __del__(self):
        logger.debug(f"[{self.__class__.__name__}] Экземпляр #{getattr(self, 'instance_id', 'N/A')} удаляется.")
    
    @classmethod
    def get_instance_count(cls):
        """Возвращает количество активных (живых) экземпляров."""
        return len(cls._instances)
    
    @classmethod
    def get_total_created(cls):
        """Возвращает общее количество созданных экземпляров за все время."""
        return cls._count


class VelocityAnalysisWindow(InstanceCounter):
    """
    Окно отображения результатов анализа скоростей.
    
    Отвечает за:
        - Выбор папки с VEL файлами
        - Отображение пяти синхронизированных графиков (V_E, V_N, V_UP, Hei, Hei 4th Diff)
        - Выбор отображаемых файлов через чекбоксы
        - Табличное представление результатов
        - Сводную статистику
        - Экспорт в CSV
    
    Взаимодействие с контроллером:
        - Контроллер предоставляет данные через метод request_velocity_analysis
        - Результаты передаются через update_results
        - Экспорт делегируется controller.export_velocity_analysis
    
    Особенности реализации:
        - Универсальная обработка данных: поддерживаются как словари, так и объекты
        - Автоматическое прореживание графиков для производительности (>1000 точек)
        - Синхронизация видимости графиков с чекбоксами
        - **Новый график для визуализации 4-й разности высоты**
        - Все цвета берутся из централизованной темы
    
    Атрибуты:
        parent: Родительское окно (MainWindow)
        controller: Экземпляр контроллера приложения
        current_dir: Текущая выбранная директория
        analysis_results: Словарь с результатами анализа от контроллера
        interactive_zoom: Менеджер интерактивного зума для графиков
        current_fig: Текущая фигура matplotlib
        current_canvas: Холст для отображения графиков
        plot_lines: Словарь линий графиков для управления видимостью
        file_vars: Словарь переменных чекбоксов для выбора файлов
    """
    
    # Цвета для графиков - берутся из темы
    PLOT_COLORS = [
        Theme.ACCENT_RED,
        Theme.ACCENT_GREEN,
        Theme.WARNING,
        Theme.INFO,
        Theme.ACCENT_ORANGE,
        Theme.ACCENT_PURPLE,
        Theme.ACCENT_CYAN,
        Theme.DEBUG,
        Theme.SUCCESS,
        Theme.FG_SECONDARY,
    ]
    
    def __init__(self, parent, controller):
        """
        Инициализация окна анализа скоростей.
        
        Args:
            parent: Родительское окно (MainWindow)
            controller: Контроллер приложения для делегирования операций
        """
        super().__init__()  # Вызов конструктора InstanceCounter
        self.parent = parent
        self.controller = controller
        self.current_dir = None
        self.available_projects: Dict[str, Path] = {}  # Доступные проекты {имя: путь}
        
        # Данные
        self.analysis_results = None
        self.summary_results = None
        self.interactive_zoom = None
        self.current_fig = None
        self.current_canvas = None
        self.plot_lines = {}
        
        # Переменные для выбора файлов
        self.file_vars: Dict[str, tk.BooleanVar] = {}
        
        # UI элементы
        self._project_var = None
        self._project_combo = None
        self.progress_frame = None
        self.progress_label = None
        self.progress_bar = None
        self.status_label = None
        self.file_count_label = None
        self.file_frame = None
        self.file_container = None
        self.notebook = None
        self.plot_frame = None
        self.table_frame = None
        self.summary_frame = None
        
        # Создаем окно
        self.window = tk.Toplevel(parent)
        self.window.title("Анализ скоростей VEL файлов")
        self.window.geometry("1600x1100")
        self.window.minsize(1400, 900)
        self.window.configure(bg=Theme.BG_PRIMARY)
        
        self.center_window()
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.create_widgets()
        self._scan_available_projects()  # Сканируем проекты при открытии
        
        # Захватываем фокус, чтобы окно было модальным
        self.window.grab_set()
    
    def on_close(self):
        """
        Закрытие окна с полной очисткой ресурсов matplotlib и обработчиков.
        """
        logger.info(f"Закрытие окна VelocityAnalysisWindow #{getattr(self, 'instance_id', 'N/A')}")
        try:
            # 1. Очищаем интерактивный зум (отключает обработчики событий)
            if self.interactive_zoom:
                self.interactive_zoom.cleanup()
                self.interactive_zoom = None
            
            # 2. Закрываем фигуру matplotlib для освобождения памяти
            if self.current_fig:
                plt.close(self.current_fig)
                self.current_fig = None
            
            # 3. Уничтожаем canvas виджет
            if self.current_canvas:
                self.current_canvas.get_tk_widget().destroy()
                self.current_canvas = None
            
            # 4. Освобождаем захват и уничтожаем окно
            self.window.grab_release()
            self.window.destroy()
            
            # 5. Принудительный сбор мусора
            gc.collect()
            
            logger.debug(f"Окно #{self.instance_id} закрыто. Активных окон Velocity: {self.get_instance_count()}")
            
        except Exception as e:
            logger.error(f"Ошибка при закрытии окна: {e}")
            # Даже при ошибке пытаемся уничтожить окно
            try:
                self.window.destroy()
            except:
                pass

    def center_window(self):
        """Центрирует окно относительно родителя или экрана."""
        self.window.update_idletasks()
        width = self.window.winfo_width() or 1600
        height = self.window.winfo_height() or 1100
        
        if self.parent:
            x = self.parent.winfo_rootx() + (self.parent.winfo_width() - width) // 2
            y = self.parent.winfo_rooty() + (self.parent.winfo_height() - height) // 2
        else:
            x = (self.window.winfo_screenwidth() - width) // 2
            y = (self.window.winfo_screenheight() - height) // 2
        
        x = max(0, min(x, self.window.winfo_screenwidth() - width))
        y = max(0, min(y, self.window.winfo_screenheight() - height))
        
        self.window.geometry(f"{width}x{height}+{x}+{y}")
    
    def create_widgets(self):
        """Создаёт все виджеты окна."""
        # Главный контейнер
        main_container = tk.Frame(self.window, bg=Theme.BG_PRIMARY)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # ============ ВЕРХНЯЯ ПАНЕЛЬ С ЗАГОЛОВКОМ ============
        self.create_header(main_container)
        
        # ============ СЕКЦИЯ ВЫБОРА ПАПКИ ============
        self.create_folder_selection(main_container)
        
        # ============ ПРОГРЕСС-БАР ============
        self.create_progress_bar(main_container)
        
        # ============ ВКЛАДКИ ============
        self.create_notebook(main_container)
        
        # ============ НИЖНЯЯ ПАНЕЛЬ - ГАЛОЧКИ ФАЙЛОВ ============
        self.create_file_selector(main_container)
        
        # ============ СТАТУСНАЯ СТРОКА ============
        self.create_status_bar(main_container)
    
    def create_header(self, parent):
        """Создаёт верхнюю панель с заголовком и кнопками управления."""
        header = tk.Frame(parent, bg=Theme.BG_PRIMARY)
        header.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            header,
            text="Анализ скоростей VEL файлов",
            font=("Arial", 14, "bold"),
            fg=Theme.FG_PRIMARY,
            bg=Theme.BG_PRIMARY,
        ).pack(side=tk.LEFT)
        
        # Панель с кнопками действий
        btn_frame = tk.Frame(header, bg=Theme.BG_PRIMARY)
        btn_frame.pack(side=tk.RIGHT)

        ModernButton(
            btn_frame,
            text="⟲ Сбросить зум",
            command=self.reset_zoom,
            width=12,
            bg=Theme.ACCENT_ORANGE,
            fg="white",
            font=("Segoe UI", 10),
        ).pack(side=tk.LEFT, padx=2)

        ModernButton(
            btn_frame,
            text="📊 Экспорт CSV",
            command=self.on_export,
            width=12,
            bg=Theme.ACCENT_GREEN,
            fg="white",
            font=("Segoe UI", 10),
        ).pack(side=tk.LEFT, padx=2)

        ModernButton(
            btn_frame,
            text="✓ Выбрать все",
            command=self.select_all_files,
            width=12,
            bg=Theme.ACCENT_BLUE,
            fg="white",
            font=("Segoe UI", 10),
        ).pack(side=tk.LEFT, padx=2)

        ModernButton(
            btn_frame,
            text="✗ Сбросить все",
            command=self.deselect_all_files,
            width=12,
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY,
            font=("Segoe UI", 10),
        ).pack(side=tk.LEFT, padx=2)
    
    def create_folder_selection(self, parent):
        """
        Создаёт панель выбора проекта с выпадающим списком.
        
        Args:
            parent: Родительский фрейм
        """
        folder_frame = tk.Frame(parent, bg=Theme.BG_PRIMARY)
        folder_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(
            folder_frame,
            text="📂 Выберите проект:",
            font=("Segoe UI", 10, "bold"),
            bg=Theme.BG_PRIMARY,
            fg=Theme.FG_PRIMARY,
        ).pack(anchor="w")
        
        dir_container = tk.Frame(folder_frame, bg=Theme.BG_PRIMARY)
        dir_container.pack(fill=tk.X, pady=(5, 0))
        
        # Выпадающий список проектов
        self._project_var = tk.StringVar()
        self._project_combo = ttk.Combobox(
            dir_container,
            textvariable=self._project_var,
            state='readonly',
            font=("Segoe UI", 10),
            width=50
        )
        self._project_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self._project_combo.bind('<<ComboboxSelected>>', self._on_project_selected)
        
        # Кнопка выбора произвольной папки
        ModernButton(
            dir_container,
            text="📂 Другая папка...",
            command=self._on_browse_folder,
            width=15,
            font=("Segoe UI", 10),
            bg=Theme.ACCENT_BLUE,
            fg="white",
        ).pack(side=tk.RIGHT)
        
        tk.Frame(parent, height=1, bg=Theme.BORDER).pack(fill=tk.X, pady=(0, 10))

    # ==================== УПРАВЛЕНИЕ ПРОЕКТАМИ ====================
    
    def _scan_available_projects(self) -> None:
        """
        Сканирует рабочую директорию на наличие подпапок с VEL файлами.
        
        Результат сохраняется в self.available_projects и обновляет
        выпадающий список. При наличии проектов автоматически выбирает первый.
        """
        self.available_projects.clear()
        base_dir = APP_CONTEXT.working_dir
        
        if not base_dir.exists():
            return
        
        # Поиск подпапок с VEL файлами
        for item in base_dir.iterdir():
            if item.is_dir():
                vel_files = list(item.glob("*.VEL")) + list(item.glob("*.[Vv][Ee][Ll]"))
                if vel_files:
                    self.available_projects[item.name] = item
        
        # Обновление UI
        if self.available_projects:
            project_names = sorted(self.available_projects.keys())
            self._project_combo['values'] = project_names
            self._project_var.set(project_names[0])
            self.current_dir = self.available_projects[project_names[0]]
            self._load_data_from_folder()
        else:
            self._project_combo['values'] = ["(Нет проектов)"]
            self._project_var.set("(Нет проектов)")
            self.show_folder_selection_prompt()
    
    def _on_project_selected(self, event=None) -> None:
        """
        Обработчик выбора проекта из выпадающего списка.
        
        Args:
            event: Событие выбора (не используется)
        """
        project_name = self._project_var.get()
        if project_name and project_name in self.available_projects:
            self.current_dir = self.available_projects[project_name]
            self._load_data_from_folder()

    def _on_browse_folder(self) -> None:
        """Открывает диалог выбора произвольной папки."""
        from view.main_window import UIPersistence
        
        self.window.grab_set()
        
        initial_dir = UIPersistence.get_last_dir()
        if not initial_dir:
            initial_dir = str(APP_CONTEXT.working_dir)
        
        self.window.grab_release()
        
        directory = filedialog.askdirectory(
            title="Выберите папку с VEL файлами",
            initialdir=initial_dir,
            parent=self.window
        )
        
        if directory:
            self.current_dir = Path(directory)
            UIPersistence.set_last_dir(directory)
            
            # Добавляем в список проектов
            folder_name = self.current_dir.name
            project_key = f"{folder_name} ({self.current_dir.parent.name})"
            self.available_projects[project_key] = self.current_dir
            
            # Обновляем комбобокс
            project_names = sorted(self.available_projects.keys())
            self._project_combo['values'] = project_names
            self._project_var.set(project_key)
            
            self._load_data_from_folder()
        
        self.window.grab_set()
        self.window.lift()

    def _load_data_from_folder(self):
        """Загружает данные из выбранной папки через контроллер."""
        self.show_loading(f"Сканирование {self.current_dir.name}...")
        self.controller.request_velocity_analysis(self, str(self.current_dir))
    
    def create_notebook(self, parent):
        """Создаёт вкладки интерфейса."""
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Вкладка с графиками
        self.plot_frame = tk.Frame(self.notebook, bg=Theme.BG_PRIMARY)
        self.notebook.add(self.plot_frame, text="Графики (V_E, V_N, V_UP, Hei, Hei 4th Diff)")
        
        # Вкладка с таблицей
        self.table_frame = tk.Frame(self.notebook, bg=Theme.BG_PRIMARY)
        self.notebook.add(self.table_frame, text="Результаты")
        
        # Вкладка со сводкой
        self.summary_frame = tk.Frame(self.notebook, bg=Theme.BG_PRIMARY)
        self.notebook.add(self.summary_frame, text="Сводка")
    
    def create_file_selector(self, parent):
        """
        Создаёт нижнюю панель с чекбоксами для выбора файлов.
        
        Чекбоксы позволяют пользователю выбирать, какие файлы отображать на графиках.
        """
        self.file_frame = tk.Frame(parent, bg=Theme.BG_SECONDARY, height=40)
        self.file_frame.pack(fill=tk.X, pady=(10, 0))
        self.file_frame.pack_propagate(False)
        
        # Контейнер для галочек без прокрутки
        self.file_container = tk.Frame(self.file_frame, bg=Theme.BG_SECONDARY)
        self.file_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
    
    def create_progress_bar(self, parent):
        """Создаёт прогресс-бар для индикации длительных операций."""
        self.progress_frame = tk.Frame(parent, bg=Theme.BG_PRIMARY)
        self.progress_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.progress_label = tk.Label(
            self.progress_frame,
            text="",
            font=("Arial", 9),
            fg=Theme.FG_SECONDARY,
            bg=Theme.BG_PRIMARY,
        )
        self.progress_label.pack()
        
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            mode='indeterminate'
        )
        self.progress_bar.pack(fill=tk.X)
        
        # По умолчанию скрыт
        self.progress_frame.pack_forget()
    
    def create_status_bar(self, parent):
        """Создаёт статусную строку внизу окна."""
        status = tk.Frame(parent, bg=Theme.BG_SECONDARY, height=24)
        status.pack(fill=tk.X, pady=(5, 0))
        status.pack_propagate(False)
        
        self.status_label = tk.Label(
            status,
            text="Готов",
            font=("Arial", 9),
            fg=Theme.FG_SECONDARY,
            bg=Theme.BG_SECONDARY,
        )
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        self.file_count_label = tk.Label(
            status,
            text="0",
            font=("Arial", 9),
            fg=Theme.FG_SECONDARY,
            bg=Theme.BG_SECONDARY,
        )
        self.file_count_label.pack(side=tk.RIGHT, padx=10)
    
    # ==================== ОТОБРАЖЕНИЕ СОСТОЯНИЯ ====================
    
    def show_folder_selection_prompt(self):
        """Показывает приглашение выбрать папку при открытии окна."""
        for frame in [self.plot_frame, self.table_frame, self.summary_frame]:
            for widget in frame.winfo_children():
                widget.destroy()
            
            tk.Label(
                frame,
                text="👆 Выберите папку с VEL файлами в верхней панели",
                font=("Arial", 12),
                fg=Theme.FG_SECONDARY,
                bg=Theme.BG_PRIMARY,
            ).pack(expand=True)

    def show_loading(self, message: str):
        """
        Показывает индикатор загрузки с сообщением.
        
        Args:
            message: Текст сообщения о текущей операции
        """
        if self.progress_label:
            self.progress_label.config(text=message)
        if self.progress_frame:
            self.progress_frame.pack(fill=tk.X, pady=(0, 10))
        if self.progress_bar:
            self.progress_bar.start(10)
        self.window.update()
    
    def hide_loading(self):
        """Скрывает индикатор загрузки."""
        if self.progress_bar:
            self.progress_bar.stop()
        if self.progress_frame:
            self.progress_frame.pack_forget()
    
    def show_error(self, error: str):
        """
        Показывает сообщение об ошибке.
        
        Args:
            error: Текст ошибки
        """
        self.hide_loading()
        if self.status_label:
            self.status_label.config(text=f"Ошибка", fg=Theme.ACCENT_RED)
        
        for frame in [self.table_frame, self.plot_frame, self.summary_frame]:
            if frame:
                for widget in frame.winfo_children():
                    widget.destroy()
                
                tk.Label(
                    frame,
                    text=f"❌ {error}",
                    font=("Arial", 11),
                    fg=Theme.ACCENT_RED,
                    bg=Theme.BG_PRIMARY,
                ).pack(expand=True)
    
    # ==================== ОБРАБОТЧИКИ СОБЫТИЙ UI ====================
    
    def on_refresh(self):
        """Обновление данных (алиас для _load_data_from_folder)."""
        self.show_loading("Обновление...")
        self.controller.request_velocity_analysis(self, str(self.current_dir))
    
    def on_export(self):
        """Экспортирует результаты анализа в CSV через контроллер."""
        if not self.analysis_results:
            messagebox.showwarning("Внимание", "Нет данных", parent=self.window)
            return
        
        from view.main_window import UIPersistence
        initial_dir = UIPersistence.get_last_dir() or str(self.current_dir)
        
        filename = filedialog.asksaveasfilename(
            title="Сохранить",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Все", "*.*")],
            initialdir=initial_dir,
            initialfile=f"velocity_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        
        if filename:
            UIPersistence.set_last_dir(filename)
            success = self.controller.export_velocity_analysis(filename)
            if success:
                messagebox.showinfo("Успех", f"Сохранено", parent=self.window)
            else:
                messagebox.showerror("Ошибка", "Не удалось экспортировать", parent=self.window)
    
    # ==================== МЕТОДЫ ОБНОВЛЕНИЯ ДАННЫХ ====================
    
    def update_results(self, results: Dict, summary: Dict):
        """
        Обновляет все данные в окне после получения результатов от контроллера.
        
        Args:
            results: Словарь результатов анализа (filename -> результат)
            summary: Сводная статистика по всем файлам
        """
        self.analysis_results = results
        self.summary_results = summary
        self.hide_loading()
        
        self.update_file_list()
        self.update_results_table()
        self.update_summary(summary)
        self.update_plots()
        
        file_count = len(results) if results else 0
        if self.file_count_label:
            self.file_count_label.config(text=f"{file_count} файлов")
        
        if self.status_label:
            if file_count > 0:
                self.status_label.config(
                    text=f"Готово: {file_count} файлов",
                    fg=Theme.SUCCESS
                )
            else:
                self.status_label.config(
                    text="VEL файлы не найдены",
                    fg=Theme.WARNING
                )
    
    def update_file_list(self):
        """
        Обновляет список файлов в нижней панели с чекбоксами.
        
        Создаёт чекбокс для каждого файла с всплывающей подсказкой
        с полным именем файла при наведении.
        """
        # Очищаем старый список
        if self.file_container:
            for widget in self.file_container.winfo_children():
                widget.destroy()
        
        self.file_vars.clear()
        
        if not self.analysis_results or not self.file_container:
            if self.file_container:
                tk.Label(
                    self.file_container,
                    text="Нет файлов",
                    font=("Segoe UI", 10),
                    bg=Theme.BG_SECONDARY,
                    fg=Theme.FG_SECONDARY,
                ).pack(side=tk.LEFT, padx=5)
            return
        
        # Сортируем файлы
        sorted_files = sorted(self.analysis_results.keys())
        
        # Создаем чекбоксы для каждого файла
        for filename in sorted_files:
            var = tk.BooleanVar(value=True)
            self.file_vars[filename] = var
            
            # Обрезаем длинные имена
            display_name = filename
            if len(display_name) > 25:
                display_name = display_name[:22] + "..."
            
            cb = tk.Checkbutton(
                self.file_container,
                text=display_name,
                variable=var,
                command=self.update_plot_visibility,
                bg=Theme.BG_SECONDARY,
                fg=Theme.FG_PRIMARY,
                activebackground=Theme.HOVER,
                selectcolor=Theme.BG_PRIMARY if Theme.BG_PRIMARY != "#FFFFFF" else "white",
                font=("Consolas", 9),
                anchor="w",
            )
            cb.pack(side=tk.LEFT, padx=8)
            
            # Всплывающая подсказка с полным именем файла
            self.create_tooltip(cb, filename)
    
    def create_tooltip(self, widget, text):
        """
        Создаёт всплывающую подсказку для виджета.
        
        Args:
            widget: Виджет, к которому привязывается подсказка
            text: Текст подсказки
        """
        def show_tooltip(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
            
            label = tk.Label(
                tooltip,
                text=text,
                bg=Theme.BG_SECONDARY,
                fg=Theme.FG_PRIMARY,
                relief=tk.SOLID,
                borderwidth=1,
                font=("Consolas", 8),
                padx=5,
                pady=2
            )
            label.pack()
            
            def hide_tooltip():
                tooltip.destroy()
            
            widget.tooltip = tooltip
            widget.after(3000, hide_tooltip)
        
        def hide_tooltip(event):
            if hasattr(widget, 'tooltip'):
                widget.tooltip.destroy()
        
        widget.bind('<Enter>', show_tooltip)
        widget.bind('<Leave>', hide_tooltip)
    
    def select_all_files(self):
        """Выбирает все файлы в чекбоксах."""
        for var in self.file_vars.values():
            var.set(True)
        self.update_plot_visibility()
    
    def deselect_all_files(self):
        """Снимает выбор со всех файлов в чекбоксах."""
        for var in self.file_vars.values():
            var.set(False)
        self.update_plot_visibility()
    
    def get_selected_files(self) -> Set[str]:
        """
        Возвращает множество выбранных файлов.
        
        Returns:
            Set[str]: Имена файлов, отмеченных в чекбоксах
        """
        return {
            filename for filename, var in self.file_vars.items()
            if var.get()
        }
    
    # ==================== ОБНОВЛЕНИЕ ВКЛАДОК ====================
    
    def update_results_table(self):
        """Обновляет таблицу с результатами анализа, включая новую колонку."""
        if not self.table_frame:
            return
            
        for widget in self.table_frame.winfo_children():
            widget.destroy()
        
        if not self.analysis_results:
            tk.Label(
                self.table_frame,
                text="Нет данных",
                font=("Arial", 11),
                fg=Theme.FG_SECONDARY,
                bg=Theme.BG_PRIMARY,
            ).pack(expand=True)
            return
        
        # Добавили колонку для 4-й разности высоты
        columns = ['Файл', 'Строк', 'Время', 'V_E', 'V_N', 'V_UP', '2D', '3D', 'Hei 4th Diff']
        
        tree_frame = tk.Frame(self.table_frame, bg=Theme.BG_PRIMARY)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Настройка стилей для Treeview
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Treeview",
                        background=Theme.BG_SECONDARY,
                        foreground=Theme.FG_PRIMARY,
                        fieldbackground=Theme.BG_SECONDARY,
                        borderwidth=0)
        style.map('Treeview', background=[('selected', Theme.SELECTED)])
        style.configure("Treeview.Heading",
                        background=Theme.BG_TERTIARY,
                        foreground=Theme.FG_PRIMARY,
                        relief="flat")
        style.map("Treeview.Heading",
                  background=[('active', Theme.HOVER)])
        
        tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show='headings',
            height=20
        )
        
        widths = [200, 60, 120, 70, 70, 70, 70, 70, 100]
        for col, width in zip(columns, widths):
            tree.heading(col, text=col)
            tree.column(col, width=width, minwidth=50, anchor='center')
        
        # Добавляем данные
        for filename, result in self.analysis_results.items():
            # Универсальная проверка типа (поддержка dict и объектов)
            if isinstance(result, dict):
                data = result.get('data', {})
                stats = result.get('statistics', {})
            else:
                data = getattr(result, 'data', {})
                stats = getattr(result, 'statistics', {})
            
            # Получаем данные с проверкой типа
            if isinstance(data, dict):
                time_span = data.get('time_span', [0, 0])
                rows = stats.get('rows_analyzed', 0)
                max_v_e = stats.get('max_v_e', 0)
                max_v_n = stats.get('max_v_n', 0)
                max_v_up = stats.get('max_v_up', 0)
                max_speed_2d = stats.get('max_speed_2d', 0)
                max_speed_3d = stats.get('max_speed_3d', 0)
                max_height_4th_diff = stats.get('max_height_4th_diff', 0)
            else:
                time_span = getattr(data, 'time_span', [0, 0])
                rows = getattr(stats, 'rows_analyzed', 0)
                max_v_e = getattr(stats, 'max_v_e', 0)
                max_v_n = getattr(stats, 'max_v_n', 0)
                max_v_up = getattr(stats, 'max_v_up', 0)
                max_speed_2d = getattr(stats, 'max_speed_2d', 0)
                max_speed_3d = getattr(stats, 'max_speed_3d', 0)
                max_height_4th_diff = getattr(stats, 'max_height_4th_diff', 0)
            
            time_span_str = f"{time_span[0]:.0f}-{time_span[1]:.0f}с" if time_span and len(time_span) > 1 else "0-0с"
            
            # Форматируем числа
            display_filename = filename[:30] + "..." if len(filename) > 30 else filename
            
            values = [
                display_filename,
                rows,
                time_span_str,
                f"{max_v_e:.3f}",
                f"{max_v_n:.3f}",
                f"{max_v_up:.3f}",
                f"{max_speed_2d:.3f}",
                f"{max_speed_3d:.3f}",
                f"{max_height_4th_diff:.3f}",
            ]
            
            tree.insert('', 'end', values=values)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def update_summary(self, summary: Dict):
        """
        Обновляет вкладку со сводной статистикой.
        
        Args:
            summary: Словарь со сводной статистикой от контроллера
        """
        if not self.summary_frame:
            return
            
        for widget in self.summary_frame.winfo_children():
            widget.destroy()
        
        if not summary:
            tk.Label(
                self.summary_frame,
                text="Нет данных",
                font=("Arial", 11),
                fg=Theme.FG_SECONDARY,
                bg=Theme.BG_PRIMARY,
            ).pack(expand=True)
            return
        
        text_widget = tk.Text(
            self.summary_frame,
            font=("Consolas", 10),
            wrap=tk.WORD,
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY,
            relief=tk.FLAT,
            padx=10,
            pady=10,
        )
        
        scrollbar = tk.Scrollbar(self.summary_frame, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Настройка тегов
        text_widget.tag_config("header", foreground=Theme.ACCENT_BLUE, font=("Consolas", 11, "bold"))
        text_widget.tag_config("value", foreground=Theme.SUCCESS, font=("Consolas", 10, "bold"))
        text_widget.tag_config("warning", foreground=Theme.WARNING)
        
        max_vel = summary.get('max_velocities', {})
        max_speed = summary.get('max_speeds', {})
        max_height_diff = summary.get('max_height_4th_diff', 0)
        
        text_widget.insert(tk.END, "📊 СВОДНАЯ СТАТИСТИКА\n", "header")
        text_widget.insert(tk.END, "═"*40 + "\n\n")
        
        text_widget.insert(tk.END, f"📁 Файлов: ")
        text_widget.insert(tk.END, f"{summary.get('total_files', 0)}\n", "value")
        
        text_widget.insert(tk.END, f"\n📈 МАКСИМАЛЬНЫЕ СКОРОСТИ:\n", "header")
        text_widget.insert(tk.END, f"   V_E (Восток): ")
        text_widget.insert(tk.END, f"{max_vel.get('v_e', 0):.3f} м/с\n", "value")
        text_widget.insert(tk.END, f"   V_N (Север): ")
        text_widget.insert(tk.END, f"{max_vel.get('v_n', 0):.3f} м/с\n", "value")
        text_widget.insert(tk.END, f"   V_UP (Вертикаль): ")
        text_widget.insert(tk.END, f"{max_vel.get('v_up', 0):.3f} м/с\n", "value")
        
        text_widget.insert(tk.END, f"\n📐 МАКСИМАЛЬНЫЕ СКОРОСТИ:\n", "header")
        text_widget.insert(tk.END, f"   2D (горизонтальная): ")
        text_widget.insert(tk.END, f"{max_speed.get('2d', 0):.3f} м/с\n", "value")
        text_widget.insert(tk.END, f"   3D (полная): ")
        text_widget.insert(tk.END, f"{max_speed.get('3d', 0):.3f} м/с\n", "value")
        
        text_widget.insert(tk.END, f"\n📏 ВЫСОТА:\n", "header")
        text_widget.insert(tk.END, f"   Макс. 4-я разность: ")
        text_widget.insert(tk.END, f"{max_height_diff:.3f} м\n", "value")
        
        text_widget.insert(tk.END, f"\n{'─'*40}\n")
        text_widget.insert(tk.END, f"⚠️ Все значения в сыром виде (без фильтрации)\n", "warning")
        
        text_widget.config(state=tk.DISABLED)
    
    def update_plots(self):
        """
        Обновляет графики на основе выбранных файлов.
        Теперь отображает 5 графиков: V_E, V_N, V_UP, Hei, Hei 4th Diff.
        ВСЕ ДАННЫЕ ОТОБРАЖАЮТСЯ В СЫРОМ ВИДЕ БЕЗ ФИЛЬТРАЦИИ.
        """
        # Закрываем старую фигуру и очищаем ресурсы ПЕРЕД созданием новой
        if self.current_fig:
            plt.close(self.current_fig)
            self.current_fig = None
        
        if self.interactive_zoom:
            self.interactive_zoom.cleanup()
            self.interactive_zoom = None
        
        if self.current_canvas:
            self.current_canvas.get_tk_widget().destroy()
            self.current_canvas = None
        
        if self.plot_frame:
            for widget in self.plot_frame.winfo_children():
                widget.destroy()
        
        if not self.analysis_results or not self.plot_frame:
            if self.plot_frame:
                tk.Label(
                    self.plot_frame,
                    text="Нет данных",
                    font=("Arial", 11),
                    fg=Theme.FG_SECONDARY,
                    bg=Theme.BG_PRIMARY,
                ).pack(expand=True)
            return
        
        selected_files = self.get_selected_files()
        
        if not selected_files:
            if self.plot_frame:
                tk.Label(
                    self.plot_frame,
                    text="Не выбрано файлов",
                    font=("Arial", 11),
                    fg=Theme.WARNING,
                    bg=Theme.BG_PRIMARY,
                ).pack(expand=True)
            return
        
        try:
            # Пять графиков в одной колонке
            fig, axes = plt.subplots(5, 1, figsize=(16, 2.5), sharex=True)
            fig.patch.set_facecolor(Theme.BG_SECONDARY)
            
            self.plot_lines = {}
            
            axis_titles = {
                0: 'V_E (Восток) [м/с]',
                1: 'V_N (Север) [м/с]',
                2: 'V_UP (Вертикаль) [м/с]',
                3: 'Высота (Hei) [м]',
                4: '4-я разность высоты (Hei 4th Diff) [м] (СЫРЫЕ ДАННЫЕ)'
            }
            
            for idx, filename in enumerate(sorted(selected_files)):
                if filename not in self.analysis_results:
                    continue
                
                result = self.analysis_results[filename]
                
                # Универсальная проверка типа
                if isinstance(result, dict):
                    data = result.get('data', {})
                else:
                    data = getattr(result, 'data', {})
                
                # Получаем данные
                if isinstance(data, dict):
                    time = data.get('time', np.array([]))
                    v_e = data.get('v_e', np.array([]))
                    v_n = data.get('v_n', np.array([]))
                    v_up = data.get('v_up', np.array([]))
                    height = data.get('height', np.array([]))
                else:
                    time = getattr(data, 'time', np.array([]))
                    v_e = getattr(data, 'v_e', np.array([]))
                    v_n = getattr(data, 'v_n', np.array([]))
                    v_up = getattr(data, 'v_up', np.array([]))
                    height = getattr(data, 'height', np.array([]))
                
                # Преобразуем в numpy массивы
                if isinstance(time, list):
                    time = np.array(time)
                if isinstance(v_e, list):
                    v_e = np.array(v_e)
                if isinstance(v_n, list):
                    v_n = np.array(v_n)
                if isinstance(v_up, list):
                    v_up = np.array(v_up)
                if isinstance(height, list):
                    height = np.array(height)
                
                if len(time) == 0:
                    continue
                
                # Прореживаем для производительности (только для отображения, не меняет значения)
                plot_time = time
                plot_v_e = v_e
                plot_v_n = v_n
                plot_v_up = v_up
                plot_height = height
                
                if len(time) > 1000:
                    step = len(time) // 1000
                    plot_time = time[::step]
                    plot_v_e = v_e[::step]
                    plot_v_n = v_n[::step]
                    plot_v_up = v_up[::step]
                    plot_height = height[::step]
                
                # Получаем рассчитанную 4-ю разность из модели
                if isinstance(result, dict):
                    stats = result.get('statistics', {})
                    height_4th_diff = stats.get('height_4th_diff_array', np.array([]))
                else:
                    stats = getattr(result, 'statistics', None)
                    height_4th_diff = getattr(stats, 'height_4th_diff_array', np.array([])) if stats else np.array([])
                
                # Если по какой-то причине массив пустой или None, вычисляем на месте как запасной вариант
                if height_4th_diff is None or len(height_4th_diff) == 0:
                    height_4th_diff = self.calculate_4th_diff(height)
                
                # Применяем то же прореживание к 4-й разности, если нужно
                plot_height_4th_diff = height_4th_diff
                if len(height_4th_diff) > 1000 and len(height_4th_diff) > 0:
                    step = len(height_4th_diff) // 1000
                    plot_height_4th_diff = height_4th_diff[::step]
                
                # НИКАКОЙ ФИЛЬТРАЦИИ - ОТОБРАЖАЕМ КАК ЕСТЬ
                color = self.PLOT_COLORS[idx % len(self.PLOT_COLORS)]
                label = filename[:12] + "..." if len(filename) > 12 else filename
                
                line0, = axes[0].plot(plot_time, plot_v_e, color=color, linewidth=1.2, label=label)
                line1, = axes[1].plot(plot_time, plot_v_n, color=color, linewidth=1.2, label=label)
                line2, = axes[2].plot(plot_time, plot_v_up, color=color, linewidth=1.2, label=label)
                line3, = axes[3].plot(plot_time, plot_height, color=color, linewidth=1.2, label=label)
                line4, = axes[4].plot(plot_time, plot_height_4th_diff, color=color, linewidth=1.2, label=label)
                
                self.plot_lines[filename] = {
                    'V_E': line0,
                    'V_N': line1,
                    'V_UP': line2,
                    'Hei': line3,
                    'Hei_4th_Diff': line4
                }
            
            # Настройка форматирования времени
            from matplotlib.ticker import FuncFormatter
            
            def format_time(seconds, pos):
                if seconds is None:
                    return ""
                hours = int(seconds // 3600)
                minutes = int((seconds % 3600) // 60)
                return f"{hours:02d}:{minutes:02d}"
            
            for i in range(5):
                ax = axes[i]
                ax.xaxis.set_major_formatter(FuncFormatter(format_time))
                ax.set_ylabel(axis_titles[i].split('[')[1].replace(']', ''))
                ax.set_title(axis_titles[i], fontsize=10, fontweight='bold')
                ax.grid(True, alpha=0.3, color=Theme.BORDER)
                ax.set_facecolor(Theme.BG_SECONDARY)
                ax.tick_params(colors=Theme.FG_SECONDARY)
                for spine in ax.spines.values():
                    spine.set_color(Theme.BORDER)
                
                if i < 3 or i == 4:
                    ax.axhline(y=0, color=Theme.BORDER, linestyle='--', alpha=0.5, linewidth=0.8)
                
                if i == 0 and ax.lines:
                    ax.legend(loc='upper right', fontsize=8, ncol=2, 
                             facecolor=Theme.BG_SECONDARY, 
                             edgecolor=Theme.BORDER,
                             labelcolor=Theme.FG_PRIMARY)
            
            axes[4].set_xlabel('Время (часы:минуты)', color=Theme.FG_PRIMARY)
            
            plt.tight_layout()
            
            canvas = FigureCanvasTkAgg(fig, self.plot_frame)
            canvas.draw()
            
            self.interactive_zoom = InteractiveZoom(fig, axes)
            self.current_fig = fig
            self.current_canvas = canvas
            
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            # Добавляем информационную метку о сырых данных
            info_frame = tk.Frame(self.plot_frame, bg=Theme.BG_PRIMARY)
            info_frame.pack(fill=tk.X, padx=5, pady=2)
            
            tk.Label(
                info_frame,
                text="📊 На графике 4-й разности отображаются СЫРЫЕ данные (без фильтрации)",
                font=("Segoe UI", 9),
                fg=Theme.ACCENT_BLUE,
                bg=Theme.BG_PRIMARY,
            ).pack()
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            if self.plot_frame:
                tk.Label(
                    self.plot_frame,
                    text=f"Ошибка построения графика:\n{str(e)}",
                    font=("Arial", 11),
                    fg=Theme.ERROR,
                    bg=Theme.BG_PRIMARY,
                ).pack(expand=True)
    
    def calculate_4th_diff(self, data: np.ndarray) -> np.ndarray:
        """
        Вычисляет 4-ю разность для входного массива.
        
        4-я разность - это второй шаг после 2-й разности (дифференцирования),
        который эффективно выделяет высокочастотные колебания и резкие скачки.
        Формула: diff4 = np.diff(data, n=4, prepend=data[:4])
        
        ВОЗВРАЩАЕТ СЫРЫЕ ДАННЫЕ - БЕЗ ФИЛЬТРАЦИИ NaN И Inf.
        
        Args:
            data: Входной numpy массив (например, высота)
            
        Returns:
            Массив той же длины, что и входной, содержащий 4-ю разность.
            Для первых 4 элементов используется prepend для сохранения длины.
            Может содержать NaN и Inf - это сырые данные.
        """
        if data is None or len(data) < 5:
            return np.array([])
        
        try:
            # Вычисляем 4-ю разность. prepend используется для сохранения длины.
            fourth_diff = np.diff(data, n=4, prepend=data[:4])
            
            # НИКАКОЙ ОБРАБОТКИ - ВОЗВРАЩАЕМ КАК ЕСТЬ
            return fourth_diff
            
        except Exception as e:
            print(f"Ошибка расчета 4-й разности: {e}")
            return np.array([])
        
    def update_plot_visibility(self):
        """
        Обновляет видимость линий на графиках в соответствии с чекбоксами.
        
        Вызывается при изменении состояния любого чекбокса.
        """
        if not hasattr(self, 'plot_lines') or not self.plot_lines:
            self.update_plots()
            return
        
        selected_files = self.get_selected_files()
        
        for filename, lines in self.plot_lines.items():
            is_file_selected = filename in selected_files
            for line in lines.values():
                if line is not None:
                    line.set_visible(is_file_selected)
        
        if self.current_canvas:
            self.current_canvas.draw_idle()
    
    def reset_zoom(self):
        """Сбрасывает масштаб всех графиков к исходному."""
        if self.interactive_zoom:
            self.interactive_zoom.reset_all_zooms()