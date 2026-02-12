#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЧИСТОЕ ПРЕДСТАВЛЕНИЕ - Виджеты для графического интерфейса.
НИКАКИХ ПРОВЕРОК СУЩЕСТВОВАНИЯ ФАЙЛОВ - только UI!
"""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional, Dict, List, Any, Tuple
import os
import numpy as np

from view.themes import Theme


class ModernButton(tk.Button):
    """Современная кнопка с ховер-эффектом."""
    
    def __init__(self, master=None, **kwargs):
        default_kwargs = {
            'font': ("Segoe UI", 10),
            'relief': tk.FLAT,
            'cursor': 'hand2',
            'padx': 14,
            'pady': 6,
            'bd': 1,
            'bg': Theme.BG_SECONDARY,
            'fg': Theme.FG_PRIMARY,
            'activebackground': Theme.HOVER,
            'activeforeground': Theme.FG_PRIMARY,
            'highlightthickness': 0,
        }
        
        default_kwargs.update(kwargs)
        super().__init__(master, **default_kwargs)
        
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
    ЧИСТОЕ ПРЕДСТАВЛЕНИЕ - Виджет для выбора файла.
    ТОЛЬКО UI, НИКАКИХ ПРОВЕРОК СУЩЕСТВОВАНИЯ ФАЙЛОВ!
    """
    
    def __init__(
        self,
        master,
        label_text: str,
        browse_callback: Callable,
        open_callback: Callable,
        stitch_callback: Optional[Callable] = None,
        expected_extension: Optional[str] = None,
        file_key: Optional[str] = None,  # ИСПРАВЛЕНО: добавляем ключ файла
        **kwargs
    ):
        super().__init__(master, bg=Theme.BG_PRIMARY, **kwargs)
        
        self._browse_callback = browse_callback
        self._open_callback = open_callback
        self._stitch_callback = stitch_callback
        self._expected_extension = expected_extension
        self._label_text = label_text
        self._file_key = file_key  # ИСПРАВЛЕНО: сохраняем ключ
        
        # Контейнер
        container = tk.Frame(self, bg=Theme.BG_PRIMARY)
        container.pack(fill=tk.X, padx=3, pady=2)
        
        # Метка
        label = tk.Label(
            container,
            text=label_text + ":",
            font=("Segoe UI", 10),
            bg=Theme.BG_PRIMARY,
            fg=Theme.FG_PRIMARY,
            anchor="w",
            width=16,
        )
        label.pack(side=tk.LEFT)
        
        # Поле ввода
        self._entry = tk.Entry(
            container,
            font=("Consolas", 10),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY,
            relief=tk.SOLID,
            bd=1,
            highlightcolor=Theme.ACCENT_BLUE,
            highlightthickness=1,
        )
        self._entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        
        # Кнопки
        btn_frame = tk.Frame(container, bg=Theme.BG_PRIMARY)
        btn_frame.pack(side=tk.RIGHT)
        
        # Сшивка (только для JPS)
        if stitch_callback:
            btn_stitch = ModernButton(
                btn_frame,
                text="🔗",
                width=3,
                bg=Theme.BG_SECONDARY,
                command=self._on_stitch,
                font=("Segoe UI", 11),
            )
            btn_stitch.pack(side=tk.RIGHT, padx=(3, 0))
        
        # Открыть
        btn_open = ModernButton(
            btn_frame,
            text="📄",
            width=3,
            bg=Theme.BG_SECONDARY,
            command=self._on_open,
            font=("Segoe UI", 11),
        )
        btn_open.pack(side=tk.RIGHT, padx=(3, 0))
        
        # Обзор
        btn_browse = ModernButton(
            btn_frame,
            text="📁",
            width=3,
            bg=Theme.BG_SECONDARY,
            command=self._on_browse,
            font=("Segoe UI", 11),
        )
        btn_browse.pack(side=tk.RIGHT, padx=(3, 0))
    
    def _on_browse(self):
        """Обработчик кнопки обзора."""
        path = self._browse_callback()
        if path:
            self._entry.delete(0, tk.END)
            self._entry.insert(0, path)
    
    def _on_open(self):
        """
        Обработчик кнопки открытия.
        ТОЛЬКО ПРОВЕРКА НА ПУСТОЙ ПУТЬ!
        """
        path = self.get_value()
        
        if not path or not path.strip():
            self._show_error(
                "Ошибка", 
                f"Путь к файлу не указан\n{self._label_text}"
            )
            return
        
        # Предупреждение о расширении (только информационное)
        if self._expected_extension:
            ext = os.path.splitext(path)[1].lower()
            if ext != self._expected_extension.lower():
                result = self._ask_yes_no(
                    "Предупреждение",
                    f"Файл должен иметь расширение {self._expected_extension}\n"
                    f"Текущее расширение: {ext}\n\n"
                    f"Продолжить открытие?"
                )
                if not result:
                    return
        
        # Контроллер проверит существование файла
        self._open_callback(path)
    
    def _on_stitch(self):
        """Обработчик кнопки сшивки."""
        if self._stitch_callback:
            # ИСПРАВЛЕНО: передаем ключ файла в колбэк
            self._stitch_callback(self._file_key)
    
    def _show_error(self, title: str, message: str):
        """Показывает сообщение об ошибке."""
        messagebox.showerror(title, message, parent=self)
    
    def _ask_yes_no(self, title: str, message: str) -> bool:
        """Запрашивает подтверждение у пользователя."""
        return messagebox.askyesno(title, message, parent=self)
    
    def get_value(self) -> str:
        """Возвращает значение поля."""
        return self._entry.get().strip()
    
    def set_value(self, value: str) -> None:
        """Устанавливает значение поля."""
        self._entry.delete(0, tk.END)
        self._entry.insert(0, value)


