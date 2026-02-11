#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Кастомные виджеты для современного интерфейса.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Callable, Optional, Dict, List, Any
import numpy as np

from frontend.themes import Theme


class ModernButton(tk.Button):
    """
    Современная кнопка с ховер-эффектом.
    """
    
    def __init__(self, master=None, **kwargs):
        # Стандартные настройки
        default_kwargs = {
            'font': ("Segoe UI", 9),
            'relief': tk.FLAT,
            'cursor': 'hand2',
            'padx': 12,
            'pady': 4,
            'bd': 1,
            'bg': Theme.BG_SECONDARY,
            'fg': Theme.FG_PRIMARY,
            'activebackground': Theme.HOVER,
            'activeforeground': Theme.FG_PRIMARY,
            'highlightthickness': 0,
        }
        
        default_kwargs.update(kwargs)
        super().__init__(master, **default_kwargs)
        
        # Сохраняем оригинальный цвет
        self._original_bg = self['bg']
        self._original_fg = self['fg']
        
        self.bind('<Enter>', self._on_enter)
        self.bind('<Leave>', self._on_leave)
    
    def _on_enter(self, e):
        if self['state'] != 'disabled':
            if self._original_bg in [
                Theme.ACCENT_BLUE, Theme.ACCENT_GREEN, Theme.ACCENT_RED,
                Theme.ACCENT_ORANGE, Theme.ACCENT_PURPLE, Theme.ACCENT_CYAN
            ]:
                # Затемняем цветные кнопки
                dark_colors = {
                    Theme.ACCENT_BLUE: "#0b5ed7",
                    Theme.ACCENT_GREEN: "#157347",
                    Theme.ACCENT_RED: "#bb2d3b",
                    Theme.ACCENT_ORANGE: "#e46a0b",
                    Theme.ACCENT_PURPLE: "#5e3a9c",
                    Theme.ACCENT_CYAN: "#0bacd0",
                }
                self['bg'] = dark_colors.get(self._original_bg, self._original_bg)
            else:
                self['bg'] = Theme.HOVER
    
    def _on_leave(self, e):
        if self['state'] != 'disabled':
            self['bg'] = self._original_bg
            self['fg'] = self._original_fg


class FileEntryWidget(tk.Frame):
    """
    Виджет для выбора файла с кнопками.
    """
    
    def __init__(
        self,
        master,
        label_text: str,
        browse_callback: Callable,
        open_callback: Callable,
        stitch_callback: Optional[Callable] = None,
        **kwargs
    ):
        super().__init__(master, bg=Theme.BG_PRIMARY, **kwargs)
        
        self._browse_callback = browse_callback
        self._open_callback = open_callback
        self._stitch_callback = stitch_callback
        
        # Контейнер
        container = tk.Frame(self, bg=Theme.BG_PRIMARY)
        container.pack(fill=tk.X, padx=2, pady=1)
        
        # Метка
        label = tk.Label(
            container,
            text=label_text + ":",
            font=("Segoe UI", 9),
            bg=Theme.BG_PRIMARY,
            fg=Theme.FG_PRIMARY,
            anchor="w",
            width=14,
        )
        label.pack(side=tk.LEFT)
        
        # Поле ввода
        self._entry = tk.Entry(
            container,
            font=("Consolas", 9),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY,
            relief=tk.SOLID,
            bd=1,
            highlightcolor=Theme.ACCENT_BLUE,
            highlightthickness=1,
        )
        self._entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # Кнопки
        btn_frame = tk.Frame(container, bg=Theme.BG_PRIMARY)
        btn_frame.pack(side=tk.RIGHT)
        
        # Сшивка (только для JPS)
        if stitch_callback:
            btn_stitch = ModernButton(
                btn_frame,
                text="🔗",
                width=2,
                bg=Theme.BG_SECONDARY,
                command=self._on_stitch,
            )
            btn_stitch.pack(side=tk.RIGHT, padx=(2, 0))
        
        # Открыть
        btn_open = ModernButton(
            btn_frame,
            text="📄",
            width=2,
            bg=Theme.BG_SECONDARY,
            command=self._on_open,
        )
        btn_open.pack(side=tk.RIGHT, padx=(2, 0))
        
        # Обзор
        btn_browse = ModernButton(
            btn_frame,
            text="📁",
            width=2,
            bg=Theme.BG_SECONDARY,
            command=self._on_browse,
        )
        btn_browse.pack(side=tk.RIGHT, padx=(2, 0))
    
    def _on_browse(self):
        """Обработчик кнопки обзора."""
        path = self._browse_callback()
        if path:
            self._entry.delete(0, tk.END)
            self._entry.insert(0, path)
    
    def _on_open(self):
        """Обработчик кнопки открытия."""
        path = self.get_value()
        if path:
            self._open_callback(path)
    
    def _on_stitch(self):
        """Обработчик кнопки сшивки."""
        if self._stitch_callback:
            self._stitch_callback()
    
    def get_value(self) -> str:
        """Возвращает значение поля."""
        return self._entry.get().strip()
    
    def set_value(self, value: str) -> None:
        """Устанавливает значение поля."""
        self._entry.delete(0, tk.END)
        self._entry.insert(0, value)


