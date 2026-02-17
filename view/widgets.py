#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Переиспользуемые виджеты для графического интерфейса.

Содержит базовые UI-компоненты, используемые в главном окне и диалогах:
    - ModernButton: кнопка с ховер-эффектом и поддержкой цветов темы
    - FileEntryWidget: поле ввода с кнопками для выбора файлов
    - CollapsibleFrame: сворачиваемая панель с заголовком
    - InteractiveZoom: интерактивный зум для matplotlib графиков

Архитектурные принципы:
    - Только UI, никакой бизнес-логики
    - Минимальные проверки (только пустые пути, только информационные предупреждения)
    - Все сложные проверки делегируются контроллеру
    - Цвета берутся из темы Theme
"""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional, Dict, List, Any, Tuple, Set
import os
import numpy as np
import weakref

from view.themes import Theme


class ModernButton(tk.Button):
    """
    Современная кнопка с ховер-эффектом и поддержкой цветов темы.
    
    Особенности:
        - При наведении меняет цвет (для акцентных кнопок - более тёмный оттенок)
        - Курсор-рука при наведении
        - Поддержка состояния disabled
        - Плоский дизайн (relief=FLAT)
    
    Акцентные цвета (из Theme.ACCENT_*) при наведении становятся темнее,
    обычные кнопки получают цвет Theme.HOVER.
    """
    
    # Соответствие акцентных цветов их тёмным версиям при наведении
    _DARK_COLORS = {
        Theme.ACCENT_BLUE: "#0b5ed7",
        Theme.ACCENT_GREEN: "#157347",
        Theme.ACCENT_RED: "#bb2d3b",
        Theme.ACCENT_ORANGE: "#e46a0b",
        Theme.ACCENT_PURPLE: "#5e3a9c",
        Theme.ACCENT_CYAN: "#0bacd0",
    }
    
    def __init__(self, master=None, **kwargs):
        """
        Инициализация кнопки.
        
        Args:
            master: Родительский виджет
            **kwargs: Параметры кнопки (переопределяют значения по умолчанию)
        """
        # Параметры по умолчанию
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
        """Обработчик наведения мыши."""
        if self['state'] != 'disabled':
            if self._original_bg in self._DARK_COLORS:
                self['bg'] = self._DARK_COLORS[self._original_bg]
            else:
                self['bg'] = Theme.HOVER
    
    def _on_leave(self, e):
        """Обработчик ухода мыши."""
        if self['state'] != 'disabled':
            self['bg'] = self._original_bg
            self['fg'] = self._original_fg


class FileEntryWidget(tk.Frame):
    """
    Виджет для выбора файла с полем ввода и кнопками.
    
    Содержит:
        - Метку с названием поля
        - Поле ввода (Entry) для отображения пути
        - Кнопку "📁" для открытия диалога выбора файла
        - Кнопку "📄" для открытия файла в программе по умолчанию
        - Кнопку "🔗" для сшивки JPS файлов (только для JPS)
    
    Архитектурные принципы:
        - НЕ проверяет существование файлов - это ответственность контроллера
        - Только проверка на пустой путь и информационные предупреждения
        - Все действия делегируются через callback'и
    
    Args:
        master: Родительский виджет
        label_text: Текст метки (например, "Ровер (JPS)")
        browse_callback: Функция, вызываемая при нажатии кнопки обзора.
                        Должна возвращать выбранный путь.
        open_callback: Функция контроллера для открытия файла.
                      Принимает путь к файлу.
        stitch_callback: Функция контроллера для сшивки (только для JPS).
                        Принимает ключ файла (rover/base1/base2).
        expected_extension: Ожидаемое расширение файла для предупреждений.
        file_key: Ключ файла (rover, base1, sr2nav, ...) для callback'ов.
    """
    
    def __init__(
        self,
        master,
        label_text: str,
        browse_callback: Callable[[], str],
        open_callback: Callable[[str], None],
        stitch_callback: Optional[Callable[[str], None]] = None,
        expected_extension: Optional[str] = None,
        file_key: Optional[str] = None,
        **kwargs
    ):
        super().__init__(master, bg=Theme.BG_PRIMARY, **kwargs)
        
        self._browse_callback = browse_callback
        self._open_callback = open_callback
        self._stitch_callback = stitch_callback
        self._expected_extension = expected_extension
        self._label_text = label_text
        self._file_key = file_key
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Создаёт все дочерние виджеты."""
        # Контейнер для выравнивания
        container = tk.Frame(self, bg=Theme.BG_PRIMARY)
        container.pack(fill=tk.X, padx=3, pady=2)
        
        # Метка
        label = tk.Label(
            container,
            text=self._label_text + ":",
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
        
        # Контейнер для кнопок
        btn_frame = tk.Frame(container, bg=Theme.BG_PRIMARY)
        btn_frame.pack(side=tk.RIGHT)
        
        # Кнопка сшивки (только для JPS файлов)
        if self._stitch_callback:
            btn_stitch = ModernButton(
                btn_frame,
                text="🔗",
                width=3,
                bg=Theme.BG_SECONDARY,
                command=self._on_stitch,
                font=("Segoe UI", 11),
            )
            btn_stitch.pack(side=tk.RIGHT, padx=(3, 0))
        
        # Кнопка открытия файла
        btn_open = ModernButton(
            btn_frame,
            text="📄",
            width=3,
            bg=Theme.BG_SECONDARY,
            command=self._on_open,
            font=("Segoe UI", 11),
        )
        btn_open.pack(side=tk.RIGHT, padx=(3, 0))
        
        # Кнопка обзора
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
        """Обработчик кнопки обзора - вызывает callback и обновляет поле."""
        path = self._browse_callback()
        if path:
            self._entry.delete(0, tk.END)
            self._entry.insert(0, path)
    
    def _on_open(self):
        """
        Обработчик кнопки открытия.
        
        Проверяет только:
            1. Не пустой ли путь
            2. Информационное предупреждение о расширении (по желанию пользователя)
        
        Реальную проверку существования файла выполняет контроллер.
        """
        path = self.get_value()
        
        if not path or not path.strip():
            self._show_error(
                "Ошибка", 
                f"Путь к файлу не указан\n{self._label_text}"
            )
            return
        
        # Информационное предупреждение о расширении
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
        
        # Делегируем контроллеру
        self._open_callback(path)
    
    def _on_stitch(self):
        """Обработчик кнопки сшивки - вызывает callback контроллера."""
        if self._stitch_callback:
            self._stitch_callback(self._file_key)
        else:
            print(f"Warning: Stitch callback called for {self._label_text} but not provided.")
    
    def _show_error(self, title: str, message: str):
        """Показывает сообщение об ошибке."""
        messagebox.showerror(title, message, parent=self)
    
    def _ask_yes_no(self, title: str, message: str) -> bool:
        """Запрашивает подтверждение у пользователя."""
        return messagebox.askyesno(title, message, parent=self)
    
    def get_value(self) -> str:
        """Возвращает текущее значение поля ввода."""
        return self._entry.get().strip()
    
    def set_value(self, value: str) -> None:
        """Устанавливает значение поля ввода."""
        self._entry.delete(0, tk.END)
        self._entry.insert(0, value)


class CollapsibleFrame(tk.Frame):
    """
    Сворачиваемая панель с заголовком.
    
    Позволяет экономить место в интерфейсе, скрывая содержимое панели.
    Состоит из:
        - Заголовка с кнопкой сворачивания (▼/▶)
        - Области содержимого (content), которую можно скрыть/показать
    
    Attributes:
        content: Фрейм для размещения дочерних виджетов
        _is_expanded: Текущее состояние (True - развёрнуто)
    """
    
    def __init__(self, master, title="", **kwargs):
        """
        Инициализация сворачиваемой панели.
        
        Args:
            master: Родительский виджет
            title: Заголовок панели
            **kwargs: Дополнительные параметры для Frame
        """
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
        
        # Заголовок
        self._title_label = tk.Label(
            self._header,
            text=title,
            font=("Segoe UI", 12, "bold"),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY,
        )
        self._title_label.pack(side=tk.LEFT, padx=8, pady=8)
        
        # Область содержимого
        self.content = tk.Frame(self, bg=Theme.BG_PRIMARY)
        self.content.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
    
    def _toggle(self):
        """Переключает состояние панели (свернуто/развернуто)."""
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
    
    Предоставляет следующие возможности:
        - Выделение области мышью для увеличения
        - Зум колёсиком мыши
        - Панорама средней кнопкой мыши
        - Двойной клик для сброса зума
        - Сброс всех осей через метод reset_all_zooms
    
    Особенности реализации:
        - Поддержка как списка осей, так и numpy массива осей
        - Явная очистка ресурсов через метод cleanup()
        - Хранение оригинальных лимитов для сброса
        - Автоматическое отключение обработчиков при очистке
    
    Важно:
        Всегда вызывать cleanup() при закрытии окна для предотвращения
        утечек памяти и висящих обработчиков событий.
    """
    
    def __init__(self, fig, axes):
        """
        Инициализация интерактивного зума.
        
        Args:
            fig: Фигура matplotlib
            axes: Ось или список осей (поддерживает вложенные списки и numpy массивы)
        """
        self.fig = fig
        self._is_cleaned_up = False
        self._connections = []  # ID соединений для отключения
        
        # Универсальное преобразование осей в плоский список
        self.axes = self._flatten_axes(axes)
        
        # Сохраняем оригинальные лимиты для сброса
        self._original_xlim = {}
        self._original_ylim = {}
        for ax in self.axes:
            self._original_xlim[ax] = ax.get_xlim()
            self._original_ylim[ax] = ax.get_ylim()
        
        self._selectors = []  # Селекторы для выделения областей
        self._pan_start = None  # Начальная точка панорамы
        self._pan_ax = None  # Ось, в которой выполняется панорама
        
        self._connect()
    
    def _flatten_axes(self, axes):
        """
        Преобразует входные оси в плоский список.
        
        Поддерживает:
            - None → []
            - Одиночную ось → [ax]
            - Список/кортеж → рекурсивно расплющивает
            - numpy массив → flatten().tolist()
        
        Args:
            axes: Входные оси в любом формате
            
        Returns:
            Плоский список осей matplotlib
        """
        if axes is None:
            return []
        
        if isinstance(axes, (list, tuple)):
            result = []
            for ax in axes:
                if isinstance(ax, (list, tuple, np.ndarray)):
                    result.extend(self._flatten_axes(ax))
                else:
                    result.append(ax)
            return result
        
        if isinstance(axes, np.ndarray):
            return axes.flatten().tolist()
        
        return [axes]
    
    def _connect(self):
        """Подключает все обработчики событий matplotlib."""
        from matplotlib.widgets import RectangleSelector
        
        # Селектор для каждой оси
        for ax in self.axes:
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
        
        # Глобальные обработчики
        cid1 = self.fig.canvas.mpl_connect('button_press_event', self._on_mouse_press)
        cid2 = self.fig.canvas.mpl_connect('button_release_event', self._on_mouse_release)
        cid3 = self.fig.canvas.mpl_connect('motion_notify_event', self._on_mouse_motion)
        cid4 = self.fig.canvas.mpl_connect('scroll_event', self._on_scroll)
        cid5 = self.fig.canvas.mpl_connect('button_press_event', self._on_double_click)
        
        self._connections = [cid1, cid2, cid3, cid4, cid5]
    
    def _make_on_select(self, ax):
        """
        Создаёт функцию обработки выделения для конкретной оси.
        
        Args:
            ax: Ось, для которой создаётся обработчик
            
        Returns:
            Функция обработки выделения
        """
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
        """
        Обработчик зума колёсиком мыши.
        
        Приближение: колесо вверх (event.button == 'up')
        Отдаление: колесо вниз (event.button == 'down')
        """
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
        """Обрабатывает двойной клик для сброса зума на текущей оси."""
        if event.dblclick and event.inaxes:
            ax = event.inaxes
            if ax in self._original_xlim:
                ax.set_xlim(self._original_xlim[ax])
                ax.set_ylim(self._original_ylim[ax])
                self.fig.canvas.draw_idle()
    
    def reset_all_zooms(self):
        """Сбрасывает зум на всех осях к оригинальным лимитам."""
        for ax in self.axes:
            if ax in self._original_xlim:
                ax.set_xlim(self._original_xlim[ax])
                ax.set_ylim(self._original_ylim[ax])
        self.fig.canvas.draw_idle()
    
    def cleanup(self):
        """
        Явная очистка ресурсов.
        
        Обязательно вызывать при закрытии окна для предотвращения:
            - Утечек памяти
            - Висящих обработчиков событий
            - Циклических ссылок
        
        Метод безопасен для многократного вызова.
        """
        if self._is_cleaned_up:
            return
        
        try:
            # Отключаем все соединения с canvas
            if hasattr(self, 'fig') and self.fig and hasattr(self.fig, 'canvas'):
                for cid in self._connections:
                    try:
                        self.fig.canvas.mpl_disconnect(cid)
                    except Exception:
                        pass
            
            # Деактивируем селекторы
            for selector in self._selectors:
                try:
                    selector.set_active(False)
                    selector.set_visible(False)
                except Exception:
                    pass
            
            # Очищаем все ссылки
            self._selectors.clear()
            self._connections.clear()
            self._original_xlim.clear()
            self._original_ylim.clear()
            
            self._is_cleaned_up = True
            
        except Exception as e:
            print(f"Ошибка при очистке InteractiveZoom: {e}")
    
    def __del__(self):
        """Резервная очистка при удалении (на случай забытого cleanup)."""
        try:
            self.cleanup()
        except Exception:
            pass