class CollapsibleFrame(tk.Frame):
    """Сворачиваемая панель с заголовком."""
    
    def __init__(self, master, title="", **kwargs):
        kwargs.pop('bg', None)
        super().__init__(master, bg=Theme.BG_PRIMARY, **kwargs)
        
        self._is_expanded = True
        
        self._header = tk.Frame(
            self,
            bg=Theme.BG_SECONDARY,
            relief=tk.FLAT,
            bd=1,
        )
        self._header.pack(fill=tk.X, pady=(0, 1))
        
        self._toggle_btn = tk.Button(
            self._header,
            text="▼",
            font=("Segoe UI", 10, "bold"),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_SECONDARY,
            relief=tk.FLAT,
            cursor='hand2',
            width=2,
            bd=0,
            command=self._toggle,
        )
        self._toggle_btn.pack(side=tk.LEFT, padx=(8, 0))
        
        self._title_label = tk.Label(
            self._header,
            text=title,
            font=("Segoe UI", 12, "bold"),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY,
        )
        self._title_label.pack(side=tk.LEFT, padx=8, pady=8)
        
        self.content = tk.Frame(self, bg=Theme.BG_PRIMARY)
        self.content.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
    
    def _toggle(self):
        if self._is_expanded:
            self.content.pack_forget()
            self._toggle_btn.config(text="▶")
            self._is_expanded = False
        else:
            self.content.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
            self._toggle_btn.config(text="▼")
            self._is_expanded = True


