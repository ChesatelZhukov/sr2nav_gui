#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЧИСТОЕ ПРЕДСТАВЛЕНИЕ - Окно анализа GPS созвездия.
ИСПРАВЛЕНО: добавлен выбор папки как в трансформации
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import pyperclip

from view.themes import Theme
from view.widgets import ModernButton, InteractiveZoom


class GPSAnalysisWindow:
    """
    Окно отображения результатов анализа GPS созвездия.
    ТОЛЬКО UI, никаких вычислений!
    
    ИСПРАВЛЕНО: добавлен выбор папки как в трансформации
    """
    
    ALL_SATELLITES = [f'G{i:02d}' for i in range(1, 33)]
    
    # Цвета для категорий стабильности
    STABILITY_COLORS = {
        'excellent': '#198754',
        'good': '#0d6efd',
        'moderate': '#fd7e14',
        'unstable': '#dc3545',
        'bad': '#b02a37',
        'critical': '#8b0000',
        'invisible': '#6c757d',
    }
    
    # GPS эпоха
    GPS_EPOCH = datetime(1980, 1, 6)
    
    def __init__(self, parent, controller):
        self.parent = parent
        self.controller = controller
        self.current_dir = Path(controller.app_context.results_dir)
        
        self.analysis_results = None
        self.interactive_zoom = None
        self.current_filename = None
        self.current_fig = None
        self.current_canvas = None
        self.current_ax = None
        
        # Для контекстного меню
        self.context_menu = None
        self.last_click_coords = None
        self.last_click_time = None
        
        self.window = tk.Toplevel(parent)
        self.window.title("Анализ GPS созвездия - Оценка стабильности")
        self.window.geometry("1400x900")
        self.window.minsize(1200, 700)
        self.window.configure(bg=Theme.BG_PRIMARY)
        
        self.center_window()
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.create_widgets()
        self.setup_text_tags()
        self.show_folder_selection_prompt()
    
    def on_close(self):
        try:
            self.window.grab_release()
        except:
            pass
        self.window.destroy()

    def center_window(self):
        self.window.update_idletasks()
        width = self.window.winfo_width() or 1400
        height = self.window.winfo_height() or 900
        
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
        main_frame = tk.Frame(self.window, bg=Theme.BG_PRIMARY)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # ============ ВЕРХНЯЯ ПАНЕЛЬ ============
        self.create_header(main_frame)
        
        # ============ СЕКЦИЯ ВЫБОРА ПАПКИ ============
        folder_frame = tk.Frame(main_frame, bg=Theme.BG_PRIMARY)
        folder_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Подпись
        tk.Label(
            folder_frame,
            text="📂 Папка с SVs файлами:",
            font=("Segoe UI", 10, "bold"),
            bg=Theme.BG_PRIMARY,
            fg=Theme.FG_PRIMARY,
        ).pack(anchor="w")
        
        # Контейнер для поля ввода и кнопок
        dir_container = tk.Frame(folder_frame, bg=Theme.BG_PRIMARY)
        dir_container.pack(fill=tk.X, pady=(5, 0))
        
        # Поле отображения пути (только для чтения)
        self._dir_var = tk.StringVar(value=str(self.current_dir))
        
        self._dir_entry = tk.Entry(
            dir_container,
            textvariable=self._dir_var,
            font=("Consolas", 10),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY,
            relief=tk.SOLID,
            bd=1,
            state='readonly',
            readonlybackground=Theme.BG_SECONDARY,
        )
        self._dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # Кнопка выбора папки
        ModernButton(
            dir_container,
            text="📂 Выбрать папку...",
            command=self._on_browse_folder,
            width=15,
            font=("Segoe UI", 10),
            bg=Theme.ACCENT_BLUE,
            fg="white",
        ).pack(side=tk.RIGHT)
        
        # Кнопка сканирования
        ModernButton(
            dir_container,
            text="🔄 Сканировать",
            command=self._on_refresh_from_folder,
            width=12,
            font=("Segoe UI", 10),
            bg=Theme.ACCENT_GREEN,
            fg="white",
        ).pack(side=tk.RIGHT, padx=(0, 5))
        
        # Разделитель
        tk.Frame(main_frame, height=1, bg=Theme.BORDER).pack(fill=tk.X, pady=(0, 10))
        
        # ============ ПРОГРЕСС-БАР ============
        self.create_progress_bar(main_frame)
        
        # ============ ВКЛАДКИ ============
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        self.plot_frame = tk.Frame(self.notebook, bg=Theme.BG_PRIMARY)
        self.notebook.add(self.plot_frame, text="Интервалы видимости")
        
        self.stats_frame = tk.Frame(self.notebook, bg=Theme.BG_PRIMARY)
        self.notebook.add(self.stats_frame, text="Статистика и проблемы")
        
        self.report_frame = tk.Frame(self.notebook, bg=Theme.BG_PRIMARY)
        self.notebook.add(self.report_frame, text="Отчет о качестве")
        
        self.export_frame = tk.Frame(self.notebook, bg=Theme.BG_PRIMARY)
        self.notebook.add(self.export_frame, text="Экспорт")
        
        # ============ СТАТУСНАЯ СТРОКА ============
        self.create_status_bar(main_frame)
        
        self.setup_export_tab()
    
    def show_folder_selection_prompt(self):
        """Показывает предложение выбрать папку."""
        for frame in [self.plot_frame, self.stats_frame, self.report_frame, self.export_frame]:
            for widget in frame.winfo_children():
                widget.destroy()
            
            tk.Label(
                frame,
                text="👆 Выберите папку с SVs файлами в верхней панели",
                font=("Arial", 12),
                fg=Theme.FG_SECONDARY,
                bg=Theme.BG_PRIMARY,
            ).pack(expand=True)

    def _on_browse_folder(self):
        """Открывает диалог выбора папки с SVs файлами."""
        from view.main_window import UIPersistence
        
        # Запоминаем, что окно анализа сейчас активно
        self.window.focus_set()
        self.window.grab_set()
        
        initial_dir = UIPersistence.get_last_dir()
        if not initial_dir:
            initial_dir = str(self.current_dir)
        
        # Временно отпускаем захват для диалога
        self.window.grab_release()
        
        directory = filedialog.askdirectory(
            title="Выберите папку с SVs файлами",
            initialdir=initial_dir,
            parent=self.window  # Явно указываем родителя
        )
        
        # Возвращаем захват и фокус окну анализа
        if directory:
            self.current_dir = Path(directory)
            self._dir_var.set(str(self.current_dir))
            UIPersistence.set_last_dir(directory)
            
            # Загружаем данные
            self._load_data_from_folder()
        
        # Восстанавливаем фокус
        self.window.focus_set()
        self.window.grab_set()
        self.window.lift()  # Поднимаем окно наверх

    def _on_refresh_from_folder(self):
        """Обновляет данные из текущей папки."""
        self._load_data_from_folder()

    def _load_data_from_folder(self):
        """Загружает данные из выбранной папки."""
        self.show_loading(f"Сканирование {self.current_dir.name}...")
        
        # ИСПРАВЛЕНИЕ: Используем специальный метод для установки временной папки
        # или модифицируем контроллер для приема пути
        
        # Вариант 1: Если у контроллера есть метод set_temp_gps_folder
        if hasattr(self.controller, 'set_temp_gps_folder'):
            self.controller.set_temp_gps_folder(str(self.current_dir))
        
        # Вариант 2: Или просто передаем через атрибут (как уже сделано)
        import types
        self.controller._temp_gps_folder = str(self.current_dir)
        
        # Запрашиваем анализ
        self.controller.request_gps_analysis(self)
    
    def setup_text_tags(self):
        pass
    
    def _configure_text_tags(self, text_widget):
        text_widget.tag_config("quality_excellent", foreground="#198754", font=("Consolas", 10, "bold"))
        text_widget.tag_config("quality_good", foreground="#0d6efd", font=("Consolas", 10, "bold"))
        text_widget.tag_config("quality_moderate", foreground="#fd7e14", font=("Consolas", 10, "bold"))
        text_widget.tag_config("quality_poor", foreground="#dc3545", font=("Consolas", 10, "bold"))
        text_widget.tag_config("quality_critical", foreground="#8b0000", font=("Consolas", 10, "bold"))
        
        text_widget.tag_config("sat_excellent", foreground="#198754")
        text_widget.tag_config("sat_good", foreground="#0d6efd")
        text_widget.tag_config("sat_moderate", foreground="#fd7e14")
        text_widget.tag_config("sat_unstable", foreground="#dc3545")
        text_widget.tag_config("sat_bad", foreground="#b02a37")
        text_widget.tag_config("sat_critical", foreground="#8b0000", font=("Consolas", 10, "bold"))
        text_widget.tag_config("sat_invisible", foreground="#6c757d")
        
        text_widget.tag_config("warning_critical", foreground="#8b0000", font=("Consolas", 10, "bold"))
        text_widget.tag_config("warning_high", foreground="#dc3545", font=("Consolas", 10, "bold"))
        text_widget.tag_config("warning_medium", foreground="#fd7e14")
        text_widget.tag_config("warning_low", foreground="#6c757d")
        text_widget.tag_config("success", foreground="#198754")
        text_widget.tag_config("info", foreground="#0d6efd")
    
    def create_header(self, parent):
        header = tk.Frame(parent, bg=Theme.BG_PRIMARY)
        header.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(
            header,
            text="Анализ GPS созвездия - Оценка стабильности",
            font=("Arial", 14, "bold"),
            fg=Theme.FG_PRIMARY,
            bg=Theme.BG_PRIMARY,
        ).pack(side=tk.LEFT)
        
        control = tk.Frame(header, bg=Theme.BG_PRIMARY)
        control.pack(side=tk.RIGHT)
        
        self.file_var = tk.StringVar()
        self.file_dropdown = ttk.Combobox(
            control,
            textvariable=self.file_var,
            state='readonly',
            width=40
        )
        self.file_dropdown.pack(side=tk.LEFT, padx=(0, 10))
        self.file_dropdown.bind('<<ComboboxSelected>>', self.on_file_selected)
        
        ModernButton(
            control,
            text="⟲ Сбросить зум",
            command=self.reset_zoom,
            width=12,
            bg=Theme.ACCENT_ORANGE,
            fg="white",
        ).pack(side=tk.LEFT, padx=2)
        
        ModernButton(
            control,
            text="💾 Сохранить график",
            command=self.save_plot,
            width=14,
            bg=Theme.ACCENT_BLUE,
            fg="white",
        ).pack(side=tk.LEFT, padx=2)
    
    def create_progress_bar(self, parent):
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
        
        self.progress_frame.pack_forget()
    
    def create_status_bar(self, parent):
        status = tk.Frame(parent, bg=Theme.BG_SECONDARY, height=24)
        status.pack(fill=tk.X, pady=(10, 0))
        status.pack_propagate(False)
        
        self.status_label = tk.Label(
            status,
            text="Готов",
            font=("Arial", 9),
            fg=Theme.FG_SECONDARY,
            bg=Theme.BG_SECONDARY,
        )
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        self.quality_label = tk.Label(
            status,
            text="",
            font=("Arial", 9, "bold"),
            bg=Theme.BG_SECONDARY,
        )
        self.quality_label.pack(side=tk.LEFT, padx=20)
        
        self.file_info_label = tk.Label(
            status,
            text="Файлов: 0",
            font=("Arial", 9),
            fg=Theme.FG_SECONDARY,
            bg=Theme.BG_SECONDARY,
        )
        self.file_info_label.pack(side=tk.RIGHT, padx=10)
    
    def setup_export_tab(self):
        container = tk.Frame(self.export_frame, bg=Theme.BG_PRIMARY, padx=20, pady=20)
        container.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(
            container,
            text="Экспорт результатов анализа GPS созвездия",
            font=("Arial", 12, "bold"),
            fg=Theme.FG_PRIMARY,
            bg=Theme.BG_PRIMARY,
        ).pack(anchor="w", pady=(0, 20))
        
        info_text = """Экспорт сохраняет сводную статистику в CSV файл.

МЕТРИКИ СТАБИЛЬНОСТИ (основные):
• Интервалы/минуту — частота пропаданий сигнала
• Категория: Эталонный, Отличный, Хороший, Умеренный, Нестабильный, Плохой, Критический
• Рекомендация: использовать / снизить вес / исключить

8 интервалов за 10 часов = 0.013 инт/мин → ЭТАЛОН
8 интервалов за 1 час = 0.133 инт/мин → УМЕРЕННЫЙ
8 интервалов за 10 минут = 0.8 инт/мин → ПЛОХОЙ"""
        
        tk.Label(
            container,
            text=info_text,
            font=("Arial", 10),
            fg=Theme.FG_SECONDARY,
            bg=Theme.BG_PRIMARY,
            justify=tk.LEFT,
            wraplength=600
        ).pack(anchor="w", pady=(0, 30))
        
        ModernButton(
            container,
            text="📊 Экспортировать в CSV",
            command=self.on_export,
            width=20,
            height=2,
            font=("Arial", 11, "bold"),
            bg=Theme.ACCENT_GREEN,
            fg="white",
        ).pack(pady=(0, 20))
        
        self.export_status = tk.Label(
            container,
            text="",
            font=("Arial", 9),
            fg=Theme.FG_SECONDARY,
            bg=Theme.BG_PRIMARY,
        )
        self.export_status.pack()
    
    def show_loading(self, message: str):
        self.progress_label.config(text=message)
        self.progress_frame.pack(fill=tk.X, pady=(0, 10))
        self.progress_bar.start(10)
        self.window.update()
    
    def hide_loading(self):
        self.progress_bar.stop()
        self.progress_frame.pack_forget()
    
    def update_results(self, results: Dict):
        """Обновляет все данные в окне."""
        self.analysis_results = results
        self.hide_loading()
        
        self.update_file_dropdown()
        self.update_stats_tab()
        self.update_report_tab()
        
        file_count = len(results)
        self.file_info_label.config(text=f"Файлов: {file_count}")
        
        if file_count > 0:
            first_file = list(results.keys())[0]
            self.file_var.set(first_file)
            self.current_filename = first_file
            self.update_plot_tab()
            
            quality = results[first_file].get('overall_quality', {})
            self.status_label.config(
                text=f"Анализ завершен. Проанализировано файлов: {file_count}",
                fg=Theme.FG_PRIMARY
            )
            self.update_quality_display(quality)
        else:
            self.status_label.config(
                text="Файлы .SVs не найдены",
                fg=Theme.WARNING
            )
            self.quality_label.config(text="")
    
    def update_quality_display(self, quality: Dict):
        if quality:
            score = quality.get('score', 0)
            category = quality.get('category', 'Н/Д')
            color = quality.get('color', Theme.FG_SECONDARY)
            
            self.quality_label.config(
                text=f"Качество: {category} ({score})",
                fg=color
            )
    
    def show_error(self, error: str):
        """Показывает ошибку."""
        self.hide_loading()
        self.status_label.config(text=f"Ошибка: {error}", fg=Theme.ERROR)
        self.quality_label.config(text="")
        
        for frame in [self.plot_frame, self.stats_frame, self.report_frame]:
            for widget in frame.winfo_children():
                widget.destroy()
            
            tk.Label(
                frame,
                text=f"❌ Ошибка загрузки данных:\n{error}",
                font=("Arial", 11),
                fg=Theme.ERROR,
                bg=Theme.BG_PRIMARY,
            ).pack(expand=True)
    
    def update_file_dropdown(self):
        if self.analysis_results:
            filenames = list(self.analysis_results.keys())
            self.file_dropdown['values'] = filenames
    
    def on_file_selected(self, event=None):
        filename = self.file_var.get()
        if filename and filename in self.analysis_results:
            self.current_filename = filename
            self.update_plot_tab()
            quality = self.analysis_results[filename].get('overall_quality', {})
            self.update_quality_display(quality)
    
    def update_plot_tab(self):
        """Обновляет вкладку с графиком."""
        for widget in self.plot_frame.winfo_children():
            widget.destroy()
        
        if not self.current_filename or not self.analysis_results:
            tk.Label(
                self.plot_frame,
                text="Выберите файл для отображения",
                font=("Arial", 11),
                fg=Theme.FG_SECONDARY,
                bg=Theme.BG_PRIMARY,
            ).pack(expand=True)
            return
        
        result = self.analysis_results[self.current_filename]
        satellite_stats = result.get('satellite_stats', {})
        
        try:
            fig, ax = plt.subplots(figsize=(16, 14))
            fig.patch.set_facecolor('white')
            self.current_ax = ax
            
            time_range = result.get('data', {}).get('time_range', (0, 1))
            total_duration = result.get('data', {}).get('total_duration', 1)
            
            duration_min = total_duration / 60
            duration_hours = total_duration / 3600
            
            # Счетчики для статистики
            excellent_count = 0
            good_count = 0
            moderate_count = 0
            unstable_count = 0
            bad_count = 0
            critical_count = 0
            
            for i, sat in enumerate(self.ALL_SATELLITES):
                y_pos = len(self.ALL_SATELLITES) - i - 1
                
                color = '#CCCCCC'
                alpha = 0.05
                is_visible = False
                ipm = 999.0
                num_intervals = 0
                visibility_percent = 0
                intervals = []
                
                if sat in satellite_stats:
                    stats = satellite_stats[sat]
                    
                    if hasattr(stats, 'get'):
                        is_visible = stats.get('is_visible', False)
                        ipm = stats.get('intervals_per_minute', 999)
                        num_intervals = stats.get('num_intervals', 0)
                        visibility_percent = stats.get('visibility_percent', 0)
                        intervals = stats.get('intervals', [])
                    else:
                        is_visible = stats.is_visible
                        ipm = stats.intervals_per_minute
                        num_intervals = stats.num_intervals
                        visibility_percent = stats.visibility_percent
                        intervals = stats.intervals if hasattr(stats, 'intervals') else []
                    
                    if is_visible:
                        if ipm <= 0.01:
                            color = self.STABILITY_COLORS['excellent']
                            alpha = 0.8
                            excellent_count += 1
                        elif ipm <= 0.05:
                            color = self.STABILITY_COLORS['excellent']
                            alpha = 0.7
                            excellent_count += 1
                        elif ipm <= 0.1:
                            color = self.STABILITY_COLORS['good']
                            alpha = 0.7
                            good_count += 1
                        elif ipm <= 0.2:
                            color = self.STABILITY_COLORS['moderate']
                            alpha = 0.7
                            moderate_count += 1
                        elif ipm <= 0.5:
                            color = self.STABILITY_COLORS['unstable']
                            alpha = 0.7
                            unstable_count += 1
                        elif ipm <= 1.0:
                            color = self.STABILITY_COLORS['bad']
                            alpha = 0.7
                            bad_count += 1
                        else:
                            color = self.STABILITY_COLORS['critical']
                            alpha = 0.7
                            critical_count += 1
                        
                        alpha = 0.3 + 0.5 * (visibility_percent / 100)
                        
                        if intervals:
                            for interval in intervals:
                                if hasattr(interval, 'get'):
                                    start = interval.get('start', 0)
                                    end = interval.get('end', 0)
                                else:
                                    start = interval.start if hasattr(interval, 'start') else 0
                                    end = interval.end if hasattr(interval, 'end') else 0
                                
                                ax.barh(
                                    y=y_pos,
                                    width=end - start,
                                    left=start,
                                    height=0.7,
                                    color=color,
                                    edgecolor=color,
                                    alpha=alpha,
                                    linewidth=0.5
                                )
                        
                        if ipm > 0.2:
                            ax.plot(
                                time_range[0] + 10, y_pos,
                                marker='v',
                                color='red',
                                markersize=8,
                                markeredgecolor='darkred',
                                markeredgewidth=1
                            )
                    else:
                        ax.barh(
                            y=y_pos,
                            width=0,
                            height=0.7,
                            color='#CCCCCC',
                            alpha=0.1
                        )
            
            ax.set_yticks(np.arange(len(self.ALL_SATELLITES)))
            ax.set_yticklabels(self.ALL_SATELLITES[::-1], fontsize=9)
            ax.set_xlim(time_range[0], time_range[1])
            
            ax.set_xlabel('Время наблюдения (секунды)', fontsize=12)
            ax.set_ylabel('Спутники GPS', fontsize=12)
            
            quality = result.get('overall_quality', {})
            
            if duration_hours >= 1:
                duration_text = f"{duration_hours:.1f} ч"
            else:
                duration_text = f"{duration_min:.0f} мин"
            
            title = f"Стабильность GPS спутников\n{self.current_filename}  |  Длительность: {duration_text}"
            if quality:
                title += f"  |  Качество: {quality.get('category', 'Н/Д')} ({quality.get('score', 0)})"
            
            ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
            ax.grid(True, alpha=0.3, axis='x', linestyle='--', linewidth=0.5)
            
            info_text = (
                f"Видимых: {result.get('visible_satellites', 0)} | "
                f"Длительность: {duration_text}\n"
                f"🟢 Отл/Эт: {excellent_count} | "
                f"🔵 Хор: {good_count} | "
                f"🟠 Умер: {moderate_count}\n"
                f"🔴 Нест: {unstable_count} | "
                f"🟤 Плох: {bad_count} | "
                f"⚫ Крит: {critical_count}"
            )
            
            ax.text(
                0.02, 0.98, info_text,
                transform=ax.transAxes,
                fontsize=10,
                verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.9, edgecolor='gray')
            )
            
            from matplotlib.patches import Patch
            from matplotlib.lines import Line2D
            
            legend_elements = [
                Patch(facecolor=self.STABILITY_COLORS['excellent'], alpha=0.7, 
                    label='Эталон/Отлично (<0.05/мин или 1 интервал)'),
                Patch(facecolor=self.STABILITY_COLORS['good'], alpha=0.7, 
                    label='Хорошо (0.05-0.1/мин)'),
                Patch(facecolor=self.STABILITY_COLORS['moderate'], alpha=0.7, 
                    label='Умеренно (0.1-0.2/мин)'),
                Patch(facecolor=self.STABILITY_COLORS['unstable'], alpha=0.7, 
                    label='Нестабильно (0.2-0.5/мин)'),
                Patch(facecolor=self.STABILITY_COLORS['bad'], alpha=0.7, 
                    label='Плохо (0.5-1.0/мин)'),
                Patch(facecolor=self.STABILITY_COLORS['critical'], alpha=0.7, 
                    label='Критично (>1.0/мин)'),
                Patch(facecolor='#CCCCCC', alpha=0.2, 
                    label='Не виден / нет данных'),
                Line2D([0], [0], marker='v', color='w', markerfacecolor='red',
                    markersize=8, label='Проблемный (>0.2/мин)',
                    markeredgecolor='darkred')
            ]
            
            ax.legend(handles=legend_elements, loc='lower left', fontsize=8, ncol=2)
            
            plt.tight_layout()
            
            canvas = FigureCanvasTkAgg(fig, self.plot_frame)
            canvas.draw()
            
            canvas.mpl_connect('button_press_event', self.on_canvas_click)
            
            self.interactive_zoom = InteractiveZoom(fig, [ax])
            self.current_fig = fig
            self.current_canvas = canvas
            
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            tk.Label(
                self.plot_frame,
                text=f"Ошибка построения графика:\n{str(e)}",
                font=("Arial", 11),
                fg=Theme.ERROR,
                bg=Theme.BG_PRIMARY,
            ).pack(expand=True)
    
    def on_canvas_click(self, event):
        """Обработчик кликов на canvas."""
        if event.button == 3:
            self.show_context_menu(event)
        elif event.button == 1 and event.dblclick:
            if self.interactive_zoom:
                self.interactive_zoom.reset_all_zooms()
    
    def create_context_menu(self):
        """Создает контекстное меню для графика."""
        self.context_menu = tk.Menu(self.window, tearoff=0, bg=Theme.BG_SECONDARY, fg=Theme.FG_PRIMARY)
        self.context_menu.add_command(label="📋 Копировать время", command=self.copy_time_to_clipboard)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="📋 Копировать время и спутник", command=self.copy_time_and_satellite)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="🔍 Показать спутник", command=self.show_satellite_info)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="⟲ Сбросить зум", command=self.reset_zoom)
    
    def show_context_menu(self, event):
        """Показывает контекстное меню при правом клике."""
        if not self.current_ax or not self.current_fig:
            return
        
        if event.inaxes != self.current_ax:
            return
        
        self.last_click_coords = (event.xdata, event.ydata)
        self.last_click_time = event.xdata
        
        if not self.context_menu:
            self.create_context_menu()
        
        try:
            self.context_menu.tk_popup(event.guiEvent.x_root, event.guiEvent.y_root)
        finally:
            self.context_menu.grab_release()
    
    def gps_seconds_to_datetime(self, gps_seconds: float) -> datetime:
        """Преобразует GPS секунды в datetime."""
        now = datetime.now()
        days_since_epoch = (now - self.GPS_EPOCH).days
        current_gps_week = days_since_epoch // 7
        week_start = self.GPS_EPOCH + timedelta(weeks=current_gps_week)
        return week_start + timedelta(seconds=gps_seconds)
    
    def format_gps_time(self, gps_seconds: float) -> str:
        """Форматирует GPS время."""
        dt = self.gps_seconds_to_datetime(gps_seconds)
        return dt.strftime("%Y:%m:%d:%H:%M:%S") + f".{int((gps_seconds % 1) * 10)}"
    
    def get_satellite_at_position(self, x: float, y: float) -> Tuple[Optional[str], Optional[Dict]]:
        """Определяет спутник по координатам клика."""
        if not self.current_filename or not self.analysis_results:
            return None, None
        
        result = self.analysis_results[self.current_filename]
        satellite_stats = result.get('satellite_stats', {})
        
        sat_index = int(round(32 - y))
        if 1 <= sat_index <= 32:
            prn = f"G{sat_index:02d}"
            if prn in satellite_stats:
                return prn, satellite_stats[prn]
        
        return None, None
    
    def copy_time_to_clipboard(self):
        """Копирует время в буфер обмена."""
        if self.last_click_time is None:
            return
        
        time_str = self.format_gps_time(self.last_click_time)
        
        try:
            pyperclip.copy(time_str)
            self.show_status_message(f"✓ Время скопировано: {time_str}", Theme.SUCCESS)
        except Exception as e:
            self.show_status_message(f"✗ Ошибка копирования: {e}", Theme.ERROR)
    
    def copy_time_and_satellite(self):
        """Копирует время и информацию о спутнике."""
        if self.last_click_time is None or self.last_click_coords is None:
            return
        
        time_str = self.format_gps_time(self.last_click_time)
        prn, stats = self.get_satellite_at_position(*self.last_click_coords)
        
        if prn:
            if stats and stats.get('is_visible', False):
                ipm = stats.get('intervals_per_minute', 0)
                visibility = stats.get('visibility_percent', 0)
                result = f"{time_str}\t{prn}\t{ipm:.3f}/мин\t{visibility:.1f}%"
            else:
                result = f"{time_str}\t{prn}\tне виден"
        else:
            result = time_str
        
        try:
            pyperclip.copy(result)
            self.show_status_message(f"✓ Данные скопированы", Theme.SUCCESS)
        except Exception as e:
            self.show_status_message(f"✗ Ошибка копирования: {e}", Theme.ERROR)
    
    def show_satellite_info(self):
        """Показывает информацию о спутнике во всплывающем окне."""
        if self.last_click_coords is None:
            return
        
        prn, stats = self.get_satellite_at_position(*self.last_click_coords)
        if not prn:
            self.show_status_message("✗ Спутник не найден", Theme.WARNING)
            return
        
        info_window = tk.Toplevel(self.window)
        info_window.title(f"Информация о спутнике {prn}")
        info_window.geometry("400x300")
        info_window.configure(bg=Theme.BG_PRIMARY)
        info_window.transient(self.window)
        info_window.grab_set()
        
        info_window.update_idletasks()
        x = self.window.winfo_rootx() + (self.window.winfo_width() - 400) // 2
        y = self.window.winfo_rooty() + (self.window.winfo_height() - 300) // 2
        info_window.geometry(f"+{x}+{y}")
        
        main = tk.Frame(info_window, bg=Theme.BG_PRIMARY, padx=20, pady=20)
        main.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(
            main,
            text=f"🛰️ Спутник {prn}",
            font=("Arial", 14, "bold"),
            bg=Theme.BG_PRIMARY,
            fg=Theme.FG_PRIMARY,
        ).pack(pady=(0, 15))
        
        if stats and stats.get('is_visible', False):
            ipm = stats.get('intervals_per_minute', 0)
            num_intervals = stats.get('num_intervals', 0)
            total_time = stats.get('total_visible_time', 0)
            visibility = stats.get('visibility_percent', 0)
            avg_duration = stats.get('avg_duration', 0)
            
            if ipm <= 0.01:
                category = "Эталонный"
                color = self.STABILITY_COLORS['excellent']
            elif ipm <= 0.05:
                category = "Отличный"
                color = self.STABILITY_COLORS['excellent']
            elif ipm <= 0.1:
                category = "Хороший"
                color = self.STABILITY_COLORS['good']
            elif ipm <= 0.2:
                category = "Умеренный"
                color = self.STABILITY_COLORS['moderate']
            elif ipm <= 0.5:
                category = "Нестабильный"
                color = self.STABILITY_COLORS['unstable']
            elif ipm <= 1.0:
                category = "Плохой"
                color = self.STABILITY_COLORS['bad']
            else:
                category = "Критический"
                color = self.STABILITY_COLORS['critical']
            
            stats_frame = tk.Frame(main, bg=Theme.BG_PRIMARY)
            stats_frame.pack(fill=tk.BOTH, expand=True)
            
            metrics = [
                ("Категория:", category, color),
                ("Частота пропаданий:", f"{ipm:.3f} инт/мин", color),
                ("Количество интервалов:", str(num_intervals), Theme.FG_PRIMARY),
                ("Общее время видимости:", f"{total_time:.0f} с ({visibility:.1f}%)", Theme.FG_PRIMARY),
                ("Средняя длительность:", f"{avg_duration:.1f} с", Theme.FG_PRIMARY),
            ]
            
            for i, (label, value, fg_color) in enumerate(metrics):
                row = tk.Frame(stats_frame, bg=Theme.BG_PRIMARY)
                row.pack(fill=tk.X, pady=2)
                
                tk.Label(
                    row,
                    text=label,
                    font=("Arial", 10, "bold"),
                    bg=Theme.BG_PRIMARY,
                    fg=Theme.FG_SECONDARY,
                    width=20,
                    anchor="w",
                ).pack(side=tk.LEFT)
                
                tk.Label(
                    row,
                    text=value,
                    font=("Arial", 10),
                    bg=Theme.BG_PRIMARY,
                    fg=fg_color,
                    anchor="w",
                ).pack(side=tk.LEFT, padx=(5, 0))
        else:
            tk.Label(
                main,
                text="Спутник не виден в данном файле",
                font=("Arial", 11),
                bg=Theme.BG_PRIMARY,
                fg=Theme.FG_SECONDARY,
            ).pack(expand=True)
        
        ModernButton(
            main,
            text="Закрыть",
            command=info_window.destroy,
            width=15,
            font=("Arial", 10),
        ).pack(pady=(20, 0))
    
    def show_status_message(self, message: str, color: str = None):
        """Показывает временное сообщение в статусной строке."""
        if hasattr(self, 'status_label'):
            original_text = self.status_label.cget('text')
            original_fg = self.status_label.cget('fg')
            
            self.status_label.config(text=message, fg=color if color else Theme.SUCCESS)
            self.window.after(3000, lambda: self.status_label.config(text=original_text, fg=original_fg))
    
    def update_stats_tab(self):
        """Обновляет вкладку со статистикой."""
        for widget in self.stats_frame.winfo_children():
            widget.destroy()
        
        if not self.analysis_results:
            tk.Label(
                self.stats_frame,
                text="Нет данных для отображения",
                font=("Arial", 11),
                fg=Theme.FG_SECONDARY,
                bg=Theme.BG_PRIMARY,
            ).pack(expand=True)
            return
        
        container = tk.Frame(self.stats_frame, bg=Theme.BG_PRIMARY)
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
        
        for filename, result in self.analysis_results.items():
            file_card = tk.Frame(scrollable, bg=Theme.BG_SECONDARY, relief=tk.SOLID, bd=1)
            file_card.pack(fill=tk.X, padx=10, pady=5)
            
            header = tk.Frame(file_card, bg=Theme.BG_SECONDARY)
            header.pack(fill=tk.X, padx=10, pady=8)
            
            quality = result.get('overall_quality', {})
            quality_color = quality.get('color', Theme.FG_PRIMARY)
            
            tk.Label(
                header,
                text=f"📁 {filename}",
                font=("Consolas", 11, "bold"),
                bg=Theme.BG_SECONDARY,
                fg=Theme.FG_PRIMARY,
            ).pack(side=tk.LEFT)
            
            tk.Label(
                header,
                text=f"Качество: {quality.get('category', 'Н/Д')} ({quality.get('score', 0)})",
                font=("Arial", 10, "bold"),
                bg=Theme.BG_SECONDARY,
                fg=quality_color,
            ).pack(side=tk.RIGHT)
            
            stats_frame = tk.Frame(file_card, bg=Theme.BG_SECONDARY)
            stats_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
            
            col1 = tk.Frame(stats_frame, bg=Theme.BG_SECONDARY)
            col1.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 20))
            
            col2 = tk.Frame(stats_frame, bg=Theme.BG_SECONDARY)
            col2.pack(side=tk.LEFT, fill=tk.Y)
            
            data = result.get('data', {})
            tk.Label(
                col1,
                text=f"Длительность: {data.get('total_duration', 0)/3600:.2f} ч",
                font=("Arial", 10),
                bg=Theme.BG_SECONDARY,
                fg=Theme.FG_PRIMARY,
                anchor="w",
            ).pack(anchor="w")
            
            tk.Label(
                col1,
                text=f"Видимых спутников: {result.get('visible_satellites', 0)}/32",
                font=("Arial", 10),
                bg=Theme.BG_SECONDARY,
                fg=Theme.FG_PRIMARY,
                anchor="w",
            ).pack(anchor="w")
            
            tk.Label(
                col2,
                text=f"Среднее кол-во: {result.get('mean_satellites', 0):.1f}",
                font=("Arial", 10),
                bg=Theme.BG_SECONDARY,
                fg=Theme.FG_PRIMARY,
                anchor="w",
            ).pack(anchor="w")
            
            tk.Label(
                col2,
                text=f"Строк (выборка): {data.get('rows_sampled', 0):,}",
                font=("Arial", 10),
                bg=Theme.BG_SECONDARY,
                fg=Theme.FG_PRIMARY,
                anchor="w",
            ).pack(anchor="w")
            
            problem_sats = []
            for sat, stats in result.get('satellite_stats', {}).items():
                if stats.get('is_visible', False):
                    ipm = stats.get('intervals_per_minute', 0)
                    if ipm > 0.2:
                        problem_sats.append((sat, stats, ipm))
            
            if problem_sats:
                tk.Frame(file_card, height=1, bg='#dc3545').pack(fill=tk.X, padx=10, pady=5)
                
                problems_frame = tk.Frame(file_card, bg=Theme.BG_SECONDARY)
                problems_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
                
                tk.Label(
                    problems_frame,
                    text=f"⚠️ ПРОБЛЕМНЫЕ СПУТНИКИ (>0.2/мин) — {len(problem_sats)}",
                    font=("Arial", 10, "bold"),
                    bg=Theme.BG_SECONDARY,
                    fg='#dc3545',
                ).pack(anchor="w", pady=(0, 5))
                
                for sat, stats, ipm in sorted(problem_sats, key=lambda x: x[2], reverse=True)[:10]:
                    num_int = stats.get('num_intervals', 0)
                    avg_dur = stats.get('avg_duration', 0)
                    visibility = stats.get('visibility_percent', 0)
                    
                    if ipm > 1.0:
                        category = "КРИТИЧНО"
                        color = "#8b0000"
                    elif ipm > 0.5:
                        category = "ПЛОХО"
                        color = "#dc3545"
                    elif ipm > 0.2:
                        category = "НЕСТАБИЛЬНО"
                        color = "#fd7e14"
                    else:
                        category = "НОРМА"
                        color = "#6c757d"
                    
                    row = tk.Frame(problems_frame, bg=Theme.BG_SECONDARY)
                    row.pack(fill=tk.X, pady=1)
                    
                    tk.Label(
                        row,
                        text=f"  {sat}",
                        font=("Consolas", 10, "bold"),
                        bg=Theme.BG_SECONDARY,
                        fg=color,
                        width=6,
                        anchor="w",
                    ).pack(side=tk.LEFT)
                    
                    tk.Label(
                        row,
                        text=f"{ipm:6.2f}/мин | инт: {num_int:3d} | ср: {avg_dur:5.1f}с | видим: {visibility:5.1f}% | {category}",
                        font=("Consolas", 9),
                        bg=Theme.BG_SECONDARY,
                        fg=color,
                        anchor="w",
                    ).pack(side=tk.LEFT)
            
            excellent_sats = []
            for sat, stats in result.get('satellite_stats', {}).items():
                if stats.get('is_visible', False):
                    ipm = stats.get('intervals_per_minute', 999)
                    if ipm <= 0.05:
                        excellent_sats.append((sat, stats, ipm))
            
            if excellent_sats:
                good_frame = tk.Frame(file_card, bg=Theme.BG_SECONDARY)
                good_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
                
                tk.Label(
                    good_frame,
                    text=f"✅ ЭТАЛОННЫЕ СПУТНИКИ (<0.05/мин) — {len(excellent_sats)}",
                    font=("Arial", 10, "bold"),
                    bg=Theme.BG_SECONDARY,
                    fg='#198754',
                ).pack(anchor="w", pady=(0, 5))
                
                for sat, stats, ipm in excellent_sats[:5]:
                    visibility = stats.get('visibility_percent', 0)
                    tk.Label(
                        good_frame,
                        text=f"  {sat}: {ipm:.3f}/мин, видимость {visibility:.1f}%",
                        font=("Consolas", 9),
                        bg=Theme.BG_SECONDARY,
                        fg='#198754',
                        anchor="w",
                    ).pack(anchor="w")
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def update_report_tab(self):
        """Обновляет вкладку с детальным отчетом."""
        for widget in self.report_frame.winfo_children():
            widget.destroy()
        
        if not self.analysis_results:
            tk.Label(
                self.report_frame,
                text="Нет данных для отображения",
                font=("Arial", 11),
                fg=Theme.FG_SECONDARY,
                bg=Theme.BG_PRIMARY,
            ).pack(expand=True)
            return
        
        text_frame = tk.Frame(self.report_frame, bg=Theme.BG_PRIMARY)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        text_widget = tk.Text(
            text_frame,
            font=("Consolas", 10),
            wrap=tk.WORD,
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY,
            relief=tk.FLAT,
            padx=15,
            pady=15,
        )
        
        scrollbar = tk.Scrollbar(text_frame, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self._configure_text_tags(text_widget)
        
        text_widget.insert(tk.END, "="*80 + "\n")
        text_widget.insert(tk.END, "ОТЧЕТ О КАЧЕСТВЕ GPS ДАННЫХ\n")
        text_widget.insert(tk.END, "="*80 + "\n\n")
        
        text_widget.insert(tk.END, f"Дата анализа: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n")
        text_widget.insert(tk.END, f"Папка с данными: {self.current_dir}\n")
        text_widget.insert(tk.END, f"Всего файлов: {len(self.analysis_results)}\n\n")
        
        text_widget.insert(tk.END, "📊 ШКАЛА ОЦЕНКИ СТАБИЛЬНОСТИ:\n")
        text_widget.insert(tk.END, "  • <0.05/мин — Эталон/Отлично (1 пропадание >20 мин)\n", "sat_excellent")
        text_widget.insert(tk.END, "  • 0.05-0.1/мин — Хорошо (1 пропадание 10-20 мин)\n", "sat_good")
        text_widget.insert(tk.END, "  • 0.1-0.2/мин — Умеренно (1 пропадание 5-10 мин)\n", "sat_moderate")
        text_widget.insert(tk.END, "  • 0.2-0.5/мин — Нестабильно (1 пропадание 2-5 мин)\n", "sat_unstable")
        text_widget.insert(tk.END, "  • 0.5-1.0/мин — Плохо (1 пропадание 1-2 мин)\n", "sat_bad")
        text_widget.insert(tk.END, "  • >1.0/мин — Критически (>1 пропадания в минуту)\n\n", "sat_critical")
        
        sorted_files = sorted(
            self.analysis_results.items(),
            key=lambda x: x[1].get('overall_quality', {}).get('score', 0)
        )
        
        for filename, result in sorted_files:
            quality = result.get('overall_quality', {})
            summary = result.get('summary', {})
            
            text_widget.insert(tk.END, f"\n{'─'*80}\n")
            text_widget.insert(tk.END, f"ФАЙЛ: {filename}\n", f"quality_{quality.get('category', 'poor').lower()}")
            text_widget.insert(tk.END, f"{'─'*80}\n")
            
            score = quality.get('score', 0)
            category = quality.get('category', 'Н/Д')
            color_tag = f"quality_{quality.get('category', 'poor').lower()}"
            
            text_widget.insert(tk.END, f"\n📊 ОЦЕНКА КАЧЕСТВА: ")
            text_widget.insert(tk.END, f"{category} ({score})\n", color_tag)
            
            if quality.get('needs_attention', False):
                text_widget.insert(tk.END, "⚠️ ТРЕБУЕТ ВНИМАНИЯ: высокий процент проблемных спутников\n", "warning_high")
            
            text_widget.insert(tk.END, f"\n📈 Основные метрики:\n")
            text_widget.insert(tk.END, f"  • Длительность: {summary.get('duration_hours', 0):.2f} ч\n")
            text_widget.insert(tk.END, f"  • Видимых спутников: {summary.get('total_visible', 0)} из 32\n")
            text_widget.insert(tk.END, f"  • Среднее количество: {summary.get('mean_satellites', 0):.1f}\n")
            
            problem_by_freq = []
            for sat, stats in result.get('satellite_stats', {}).items():
                if stats.get('is_visible', False):
                    ipm = stats.get('intervals_per_minute', 0)
                    if ipm > 0.2:
                        problem_by_freq.append((sat, stats, ipm))
            
            if problem_by_freq:
                text_widget.insert(tk.END, f"\n⚠️ ПРОБЛЕМНЫЕ ПО ЧАСТОТЕ (>0.2/мин):\n")
                text_widget.insert(tk.END, f"  • Всего: {len(problem_by_freq)}\n")
                
                critical_freq = sum(1 for _, _, ipm in problem_by_freq if ipm > 1.0)
                if critical_freq > 0:
                    text_widget.insert(tk.END, f"  • Критических (>1/мин): {critical_freq}\n", "warning_critical")
                
                for sat, stats, ipm in sorted(problem_by_freq, key=lambda x: x[2], reverse=True)[:5]:
                    num_int = stats.get('num_intervals', 0)
                    avg_dur = stats.get('avg_duration', 0)
                    
                    if ipm > 1.0:
                        tag = "sat_critical"
                    elif ipm > 0.5:
                        tag = "sat_bad"
                    else:
                        tag = "sat_unstable"
                    
                    text_widget.insert(
                        tk.END,
                        f"     {sat}: {ipm:.3f}/мин ({num_int} инт, ср.{avg_dur:.0f}с)\n",
                        tag
                    )
            
            excellent_freq = []
            for sat, stats in result.get('satellite_stats', {}).items():
                if stats.get('is_visible', False):
                    ipm = stats.get('intervals_per_minute', 999)
                    if ipm <= 0.05:
                        excellent_freq.append((sat, stats, ipm))
            
            if excellent_freq:
                text_widget.insert(tk.END, f"\n✅ ЭТАЛОННЫЕ СПУТНИКИ (<0.05/мин):\n")
                for sat, stats, ipm in excellent_freq[:5]:
                    text_widget.insert(
                        tk.END,
                        f"     {sat}: {ipm:.3f}/мин, видимость {stats.get('visibility_percent', 0):.1f}%\n",
                        "sat_excellent"
                    )
        
        text_widget.insert(tk.END, f"\n{'='*80}\n")
        text_widget.insert(tk.END, "КОНЕЦ ОТЧЕТА\n")
        text_widget.insert(tk.END, f"{'='*80}\n")
        
        text_widget.config(state=tk.DISABLED)
    
    def on_refresh(self):
        self.show_loading("Обновление данных...")
        self._load_data_from_folder()
    
    def on_export(self):
        if not self.analysis_results:
            messagebox.showwarning(
                "Внимание",
                "Нет данных для экспорта",
                parent=self.window
            )
            return
        
        from view.main_window import UIPersistence
        initial_dir = UIPersistence.get_last_dir()
        if not initial_dir:
            initial_dir = str(self.current_dir)
        
        filename = filedialog.asksaveasfilename(
            title="Экспортировать результаты анализа",
            defaultextension=".csv",
            filetypes=[("CSV файлы", "*.csv"), ("Все файлы", "*.*")],
            initialdir=initial_dir,
            initialfile=f"gps_stability_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        
        if filename:
            UIPersistence.set_last_dir(filename)
            self.export_status.config(text="Экспорт...", fg=Theme.FG_SECONDARY)
            self.window.update()
            
            success = self.controller.export_gps_analysis(filename)
            
            if success:
                self.export_status.config(
                    text=f"✓ Результаты сохранены",
                    fg=Theme.SUCCESS
                )
                messagebox.showinfo(
                    "Успех",
                    f"Результаты сохранены",
                    parent=self.window
                )
            else:
                self.export_status.config(
                    text="✗ Ошибка при экспорте",
                    fg=Theme.ERROR
                )
    
    def reset_zoom(self):
        if self.interactive_zoom:
            self.interactive_zoom.reset_all_zooms()
    
    def save_plot(self):
        if not self.current_fig:
            messagebox.showwarning(
                "Внимание",
                "Нет активного графика",
                parent=self.window
            )
            return
        
        from view.main_window import UIPersistence
        initial_dir = UIPersistence.get_last_dir()
        if not initial_dir:
            initial_dir = str(self.current_dir)
        
        filename = filedialog.asksaveasfilename(
            title="Сохранить график",
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("PDF", "*.pdf"), ("SVG", "*.svg")],
            initialdir=initial_dir,
            initialfile=f"gps_stability_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        )
        
        if filename:
            UIPersistence.set_last_dir(filename)
            try:
                self.current_fig.savefig(filename, dpi=300, bbox_inches='tight')
                messagebox.showinfo("Успех", "График сохранен", parent=self.window)
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить: {str(e)}", parent=self.window)