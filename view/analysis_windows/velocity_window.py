#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЧИСТОЕ ПРЕДСТАВЛЕНИЕ - Окно анализа скоростей.
ИСПРАВЛЕНО: добавлен выбор папки как в трансформации
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
from pathlib import Path

from view.themes import Theme
from view.widgets import ModernButton, InteractiveZoom
from matplotlib.widgets import RectangleSelector


class VelocityAnalysisWindow:
    """
    Окно отображения результатов анализа скоростей.
    ИСПРАВЛЕНО: добавлен выбор папки как в трансформации
    """
    
    def __init__(self, parent, controller):
        """
        Args:
            parent: Родительское окно
            controller: Контроллер приложения
        """
        self.parent = parent
        self.controller = controller
        self.current_dir = Path(controller.app_context.results_dir)
        
        # Данные
        self.analysis_results = None
        self.interactive_zoom = None
        self.current_fig = None
        self.current_canvas = None
        self.plot_lines = {}
        
        # Всегда три оси
        self.visible_axes = ['V_E', 'V_N', 'V_UP']
        
        # Переменные для выбора файлов
        self.file_vars: Dict[str, tk.BooleanVar] = {}
        
        # Создаем окно
        self.window = tk.Toplevel(parent)
        self.window.title("Анализ скоростей VEL файлов")
        self.window.geometry("1400x900")
        self.window.minsize(1200, 700)
        self.window.configure(bg=Theme.BG_PRIMARY)
        
        self.center_window()
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.create_widgets()
        self.show_folder_selection_prompt()
    
    def on_close(self):
        """Закрытие окна."""
        try:
            self.window.grab_release()
        except:
            pass
        self.window.destroy()

    def center_window(self):
        """Центрирование окна."""
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
        """Создание интерфейса."""
        # Главный контейнер
        main_container = tk.Frame(self.window, bg=Theme.BG_PRIMARY)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # ============ ВЕРХНЯЯ ПАНЕЛЬ С ЗАГОЛОВКОМ ============
        header = tk.Frame(main_container, bg=Theme.BG_PRIMARY)
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
            font=("Segoe UI", 10),
        ).pack(side=tk.LEFT, padx=2)

        ModernButton(
            btn_frame,
            text="✗ Сбросить все",
            command=self.deselect_all_files,
            width=12,
            font=("Segoe UI", 10),
        ).pack(side=tk.LEFT, padx=2)
        
        # ============ СЕКЦИЯ ВЫБОРА ПАПКИ ============
        folder_frame = tk.Frame(main_container, bg=Theme.BG_PRIMARY)
        folder_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Подпись
        tk.Label(
            folder_frame,
            text="📂 Папка с VEL файлами:",
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
        tk.Frame(main_container, height=1, bg=Theme.BORDER).pack(fill=tk.X, pady=(0, 10))
        
        # ============ ПРОГРЕСС-БАР ============
        self.create_progress_bar(main_container)
        
        # ============ ВКЛАДКИ ============
        self.notebook = ttk.Notebook(main_container)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Вкладка с графиками
        self.plot_frame = tk.Frame(self.notebook, bg=Theme.BG_PRIMARY)
        self.notebook.add(self.plot_frame, text="Графики")
        
        # Вкладка с таблицей
        self.table_frame = tk.Frame(self.notebook, bg=Theme.BG_PRIMARY)
        self.notebook.add(self.table_frame, text="Результаты")
        
        # Вкладка со сводкой
        self.summary_frame = tk.Frame(self.notebook, bg=Theme.BG_PRIMARY)
        self.notebook.add(self.summary_frame, text="Сводка")
        
        # ============ НИЖНЯЯ ПАНЕЛЬ - ГАЛОЧКИ ФАЙЛОВ ============
        self.create_file_selector(main_container)
        
        # ============ СТАТУСНАЯ СТРОКА ============
        self.create_status_bar(main_container)
    
    def show_folder_selection_prompt(self):
        """Показывает предложение выбрать папку."""
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

    def _on_browse_folder(self):
        """Открывает диалог выбора папки с VEL файлами."""
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
            title="Выберите папку с VEL файлами",
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
        
        # ИСПРАВЛЕНИЕ: Сохраняем путь для контроллера
        import types
        self.controller._temp_analysis_folder = str(self.current_dir)
        
        # Запрашиваем анализ
        self.controller.request_velocity_analysis(self)
    
    def create_file_selector(self, parent):
        """Создает нижнюю панель с галочками файлов."""
        self.file_frame = tk.Frame(parent, bg=Theme.BG_SECONDARY, height=40)
        self.file_frame.pack(fill=tk.X, pady=(10, 0))
        self.file_frame.pack_propagate(False)
        
        # Контейнер для галочек без прокрутки
        self.file_container = tk.Frame(self.file_frame, bg=Theme.BG_SECONDARY)
        self.file_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
    
    def create_progress_bar(self, parent):
        """Создает прогресс-бар."""
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
        """Создает статусную строку."""
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
    
    def show_loading(self, message: str):
        """Показывает индикатор загрузки."""
        self.progress_label.config(text=message)
        self.progress_frame.pack(fill=tk.X, pady=(0, 10))
        self.progress_bar.start(10)
        self.window.update()
    
    def hide_loading(self):
        """Скрывает индикатор загрузки."""
        self.progress_bar.stop()
        self.progress_frame.pack_forget()
    
    # ============ МЕТОДЫ ДЛЯ КОНТРОЛЛЕРА ============
    
    def update_results(self, results: Dict, summary: Dict):
        """Обновляет данные."""
        self.analysis_results = results
        self.hide_loading()
        
        self.update_file_list()
        self.update_results_table()
        self.update_summary(summary)
        self.update_plots()
        
        file_count = len(results)
        self.file_count_label.config(text=f"{file_count} файлов")
        
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
    
    def show_error(self, error: str):
        """Показывает ошибку."""
        self.hide_loading()
        self.status_label.config(text=f"Ошибка", fg=Theme.ERROR)
        
        for frame in [self.table_frame, self.plot_frame, self.summary_frame]:
            for widget in frame.winfo_children():
                widget.destroy()
            
            tk.Label(
                frame,
                text=f"❌ {error}",
                font=("Arial", 11),
                fg=Theme.ERROR,
                bg=Theme.BG_PRIMARY,
            ).pack(expand=True)
    
    # ============ УПРАВЛЕНИЕ ФАЙЛАМИ ============
    
    def update_file_list(self):
        """Обновляет список файлов в нижней панели."""
        # Очищаем старый список
        for widget in self.file_container.winfo_children():
            widget.destroy()
        
        self.file_vars.clear()
        
        if not self.analysis_results:
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
                font=("Consolas", 9),
                anchor="w",
            )
            cb.pack(side=tk.LEFT, padx=8)
            
            # Всплывающая подсказка
            self.create_tooltip(cb, filename)
    
    def create_tooltip(self, widget, text):
        """Создает всплывающую подсказку."""
        def show_tooltip(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
            
            label = tk.Label(
                tooltip,
                text=text,
                bg="#ffffe0",
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
        """Выбирает все файлы."""
        for var in self.file_vars.values():
            var.set(True)
        self.update_plot_visibility()
    
    def deselect_all_files(self):
        """Снимает выбор со всех файлов."""
        for var in self.file_vars.values():
            var.set(False)
        self.update_plot_visibility()
    
    def get_selected_files(self) -> Set[str]:
        """Возвращает выбранные файлы."""
        return {
            filename for filename, var in self.file_vars.items()
            if var.get()
        }
    
    # ============ ОБНОВЛЕНИЕ ВКЛАДОК ============
    
    def update_results_table(self):
        """Обновляет таблицу."""
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
        
        columns = ['Файл', 'Строк', 'Время', 'V_E', 'V_N', 'V_UP', '2D', '3D']
        
        tree_frame = tk.Frame(self.table_frame, bg=Theme.BG_PRIMARY)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show='headings',
            height=20
        )
        
        widths = [200, 60, 120, 70, 70, 70, 70, 70]
        for col, width in zip(columns, widths):
            tree.heading(col, text=col)
            tree.column(col, width=width, minwidth=50)
        
        for filename, result in self.analysis_results.items():
            data = result.get('data', {})
            stats = result.get('statistics', {})
            
            time_span = f"{data.get('time_span', [0,0])[0]:.0f}-{data.get('time_span', [0,0])[1]:.0f}с"
            
            values = [
                filename[:30] + "..." if len(filename) > 30 else filename,
                stats.get('rows_analyzed', 0),
                time_span,
                f"{stats.get('max_v_e', 0):.3f}",
                f"{stats.get('max_v_n', 0):.3f}",
                f"{stats.get('max_v_up', 0):.3f}",
                f"{stats.get('max_speed_2d', 0):.3f}",
                f"{stats.get('max_speed_3d', 0):.3f}",
            ]
            
            tree.insert('', 'end', values=values)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def update_summary(self, summary: Dict):
        """Обновляет сводку."""
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
        text_widget.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        max_vel = summary.get('max_velocities', {})
        max_speed = summary.get('max_speeds', {})
        
        text_widget.insert(tk.END, f"Файлов: {summary.get('total_files', 0)}\n\n")
        text_widget.insert(tk.END, f"Макс V_E: {max_vel.get('v_e', 0):.3f} м/с\n")
        text_widget.insert(tk.END, f"Макс V_N: {max_vel.get('v_n', 0):.3f} м/с\n")
        text_widget.insert(tk.END, f"Макс V_UP: {max_vel.get('v_up', 0):.3f} м/с\n")
        text_widget.insert(tk.END, f"Макс 2D: {max_speed.get('2d', 0):.3f} м/с\n")
        text_widget.insert(tk.END, f"Макс 3D: {max_speed.get('3d', 0):.3f} м/с\n")
        
        text_widget.config(state=tk.DISABLED)
    
    def update_plots(self):
        """Обновляет графики."""
        for widget in self.plot_frame.winfo_children():
            widget.destroy()
        
        if not self.analysis_results:
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
            tk.Label(
                self.plot_frame,
                text="Не выбрано файлов",
                font=("Arial", 11),
                fg=Theme.WARNING,
                bg=Theme.BG_PRIMARY,
            ).pack(expand=True)
            return
        
        try:
            # Три графика
            fig, axes = plt.subplots(1, 3, figsize=(16, 6))
            fig.patch.set_facecolor('white')
            
            colors = ['#e6194b', '#3cb44b', '#ffe119', '#4363d8', '#f58231',
                     '#911eb4', '#42d4f4', '#f032e6', '#bfef45', '#fabed4']
            
            self.plot_lines = {}
            
            axis_titles = {
                0: 'V_E (Восток)',
                1: 'V_N (Север)',
                2: 'V_UP (Вертикаль)'
            }
            
            for idx, filename in enumerate(sorted(selected_files)):
                if filename not in self.analysis_results:
                    continue
                
                result = self.analysis_results[filename]
                data = result.get('data', {})
                
                time = data.get('time', np.array([]))
                v_e = data.get('v_e', np.array([]))
                v_n = data.get('v_n', np.array([]))
                v_up = data.get('v_up', np.array([]))
                
                if len(time) == 0:
                    continue
                
                if len(time) > 1000:
                    step = len(time) // 1000
                    time = time[::step]
                    v_e = v_e[::step]
                    v_n = v_n[::step]
                    v_up = v_up[::step]
                
                color = colors[idx % len(colors)]
                label = filename[:12] + "..." if len(filename) > 12 else filename
                
                line0, = axes[0].plot(time, v_e, color=color, linewidth=1.2, label=label)
                line1, = axes[1].plot(time, v_n, color=color, linewidth=1.2, label=label)
                line2, = axes[2].plot(time, v_up, color=color, linewidth=1.2, label=label)
                
                self.plot_lines[filename] = {
                    'V_E': line0,
                    'V_N': line1,
                    'V_UP': line2
                }
            
            from matplotlib.ticker import FuncFormatter
            
            def format_time(seconds, pos):
                hours = int(seconds // 3600)
                minutes = int((seconds % 3600) // 60)
                return f"{hours:02d}:{minutes:02d}"
            
            for i in range(3):
                ax = axes[i]
                ax.xaxis.set_major_formatter(FuncFormatter(format_time))
                ax.set_xlabel('Время')
                ax.set_ylabel('м/с')
                ax.set_title(axis_titles[i])
                ax.grid(True, alpha=0.3)
                ax.axhline(y=0, color='gray', linestyle='--', alpha=0.5, linewidth=0.8)
                
                if ax.lines:
                    ax.legend(loc='upper right', fontsize=8)
            
            plt.tight_layout()
            
            canvas = FigureCanvasTkAgg(fig, self.plot_frame)
            canvas.draw()
            
            # Уничтожаем старый зум если есть
            if self.interactive_zoom:
                try:
                    del self.interactive_zoom
                except:
                    pass
            
            self.interactive_zoom = InteractiveZoom(fig, axes)
            self.current_fig = fig
            self.current_canvas = canvas
            
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            tk.Label(
                self.plot_frame,
                text=f"Ошибка: {str(e)}",
                font=("Arial", 11),
                fg=Theme.ERROR,
                bg=Theme.BG_PRIMARY,
            ).pack(expand=True)
    
    def update_plot_visibility(self):
        """Обновляет видимость графиков."""
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
        """Сбрасывает зум."""
        if self.interactive_zoom:
            self.interactive_zoom.reset_all_zooms()
    
    # ============ ОБРАБОТЧИКИ ============
    
    def on_refresh(self):
        """Обновление."""
        self.show_loading("Обновление...")
        self.controller.request_velocity_analysis(self)
    
    def on_export(self):
        """Экспорт."""
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