class CollapsibleFrame(tk.Frame):
    """
    Сворачиваемая панель с заголовком.
    """
    
    def __init__(self, master, title="", **kwargs):
        kwargs.pop('bg', None)
        super().__init__(master, bg=Theme.BG_PRIMARY, **kwargs)
        
        self._is_expanded = True
        
        # Заголовок
        self._header = tk.Frame(
            self,
            bg=Theme.BG_SECONDARY,
            relief=tk.FLAT,
            bd=1,
        )
        self._header.pack(fill=tk.X, pady=(0, 1))
        
        # Кнопка сворачивания
        self._toggle_btn = tk.Button(
            self._header,
            text="▼",
            font=("Segoe UI", 8),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_SECONDARY,
            relief=tk.FLAT,
            cursor='hand2',
            width=2,
            bd=0,
            command=self._toggle,
        )
        self._toggle_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        # Заголовок
        tk.Label(
            self._header,
            text=title,
            font=("Segoe UI", 10, "bold"),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY,
        ).pack(side=tk.LEFT, padx=5, pady=5)
        
        # Контейнер для содержимого
        self.content = tk.Frame(self, bg=Theme.BG_PRIMARY)
        self.content.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
    
    def _toggle(self):
        """Сворачивает/разворачивает панель."""
        if self._is_expanded:
            self.content.pack_forget()
            self._toggle_btn.config(text="▶")
            self._is_expanded = False
        else:
            self.content.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
            self._toggle_btn.config(text="▼")
            self._is_expanded = True

class InteractiveZoom:
    """
    Интерактивный зум для matplotlib графиков.
    Встроенная реализация, не требует внешних зависимостей.
    """
    
    def __init__(self, fig, axes):
        self.fig = fig
        self.axes = [axes] if not isinstance(axes, (list, np.ndarray)) else axes.flatten()
        
        # Сохраняем исходные лимиты
        self._original_xlim = {}
        self._original_ylim = {}
        
        for ax in self.axes:
            self._original_xlim[ax] = ax.get_xlim()
            self._original_ylim[ax] = ax.get_ylim()
        
        self._selectors = []
        self._connect()
    
    def _connect(self):
        from matplotlib.widgets import RectangleSelector
        
        for ax in self.axes:
            selector = RectangleSelector(
                ax,
                self._on_select,
                useblit=True,
                button=1,
                spancoords='data',
                interactive=True,
                props=dict(facecolor='red', alpha=0.3, edgecolor='red'),
            )
            self._selectors.append(selector)
            self.fig.canvas.mpl_connect('button_press_event', self._on_double_click)
    
    def _on_select(self, eclick, erelease):
        ax = eclick.inaxes
        if ax is None:
            return
        
        x1, y1 = eclick.xdata, eclick.ydata
        x2, y2 = erelease.xdata, erelease.ydata
        
        ax.set_xlim(min(x1, x2), max(x1, x2))
        ax.set_ylim(min(y1, y2), max(y1, y2))
        self.fig.canvas.draw_idle()
    
    def _on_double_click(self, event):
        if event.dblclick and event.inaxes:
            ax = event.inaxes
            if ax in self._original_xlim:
                ax.set_xlim(self._original_xlim[ax])
                ax.set_ylim(self._original_ylim[ax])
                self.fig.canvas.draw_idle()
    
    def reset_all_zooms(self):
        for ax in self.axes:
            if ax in self._original_xlim:
                ax.set_xlim(self._original_xlim[ax])
                ax.set_ylim(self._original_ylim[ax])
        self.fig.canvas.draw_idle()