class InteractiveZoom:
    """
    Интерактивный зум для matplotlib графиков.
    ИСПРАВЛЕНО: корректная работа со списками и массивами numpy
    """
    
    def __init__(self, fig, axes):
        self.fig = fig
        
        # УНИВЕРСАЛЬНОЕ ПРЕОБРАЗОВАНИЕ: работает и со списком, и с numpy array
        if axes is None:
            self.axes = []
        elif isinstance(axes, (list, tuple)):
            # Расплющиваем вложенные списки/массивы
            self.axes = []
            for ax in axes:
                if isinstance(ax, (list, tuple, np.ndarray)):
                    self.axes.extend(ax)
                else:
                    self.axes.append(ax)
        elif isinstance(axes, np.ndarray):
            self.axes = axes.flatten().tolist()
        else:
            self.axes = [axes]
        
        self._original_xlim = {}
        self._original_ylim = {}
        self._selectors = []
        self._pan_start = None
        self._pan_ax = None
        
        # Сохраняем оригинальные лимиты
        for ax in self.axes:
            self._original_xlim[ax] = ax.get_xlim()
            self._original_ylim[ax] = ax.get_ylim()
        
        self._connect()
    
    def _connect(self):
        """Подключает все обработчики событий."""
        from matplotlib.widgets import RectangleSelector
        
        for ax in self.axes:
            # Селектор для выделения области
            selector = RectangleSelector(
                ax,
                self._make_on_select(ax),
                useblit=True,
                button=1,
                spancoords='data',
                interactive=True,
                props=dict(facecolor='red', alpha=0.3, edgecolor='red'),
            )
            self._selectors.append(selector)
        
        # Подключаем глобальные обработчики
        self.fig.canvas.mpl_connect('button_press_event', self._on_mouse_press)
        self.fig.canvas.mpl_connect('button_release_event', self._on_mouse_release)
        self.fig.canvas.mpl_connect('motion_notify_event', self._on_mouse_motion)
        self.fig.canvas.mpl_connect('scroll_event', self._on_scroll)
        self.fig.canvas.mpl_connect('button_press_event', self._on_double_click)
    
    def _make_on_select(self, ax):
        """Создает функцию обработки выделения для конкретной оси."""
        def on_select(eclick, erelease):
            x1, y1 = eclick.xdata, eclick.ydata
            x2, y2 = erelease.xdata, erelease.ydata
            
            if x1 is not None and x2 is not None and x1 != x2:
                ax.set_xlim(min(x1, x2), max(x1, x2))
                ax.set_ylim(min(y1, y2), max(y1, y2))
                self.fig.canvas.draw_idle()
            
            # Делаем селектор невидимым, но оставляем активным
            for selector in self._selectors:
                if selector.ax == ax:
                    selector.set_visible(False)
            
            self.fig.canvas.draw_idle()
        
        return on_select
    
    def _on_scroll(self, event):
        """Зум колесиком мыши."""
        ax = event.inaxes
        if ax is None:
            return
        
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        xdata = event.xdata
        ydata = event.ydata
        
        if xdata is None or ydata is None:
            return
        
        scale_factor = 0.9 if event.button == 'up' else 1.1
        
        new_xlim = (xdata - (xdata - xlim[0]) * scale_factor,
                   xdata + (xlim[1] - xdata) * scale_factor)
        new_ylim = (ydata - (ydata - ylim[0]) * scale_factor,
                   ydata + (ylim[1] - ydata) * scale_factor)
        
        ax.set_xlim(new_xlim)
        ax.set_ylim(new_ylim)
        self.fig.canvas.draw_idle()
    
    def _on_mouse_press(self, event):
        """Начало панорамы (средняя кнопка мыши)."""
        if event.button == 2 and event.inaxes:
            self._pan_start = (event.xdata, event.ydata)
            self._pan_ax = event.inaxes
    
    def _on_mouse_release(self, event):
        """Конец панорамы."""
        if event.button == 2:
            self._pan_start = None
            self._pan_ax = None
    
    def _on_mouse_motion(self, event):
        """Перемещение при панораме."""
        if self._pan_start is None or self._pan_ax is None or event.inaxes != self._pan_ax:
            return
        
        if event.xdata is None or event.ydata is None:
            return
        
        dx = self._pan_start[0] - event.xdata
        dy = self._pan_start[1] - event.ydata
        
        xlim = self._pan_ax.get_xlim()
        ylim = self._pan_ax.get_ylim()
        
        self._pan_ax.set_xlim(xlim[0] + dx, xlim[1] + dx)
        self._pan_ax.set_ylim(ylim[0] + dy, ylim[1] + dy)
        
        self.fig.canvas.draw_idle()
        self._pan_start = (event.xdata, event.ydata)
    
    def _on_double_click(self, event):
        """Обрабатывает двойной клик для сброса зума."""
        if event.dblclick and event.inaxes:
            ax = event.inaxes
            if ax in self._original_xlim:
                ax.set_xlim(self._original_xlim[ax])
                ax.set_ylim(self._original_ylim[ax])
                self.fig.canvas.draw_idle()
    
    def reset_all_zooms(self):
        """Сбрасывает зум на всех осях."""
        for ax in self.axes:
            if ax in self._original_xlim:
                ax.set_xlim(self._original_xlim[ax])
                ax.set_ylim(self._original_ylim[ax])
        self.fig.canvas.draw_idle()
    
    def __del__(self):
        """Очистка селекторов при удалении."""
        for selector in self._selectors:
            try:
                selector.set_active(False)
                selector.set_visible(False)
            except:
                pass