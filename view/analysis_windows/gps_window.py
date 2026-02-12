#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЧИСТОЕ ПРЕДСТАВЛЕНИЕ - Окно анализа GPS созвездия.
ИСПРАВЛЕНО: отображение метрик в минутах, а не абсолютных интервалах.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime

from view.themes import Theme
from view.widgets import ModernButton, InteractiveZoom


class GPSAnalysisWindow:
    """
    Окно отображения результатов анализа GPS созвездия.
    ТОЛЬКО UI, никаких вычислений!
    
    ИСПРАВЛЕНО: показываем интервалы/минуту, цвет по частоте пропаданий.
    """
    
    ALL_SATELLITES = [f'G{i:02d}' for i in range(1, 33)]
    
    # Цвета для категорий стабильности (по частоте!)
    STABILITY_COLORS = {
        'excellent': '#198754',  # зеленый - <0.02 инт/мин
        'good': '#0d6efd',       # синий - 0.02-0.1 инт/мин
        'moderate': '#fd7e14',   # оранжевый - 0.1-0.2 инт/мин
        'unstable': '#dc3545',   # красный - 0.2-0.5 инт/мин
        'bad': '#b02a37',        # темно-красный - 0.5-1.0 инт/мин
        'critical': '#8b0000',   # очень темный красный - >1.0 инт/мин
        'invisible': '#6c757d',  # серый
    }
    
    def __init__(self, parent, controller):
        self.parent = parent
        self.controller = controller
        self.results_dir = str(controller.app_context.results_dir)
        
        self.analysis_results = None
        self.interactive_zoom = None
        self.current_filename = None
        self.current_fig = None
        self.current_canvas = None
        
        self.window = tk.Toplevel(parent)
        self.window.title("Анализ GPS созвездия - Оценка стабильности")
        self.window.geometry("1400x900")
        self.window.minsize(1200, 700)
        self.window.configure(bg=Theme.BG_PRIMARY)
        
        self.center_window()
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.create_widgets()
        self.setup_text_tags()
        
        self.controller.request_gps_analysis(self)
    
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
        
        self.create_header(main_frame)
        self.create_progress_bar(main_frame)
        
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
        
        self.create_status_bar(main_frame)
        self.setup_export_tab()
        self.show_loading("Анализ GPS созвездия...")
    
    def setup_text_tags(self):
        pass
    
    def _configure_text_tags(self, text_widget):
        # Категории качества
        text_widget.tag_config("quality_excellent", foreground="#198754", font=("Consolas", 10, "bold"))
        text_widget.tag_config("quality_good", foreground="#0d6efd", font=("Consolas", 10, "bold"))
        text_widget.tag_config("quality_moderate", foreground="#fd7e14", font=("Consolas", 10, "bold"))
        text_widget.tag_config("quality_poor", foreground="#dc3545", font=("Consolas", 10, "bold"))
        text_widget.tag_config("quality_critical", foreground="#8b0000", font=("Consolas", 10, "bold"))
        
        # Стабильность спутников (по частоте)
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
            text="🔄 Обновить",
            command=self.on_refresh,
            width=10,
        ).pack(side=tk.LEFT, padx=2)
        
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
        """Обновляет вкладку с графиком - ДИАГНОСТИЧЕСКАЯ ВЕРСИЯ"""
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
        
        print(f"\n{'='*60}")
        print(f"ОТРИСОВКА ГРАФИКА: {self.current_filename}")
        print(f"{'='*60}")
        
        result = self.analysis_results[self.current_filename]
        satellite_stats = result.get('satellite_stats', {})
        
        # ПРОВЕРЯЕМ, ЧТО ПРИШЛО
        print(f"Тип данных: {type(satellite_stats)}")
        print(f"Количество спутников в stats: {len(satellite_stats)}")
        
        if satellite_stats:
            # Возьмем первый спутник для проверки
            sample_sat = list(satellite_stats.keys())[0]
            sample_stats = satellite_stats[sample_sat]
            print(f"\nПРОВЕРКА СПУТНИКА {sample_sat}:")
            print(f"  is_visible: {sample_stats.get('is_visible', False)}")
            print(f"  num_intervals: {sample_stats.get('num_intervals', 0)}")
            print(f"  intervals_per_minute: {sample_stats.get('intervals_per_minute', 999)}")
            print(f"  stability_category: {sample_stats.get('stability_category', ('N/A', 'N/A'))}")
            
            # Проверяем все видимые спутники
            print(f"\nВСЕ ВИДИМЫЕ СПУТНИКИ:")
            for sat, stats in satellite_stats.items():
                if stats.get('is_visible', False):
                    ipm = stats.get('intervals_per_minute', 999)
                    cat = stats.get('stability_category', ('N/A', 'N/A'))
                    cat_name = cat[0] if isinstance(cat, tuple) else cat
                    print(f"  {sat}: ИПМ={ipm:.3f}, категория={cat_name}")
        
        try:
            fig, ax = plt.subplots(figsize=(16, 14))
            fig.patch.set_facecolor('white')
            
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
                
                # По умолчанию - спутник отсутствует (серый)
                color = '#CCCCCC'
                alpha = 0.05
                is_visible = False
                ipm = 999.0
                num_intervals = 0
                visibility_percent = 0
                intervals = []
                
                if sat in satellite_stats:
                    stats = satellite_stats[sat]
                    
                    # ИСПРАВЛЕНИЕ: stats может быть словарем или объектом SatelliteStatistics
                    if hasattr(stats, 'get'):
                        # Это словарь
                        is_visible = stats.get('is_visible', False)
                        ipm = stats.get('intervals_per_minute', 999)
                        num_intervals = stats.get('num_intervals', 0)
                        visibility_percent = stats.get('visibility_percent', 0)
                        intervals = stats.get('intervals', [])
                    else:
                        # Это объект SatelliteStatistics
                        is_visible = stats.is_visible
                        ipm = stats.intervals_per_minute
                        num_intervals = stats.num_intervals
                        visibility_percent = stats.visibility_percent
                        intervals = stats.intervals if hasattr(stats, 'intervals') else []
                    
                    if is_visible:
                        # ============ ИСПРАВЛЕННАЯ ЛОГИКА ЦВЕТОВ ============
                        # Эталонный/Отличный - зеленый
                        if ipm <= 0.05:
                            color = self.STABILITY_COLORS['excellent']  # #198754
                            alpha = 0.7
                            excellent_count += 1
                        # Хороший - синий
                        elif ipm <= 0.1:
                            color = self.STABILITY_COLORS['good']  # #0d6efd
                            alpha = 0.7
                            good_count += 1
                        # Умеренный - оранжевый
                        elif ipm <= 0.2:
                            color = self.STABILITY_COLORS['moderate']  # #fd7e14
                            alpha = 0.7
                            moderate_count += 1
                        # Нестабильный - красный
                        elif ipm <= 0.5:
                            color = self.STABILITY_COLORS['unstable']  # #dc3545
                            alpha = 0.7
                            unstable_count += 1
                        # Плохой - темно-красный
                        elif ipm <= 1.0:
                            color = self.STABILITY_COLORS['bad']  # #b02a37
                            alpha = 0.7
                            bad_count += 1
                        # Критический - очень темный красный
                        else:
                            color = self.STABILITY_COLORS['critical']  # #8b0000
                            alpha = 0.7
                            critical_count += 1
                        
                        # Прозрачность зависит от процента видимости
                        alpha = 0.3 + 0.5 * (visibility_percent / 100)
                        
                        # Отрисовка интервалов
                        if intervals:
                            for interval in intervals:
                                # interval может быть словарем или объектом
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
                        
                        # Маркер только для проблемных (>0.2/мин И >1 интервал)
                        is_problematic = ipm > 0.2 and num_intervals > 1
                        if is_problematic:
                            ax.plot(
                                time_range[0] + 10, y_pos,
                                marker='v',
                                color='red',
                                markersize=8,
                                markeredgecolor='darkred',
                                markeredgewidth=1
                            )
                    else:
                        # Спутник есть в статистике, но видимость 0% - серый с низкой прозрачностью
                        ax.barh(
                            y=y_pos,
                            width=0,
                            height=0.7,
                            color='#CCCCCC',
                            alpha=0.1
                        )
                else:
                    # НЕТ ДАННЫХ - серый с очень низкой прозрачностью
                    ax.barh(
                        y=y_pos,
                        width=0,
                        height=0.7,
                        color='#CCCCCC',
                        alpha=0.05
                    )
            
            print(f"\nСТАТИСТИКА ЦВЕТОВ:")
            print(f"  Эталон/Отлично: {excellent_count}")
            print(f"  Хорошо: {good_count}")
            print(f"  Умеренно: {moderate_count}")
            print(f"  Нестабильно: {unstable_count}")
            print(f"  Плохо: {bad_count}")
            print(f"  Критично: {critical_count}")
            print(f"{'='*60}\n")
            
            # Настройка осей
            ax.set_yticks(np.arange(len(self.ALL_SATELLITES)))
            ax.set_yticklabels(self.ALL_SATELLITES[::-1], fontsize=9)
            ax.set_xlim(time_range[0], time_range[1])
            
            ax.set_xlabel('Время наблюдения (секунды)', fontsize=12)
            ax.set_ylabel('Спутники GPS', fontsize=12)
            
            # Заголовок с длительностью и статистикой
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
            
            # Информационная панель со статистикой
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
            
            # Легенда
            from matplotlib.patches import Patch
            from matplotlib.lines import Line2D
            
            legend_elements = [
                Patch(facecolor=self.STABILITY_COLORS['excellent'], alpha=0.7, 
                    label='Эталон/Отлично (<0.05/мин)'),
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
                    markersize=8, label='Проблемный (>0.2/мин, >1 интервал)',
                    markeredgecolor='darkred')
            ]
            
            ax.legend(handles=legend_elements, loc='lower left', fontsize=8, ncol=2)
            
            plt.tight_layout()
            
            canvas = FigureCanvasTkAgg(fig, self.plot_frame)
            canvas.draw()
            
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


    def update_stats_tab(self):
        """Обновляет вкладку со статистикой - акцент на частоту/мин."""
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
            
            # Проблемные спутники (по частоте!)
            problem_sats = []
            for sat, stats in result.get('satellite_stats', {}).items():
                if stats.get('is_visible', False):
                    ipm = stats.get('intervals_per_minute', 0)
                    if ipm > 0.2:  # >1 раза в 5 минут
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
                
                # Сортируем по частоте (худшие сверху)
                for sat, stats, ipm in sorted(problem_sats, key=lambda x: x[2], reverse=True)[:10]:
                    num_int = stats.get('num_intervals', 0)
                    avg_dur = stats.get('avg_duration', 0)
                    visibility = stats.get('visibility_percent', 0)
                    
                    # Категория по частоте
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
            
            # Отличные спутники (для контраста)
            excellent_sats = []
            for sat, stats in result.get('satellite_stats', {}).items():
                if stats.get('is_visible', False):
                    ipm = stats.get('intervals_per_minute', 999)
                    if ipm <= 0.05:  # <1 в 20 минут
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
        text_widget.insert(tk.END, f"Папка с данными: {self.results_dir}\n")
        text_widget.insert(tk.END, f"Всего файлов: {len(self.analysis_results)}\n\n")
        
        # Шкала оценки
        text_widget.insert(tk.END, "📊 ШКАЛА ОЦЕНКИ СТАБИЛЬНОСТИ:\n")
        text_widget.insert(tk.END, "  • <0.05/мин — Эталон/Отлично (1 пропадание >20 мин)\n", "sat_excellent")
        text_widget.insert(tk.END, "  • 0.05-0.1/мин — Хорошо (1 пропадание 10-20 мин)\n", "sat_good")
        text_widget.insert(tk.END, "  • 0.1-0.2/мин — Умеренно (1 пропадание 5-10 мин)\n", "sat_moderate")
        text_widget.insert(tk.END, "  • 0.2-0.5/мин — Нестабильно (1 пропадание 2-5 мин)\n", "sat_unstable")
        text_widget.insert(tk.END, "  • 0.5-1.0/мин — Плохо (1 пропадание 1-2 мин)\n", "sat_bad")
        text_widget.insert(tk.END, "  • >1.0/мин — Критически (>1 пропадания в минуту)\n\n", "sat_critical")
        
        # Сортируем файлы по качеству
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
            
            # Проблемные по частоте
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
            
            # Эталонные спутники
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
        self.controller.request_gps_analysis(self)
    
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
            initial_dir = self.results_dir
        
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
            initial_dir = self.results_dir
        
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