class TransformFileDialog:
    """
    Диалог выбора файлов для трансформации в TBL.
    """
    
    def __init__(self, parent, working_dir: str, callback: Callable):
        self._parent = parent
        self._working_dir = Path(working_dir)
        self._callback = callback
        self._vars: Dict[str, tk.BooleanVar] = {}
        self._checkboxes: Dict[str, tk.Checkbutton] = {}
        
        self._create_dialog()
    
    def _create_dialog(self):
        """Создаёт диалоговое окно."""
        self.dialog = tk.Toplevel(self._parent)
        self.dialog.title("Трансформация в TBL")
        self.dialog.geometry("550x500")
        self.dialog.transient(self._parent)
        self.dialog.grab_set()
        self.dialog.configure(bg=Theme.BG_PRIMARY)
        
        # Центрируем
        self.dialog.update_idletasks()
        x = self._parent.winfo_rootx() + 100
        y = self._parent.winfo_rooty() + 100
        self.dialog.geometry(f"+{x}+{y}")
        
        self._create_widgets()
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _create_widgets(self):
        """Создаёт виджеты."""
        main = tk.Frame(self.dialog, bg=Theme.BG_PRIMARY, padx=15, pady=15)
        main.pack(fill=tk.BOTH, expand=True)
        
        # Заголовок
        tk.Label(
            main,
            text="Выберите файлы для трансформации",
            font=("Segoe UI", 11, "bold"),
            bg=Theme.BG_PRIMARY,
            fg=Theme.FG_PRIMARY,
        ).pack(anchor="w", pady=(0, 10))
        
        # Путь
        results_path = self._working_dir / "results"
        tk.Label(
            main,
            text=f"📁 {results_path}",
            font=("Consolas", 8),
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
            ("Phase_L1.VEL", "ROVER_KIN", "Фаза L1"),
            ("Phase_IO.VEL", "ROVER_KIN", "Фаза IO"),
            ("PhaseIOS.VEL", "ROVER_KIN", "Фаза IOS"),
            ("PhaseL1S.VEL", "ROVER_KIN", "Фаза L1S"),
            ("Base_Std.QC", "BASE_STD", "Стандарт базы"),
            ("Rover_Std.QC", "ROVER_STD", "Стандарт ровера"),
        ]
        
        for filename, _, description in file_options:
            file_path = results_path / filename
            exists = file_path.exists()
            
            var = tk.BooleanVar(value=exists and filename == "Phase_L1.VEL")
            self._vars[filename] = var
            
            row = tk.Frame(scrollable, bg=Theme.BG_PRIMARY)
            row.pack(fill=tk.X, pady=2)
            
            # Чекбокс
            cb = tk.Checkbutton(
                row,
                variable=var,
                bg=Theme.BG_PRIMARY,
                fg=Theme.FG_PRIMARY,
                activebackground=Theme.HOVER,
                selectcolor="white" if exists else Theme.BG_PRIMARY,
                state="normal" if exists else "disabled",
            )
            cb.pack(side="left")
            self._checkboxes[filename] = cb
            
            # Информация
            info = tk.Frame(row, bg=Theme.BG_PRIMARY)
            info.pack(side="left", padx=(5, 0), fill=tk.X, expand=True)
            
            tk.Label(
                info,
                text=filename,
                font=("Consolas", 9, "bold" if exists else "normal"),
                bg=Theme.BG_PRIMARY,
                fg=Theme.FG_PRIMARY if exists else Theme.FG_DISABLED,
                anchor="w",
            ).pack(anchor="w")
            
            status_color = Theme.SUCCESS if exists else Theme.FG_DISABLED
            status_text = "✓ Доступен" if exists else "✗ Не найден"
            
            tk.Label(
                info,
                text=status_text,
                font=("Segoe UI", 8),
                bg=Theme.BG_PRIMARY,
                fg=status_color,
            ).pack(anchor="w")
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Кнопки
        btn_frame = tk.Frame(main, bg=Theme.BG_PRIMARY)
        btn_frame.pack(fill=tk.X, pady=(15, 0))
        
        ModernButton(
            btn_frame,
            text="✓ Все",
            command=self._select_all,
            width=8,
        ).pack(side="left", padx=(0, 5))
        
        ModernButton(
            btn_frame,
            text="✗ Сброс",
            command=self._deselect_all,
            width=8,
        ).pack(side="left")
        
        ModernButton(
            btn_frame,
            text="Закрыть",
            command=self._on_close,
            width=10,
        ).pack(side="right", padx=(5, 0))
        
        ModernButton(
            btn_frame,
            text="Трансформировать",
            bg=Theme.ACCENT_GREEN,
            fg="white",
            command=self._on_transform,
            width=15,
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
        """Запускает трансформацию."""
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
        
        self._callback(selected)
        self._on_close()
    
    def _on_close(self):
        """Закрывает диалог."""
        self.dialog.destroy()
    
    def show(self):
        """Показывает диалог."""
        self.dialog.wait_window()


class BaseAnalysisDialog:
    """
    Базовый класс для диалогов анализа данных.
    """
    
    def __init__(self, parent, title: str, geometry: str = "1200x800"):
        self.parent = parent
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry(geometry)
        self.dialog.minsize(1000, 600)
        self.dialog.configure(bg=Theme.BG_PRIMARY)
        
        # Центрируем
        self.dialog.update_idletasks()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        width = self.dialog.winfo_width()
        height = self.dialog.winfo_height()
        
        x = parent_x + (parent_width - width) // 2
        y = parent_y + (parent_height - height) // 2
        
        x = max(0, min(x, self.dialog.winfo_screenwidth() - width))
        y = max(0, min(y, self.dialog.winfo_screenheight() - height))
        
        self.dialog.geometry(f"+{x}+{y}")
        
        self.dialog.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def on_close(self):
        """Обработчик закрытия."""
        try:
            self.dialog.grab_release()
        except:
            pass
        self.dialog.destroy()
    
    def show(self):
        """Показывает диалог."""
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        self.dialog.wait_window()


class VelocityAnalysisDialog(BaseAnalysisDialog):
    """
    Диалог отображения результатов анализа скоростей.
    """
    
    def __init__(self, parent, results, message_callback):
        super().__init__(parent, "Анализ скоростей VEL файлов", "1300x850")
        
        self._results = results
        self._message_callback = message_callback
        self._current_fig = None
        self._current_canvas = None
        self._interactive_zoom = None
        self._plot_lines = {}
        self._file_vars = {}
        
        self._create_widgets()
        self._update_plots()
    
    def _create_widgets(self):
        """Создаёт виджеты."""
        # Главный контейнер
        main = tk.Frame(self.dialog, bg=Theme.BG_PRIMARY)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Верхняя панель
        header = tk.Frame(main, bg=Theme.BG_SECONDARY, height=50)
        header.pack(fill=tk.X, pady=(0, 10))
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="📊 Анализ скоростей VEL файлов",
            font=("Segoe UI", 12, "bold"),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY,
        ).pack(side=tk.LEFT, padx=15, pady=12)
        
        # Кнопки управления
        btn_frame = tk.Frame(header, bg=Theme.BG_SECONDARY)
        btn_frame.pack(side=tk.RIGHT, padx=15)
        
        ModernButton(
            btn_frame,
            text="Сбросить зум",
            command=self._reset_zoom,
            width=12,
        ).pack(side=tk.LEFT, padx=2)
        
        ModernButton(
            btn_frame,
            text="Сохранить график",
            command=self._save_plot,
            width=12,
        ).pack(side=tk.LEFT, padx=2)
        
        # Notebook
        self._notebook = ttk.Notebook(main)
        self._notebook.pack(fill=tk.BOTH, expand=True)
        
        # Вкладка с графиками
        self._plot_tab = tk.Frame(self._notebook, bg=Theme.BG_PRIMARY)
        self._notebook.add(self._plot_tab, text="Графики скоростей")
        
        # Вкладка со статистикой
        self._stats_tab = tk.Frame(self._notebook, bg=Theme.BG_PRIMARY)
        self._notebook.add(self._stats_tab, text="Статистика")
        
        # Вкладка со сводкой
        self._summary_tab = tk.Frame(self._notebook, bg=Theme.BG_PRIMARY)
        self._notebook.add(self._summary_tab, text="Сводка")
        
        # Статус
        status = tk.Frame(main, bg=Theme.BG_SECONDARY, height=25)
        status.pack(fill=tk.X, pady=(10, 0))
        status.pack_propagate(False)
        
        files_count = len([r for r in self._results.values() if r.success])
        tk.Label(
            status,
            text=f"✅ Проанализировано файлов: {files_count}",
            font=("Segoe UI", 9),
            bg=Theme.BG_SECONDARY,
            fg=Theme.SUCCESS,
        ).pack(side=tk.LEFT, padx=15, pady=2)
        
        # Заполняем статистику
        self._fill_stats_tab()
        self._fill_summary_tab()
    
    def _fill_stats_tab(self):
        """Заполняет вкладку со статистикой."""
        from backend.analyzers.velocity_analyzer import VelocityAnalysis
        
        # Treeview с прокруткой
        container = tk.Frame(self._stats_tab, bg=Theme.BG_PRIMARY, padx=10, pady=10)
        container.pack(fill=tk.BOTH, expand=True)
        
        columns = [
            'Файл', 'Строк', 'Время',
            'Макс V_E', 'Макс V_N', 'Макс V_UP',
            '2D макс', '3D макс',
        ]
        
        tree = ttk.Treeview(
            container,
            columns=columns,
            show='headings',
            height=20,
        )
        
        # Настройка колонок
        widths = [200, 60, 120, 70, 70, 70, 80, 80]
        for col, width in zip(columns, widths):
            tree.heading(col, text=col)
            tree.column(col, width=width, minwidth=50)
        
        # Скроллбар
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Заполняем данными
        for filename, result in self._results.items():
            if not result.success or not result.stats:
                continue
            
            stats = result.stats
            time_range = f"{result.time_range[0]:.0f}-{result.time_range[1]:.0f}с"
            
            values = [
                filename,
                stats.samples,
                time_range,
                f"{stats.max_v_e:.3f}",
                f"{stats.max_v_n:.3f}",
                f"{stats.max_v_up:.3f}",
                f"{stats.max_speed_2d:.3f}",
                f"{stats.max_speed_3d:.3f}",
            ]
            
            tree.insert('', 'end', values=values)
    
    def _fill_summary_tab(self):
        """Заполняет вкладку со сводкой."""
        text_widget = tk.Text(
            self._summary_tab,
            font=("Consolas", 10),
            wrap=tk.WORD,
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY,
            padx=15,
            pady=15,
        )
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        from datetime import datetime
        
        text_widget.insert(tk.END, "="*70 + "\n")
        text_widget.insert(tk.END, "СВОДКА АНАЛИЗА СКОРОСТЕЙ\n")
        text_widget.insert(tk.END, "="*70 + "\n\n")
        
        text_widget.insert(tk.END, f"Дата анализа: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n")
        text_widget.insert(tk.END, f"Всего файлов: {len(self._results)}\n\n")
        
        # Максимальные скорости
        max_v_e = 0
        max_v_n = 0
        max_v_up = 0
        max_2d = 0
        max_3d = 0
        
        for result in self._results.values():
            if result.success and result.stats:
                stats = result.stats
                max_v_e = max(max_v_e, stats.max_v_e)
                max_v_n = max(max_v_n, stats.max_v_n)
                max_v_up = max(max_v_up, stats.max_v_up)
                max_2d = max(max_2d, stats.max_speed_2d)
                max_3d = max(max_3d, stats.max_speed_3d)
        
        text_widget.insert(tk.END, "МАКСИМАЛЬНЫЕ ЗНАЧЕНИЯ:\n")
        text_widget.insert(tk.END, "-"*40 + "\n")
        text_widget.insert(tk.END, f"V_E (восток):  {max_v_e:.3f} м/с\n")
        text_widget.insert(tk.END, f"V_N (север):   {max_v_n:.3f} м/с\n")
        text_widget.insert(tk.END, f"V_UP (вверх):  {max_v_up:.3f} м/с\n")
        text_widget.insert(tk.END, f"2D скорость:   {max_2d:.3f} м/с\n")
        text_widget.insert(tk.END, f"3D скорость:   {max_3d:.3f} м/с\n")
        
        text_widget.config(state=tk.DISABLED)
    
    def _update_plots(self):
        """Строит графики скоростей."""
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        from matplotlib.ticker import FuncFormatter
        
        # Очищаем
        for widget in self._plot_tab.winfo_children():
            widget.destroy()
        
        if not self._results:
            tk.Label(
                self._plot_tab,
                text="Нет данных для отображения",
                font=("Segoe UI", 11),
                fg=Theme.FG_SECONDARY,
                bg=Theme.BG_PRIMARY,
            ).pack(pady=50)
            return
        
        # Создаём фигуру
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        fig.suptitle('Анализ скоростей из VEL файлов', fontsize=14, fontweight='bold')
        fig.patch.set_facecolor('white')
        
        # Цвета для файлов
        colors = plt.cm.Set3(np.linspace(0, 1, 12))
        
        self._plot_lines = {0: {}, 1: {}, 2: {}}
        
        # Строим графики
        for idx, (filename, result) in enumerate(self._results.items()):
            if not result.success or not result.data:
                continue
            
            color = colors[idx % len(colors)]
            data = result.data
            
            # V_E
            axes[0].plot(
                data['time'],
                data['v_e'],
                color=color,
                linewidth=1,
                alpha=0.8,
                label=filename[:20] + '...' if len(filename) > 20 else filename,
            )
            self._plot_lines[0][filename] = {'V_E': axes[0].lines[-1]}
            
            # V_N
            axes[1].plot(
                data['time'],
                data['v_n'],
                color=color,
                linewidth=1,
                alpha=0.8,
                label=filename[:20] + '...' if len(filename) > 20 else filename,
            )
            self._plot_lines[1][filename] = {'V_N': axes[1].lines[-1]}
            
            # V_UP
            axes[2].plot(
                data['time'],
                data['v_up'],
                color=color,
                linewidth=1,
                alpha=0.8,
                label=filename[:20] + '...' if len(filename) > 20 else filename,
            )
            self._plot_lines[2][filename] = {'V_UP': axes[2].lines[-1]}
        
        # Настройка осей
        def format_time(seconds, pos):
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        
        for ax in axes:
            ax.xaxis.set_major_formatter(FuncFormatter(format_time))
            ax.set_xlabel('Время (чч:мм:сс)')
            ax.set_ylabel('Скорость (м/с)')
            ax.grid(True, alpha=0.3)
            ax.axhline(y=0, color='gray', linestyle='--', alpha=0.5, linewidth=0.8)
            ax.legend(loc='upper right', fontsize=8)
        
        axes[0].set_title('Скорость по востоку (V_E)')
        axes[1].set_title('Скорость по северу (V_N)')
        axes[2].set_title('Вертикальная скорость (V_UP)')
        
        plt.tight_layout()
        
        # Встраиваем в Tkinter
        canvas = FigureCanvasTkAgg(fig, self._plot_tab)
        canvas.draw()
        
        # Интерактивный зум
        self._interactive_zoom = InteractiveZoom(fig, axes)
        
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self._current_fig = fig
        self._current_canvas = canvas
    
    def _reset_zoom(self):
        """Сбрасывает зум."""
        if self._interactive_zoom:
            self._interactive_zoom.reset_all_zooms()
    
    def _save_plot(self):
        """Сохраняет график в файл."""
        if not self._current_fig:
            return
        
        from datetime import datetime
        default_name = f"VEL_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        path = filedialog.asksaveasfilename(
            title="Сохранить график",
            defaultextension=".png",
            filetypes=[
                ("PNG файлы", "*.png"),
                ("PDF файлы", "*.pdf"),
                ("SVG файлы", "*.svg"),
            ],
            initialfile=default_name,
        )
        
        if path:
            try:
                self._current_fig.savefig(path, dpi=300, bbox_inches='tight')
                messagebox.showinfo("Сохранено", f"График сохранён:\n{path}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить: {e}")


class GPSConstellationDialog(BaseAnalysisDialog):
    """
    Диалог отображения результатов анализа GPS созвездия.
    """
    
    def __init__(self, parent, results, message_callback):
        super().__init__(parent, "Анализ GPS созвездия", "1400x900")
        
        self._results = results
        self._message_callback = message_callback
        self._current_fig = None
        self._current_canvas = None
        self._interactive_zoom = None
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Создаёт виджеты."""
        from backend.analyzers.gps_constellation_analyzer import ConstellationAnalysis
        
        # Главный контейнер
        main = tk.Frame(self.dialog, bg=Theme.BG_PRIMARY)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Верхняя панель
        header = tk.Frame(main, bg=Theme.BG_SECONDARY, height=50)
        header.pack(fill=tk.X, pady=(0, 10))
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="🛰️ Анализ GPS созвездия",
            font=("Segoe UI", 12, "bold"),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY,
        ).pack(side=tk.LEFT, padx=15, pady=12)
        
        # Выбор файла
        frame_select = tk.Frame(header, bg=Theme.BG_SECONDARY)
        frame_select.pack(side=tk.RIGHT, padx=15)
        
        tk.Label(
            frame_select,
            text="Файл:",
            font=("Segoe UI", 9),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY,
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        self._file_var = tk.StringVar()
        self._file_combo = ttk.Combobox(
            frame_select,
            textvariable=self._file_var,
            state='readonly',
            width=30,
        )
        self._file_combo.pack(side=tk.LEFT)
        self._file_combo.bind('<<ComboboxSelected>>', self._on_file_selected)
        
        # Кнопки
        btn_frame = tk.Frame(header, bg=Theme.BG_SECONDARY)
        btn_frame.pack(side=tk.RIGHT, padx=15)
        
        ModernButton(
            btn_frame,
            text="Сбросить зум",
            command=self._reset_zoom,
            width=12,
        ).pack(side=tk.LEFT, padx=2)
        
        ModernButton(
            btn_frame,
            text="Сохранить график",
            command=self._save_plot,
            width=12,
        ).pack(side=tk.LEFT, padx=2)
        
        # Notebook
        self._notebook = ttk.Notebook(main)
        self._notebook.pack(fill=tk.BOTH, expand=True)
        
        # Вкладка с графиком
        self._plot_tab = tk.Frame(self._notebook, bg=Theme.BG_PRIMARY)
        self._notebook.add(self._plot_tab, text="Интервалы видимости")
        
        # Вкладка со статистикой
        self._stats_tab = tk.Frame(self._notebook, bg=Theme.BG_PRIMARY)
        self._notebook.add(self._stats_tab, text="Статистика")
        
        # Заполняем данные
        self._fill_stats_tab()
        self._update_file_list()
    
    def _update_file_list(self):
        """Обновляет список файлов."""
        filenames = [f for f, r in self._results.items() if r.success]
        self._file_combo['values'] = filenames
        if filenames:
            self._file_var.set(filenames[0])
            self._on_file_selected()
    
    def _fill_stats_tab(self):
        """Заполняет вкладку со статистикой."""
        # Treeview с прокруткой
        container = tk.Frame(self._stats_tab, bg=Theme.BG_PRIMARY, padx=10, pady=10)
        container.pack(fill=tk.BOTH, expand=True)
        
        columns = [
            'Файл', 'Длительность', 'Видимые/32', 'Среднее',
            'Топ-1', '%', 'Топ-2', '%',
        ]
        
        tree = ttk.Treeview(
            container,
            columns=columns,
            show='headings',
            height=15,
        )
        
        widths = [200, 80, 80, 70, 60, 50, 60, 50]
        for col, width in zip(columns, widths):
            tree.heading(col, text=col)
            tree.column(col, width=width, minwidth=50)
        
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Заполняем
        for filename, result in self._results.items():
            if not result.success:
                continue
            
            # Топ-5 спутников
            sorted_sats = sorted(
                result.satellite_stats.values(),
                key=lambda x: x.visibility_percent,
                reverse=True,
            )
            
            top1 = sorted_sats[0] if sorted_sats else None
            top2 = sorted_sats[1] if len(sorted_sats) > 1 else None
            
            values = [
                filename,
                f"{result.total_duration / 3600:.1f}ч",
                f"{result.visible_satellites}/32",
                f"{result.mean_satellites:.1f}",
                top1.name if top1 else "-",
                f"{top1.visibility_percent:.0f}%" if top1 else "-",
                top2.name if top2 else "-",
                f"{top2.visibility_percent:.0f}%" if top2 else "-",
            ]
            
            tree.insert('', 'end', values=values)
    
    def _on_file_selected(self, event=None):
        """Обработчик выбора файла."""
        filename = self._file_var.get()
        if filename and filename in self._results:
            self._update_plot(filename)
    
    def _update_plot(self, filename):
        """Строит график интервалов видимости."""
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        from matplotlib.ticker import FuncFormatter, MaxNLocator
        import re
        from datetime import datetime, timedelta
        
        # Очищаем
        for widget in self._plot_tab.winfo_children():
            widget.destroy()
        
        result = self._results[filename]
        
        # Определяем начальное время
        start_datetime = None
        date_match = re.search(r'(\d{8})_?(\d{6})?', filename)
        if date_match:
            date_str = date_match.group(1)
            time_str = date_match.group(2) if date_match.group(2) else "000000"
            try:
                start_datetime = datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")
            except:
                pass
        
        if not start_datetime:
            start_datetime = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Создаём фигуру
        fig, ax = plt.subplots(figsize=(15, 10))
        fig.patch.set_facecolor('white')
        
        # Все 32 спутника
        all_sats = [f'G{i:02d}' for i in range(1, 33)]
        
        # Цветовая карта
        cmap = plt.cm.Greens
        
        # Рисуем интервалы
        for i, sat in enumerate(all_sats):
            y_pos = len(all_sats) - i - 1
            
            intervals = result.intervals.get(sat, [])
            stats = result.satellite_stats.get(sat)
            
            if intervals and stats and stats.is_visible:
                intensity = 0.3 + 0.7 * (stats.visibility_percent / 100)
                color = cmap(intensity)
                
                for iv in intervals:
                    ax.barh(
                        y=y_pos,
                        width=iv.duration,
                        left=iv.start,
                        height=0.7,
                        color=color,
                        edgecolor=cmap(intensity * 0.8),
                        alpha=0.8,
                        linewidth=0.5,
                    )
            else:
                ax.barh(
                    y=y_pos,
                    width=0,
                    height=0.7,
                    color='#CCCCCC',
                    alpha=0.3,
                )
        
        # Настройка осей
        ax.set_yticks(np.arange(len(all_sats)))
        ax.set_yticklabels(all_sats[::-1], fontsize=8)
        
        # Форматирование времени
        def format_datetime(seconds, pos):
            if seconds < 0:
                seconds = 0
            try:
                dt = start_datetime + timedelta(seconds=seconds)
                return dt.strftime("%H:%M:%S")
            except:
                return f"{seconds:.0f}c"
        
        ax.xaxis.set_major_formatter(FuncFormatter(format_datetime))
        ax.xaxis.set_major_locator(MaxNLocator(8))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right', fontsize=8)
        
        ax.set_xlabel('Время наблюдения (ЧЧ:ММ:СС)', fontsize=11)
        ax.set_ylabel('Спутники GPS', fontsize=11)
        ax.set_title(f'Интервалы видимости спутников GPS\n{filename}', fontsize=12, fontweight='bold')
        ax.grid(True, alpha=0.3, axis='x', linestyle='--', linewidth=0.5)
        
        # Информация
        info_text = (
            f"Всего: 32 | Видимых: {result.visible_satellites} | "
            f"Длит.: {result.total_duration / 3600:.1f} ч | "
            f"Среднее: {result.mean_satellites:.1f}"
        )
        
        ax.text(
            0.02, 0.98, info_text,
            transform=ax.transAxes,
            fontsize=10,
            verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8),
        )
        
        plt.tight_layout()
        
        # Встраиваем
        canvas = FigureCanvasTkAgg(fig, self._plot_tab)
        canvas.draw()
        
        # Интерактивный зум
        self._interactive_zoom = InteractiveZoom(fig, [ax])
        
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self._current_fig = fig
        self._current_canvas = canvas
    
    def _reset_zoom(self):
        """Сбрасывает зум."""
        if self._interactive_zoom:
            self._interactive_zoom.reset_all_zooms()
    
    def _save_plot(self):
        """Сохраняет график в файл."""
        if not self._current_fig:
            return
        
        from datetime import datetime
        default_name = f"GPS_{self._file_var.get()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        path = filedialog.asksaveasfilename(
            title="Сохранить график",
            defaultextension=".png",
            filetypes=[
                ("PNG файлы", "*.png"),
                ("PDF файлы", "*.pdf"),
                ("SVG файлы", "*.svg"),
            ],
            initialfile=default_name,
        )
        
        if path:
            try:
                self._current_fig.savefig(path, dpi=300, bbox_inches='tight')
                messagebox.showinfo("Сохранено", f"График сохранён:\n{path}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить: {e}")