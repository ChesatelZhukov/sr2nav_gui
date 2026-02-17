#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Диалоговые окна приложения.

Содержит модальные диалоги для взаимодействия с пользователем:
    - GPSExclusionDialog: выбор исключаемых спутников GPS
    - TransformFileDialog: выбор файлов для трансформации в TBL

Архитектурные принципы:
    - Только UI, никакой бизнес-логики
    - Все операции делегируются контроллеру через callback'и
    - Состояние UI (последние пути) сохраняется через UIPersistence
    - Диалоги модальные (блокируют родительское окно)
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Callable, Optional, Dict, List, Any, Set
import os

from view.themes import Theme
from view.widgets import ModernButton
from view.persistence import UIPersistence


class GPSExclusionDialog:
    """
    Диалог выбора спутников GPS для исключения из обработки.
    
    Позволяет пользователю отметить спутники, которые следует исключить.
    UI отображает все 32 спутника (G01-G32) с чекбоксами:
        - Чекбокс отмечен = спутник ВКЛЮЧЁН (не исключается)
        - Чекбокс снят = спутник ИСКЛЮЧЁН
    
    При сохранении вызывает callback контроллера с множеством исключённых спутников.
    
    Важное архитектурное решение:
        Диалог получает начальное состояние (initial_excluded) при создании,
        но не хранит его после закрытия. Вся логика сохранения делегируется контроллеру.
    
    Attributes:
        ALL_SATELLITES: Список всех GPS спутников G01...G32
        parent: Родительское окно
        initial_excluded: Начальное множество исключённых спутников
        on_save_callback: Функция контроллера для сохранения
        _vars: Словарь переменных чекбоксов {sat: BooleanVar}
        result: Результат выбора (множество исключённых) или None
    """
    
    ALL_SATELLITES = [f"G{i:02d}" for i in range(1, 33)]
    
    def __init__(
        self, 
        parent: tk.Tk, 
        initial_excluded: Set[str],
        on_save_callback: Callable[[Set[str]], None]
    ):
        """
        Инициализация диалога исключения спутников.
        
        Args:
            parent: Родительское окно (для центрирования и модальности)
            initial_excluded: Начальное множество исключённых спутников
                             (для инициализации состояния чекбоксов)
            on_save_callback: Функция контроллера для сохранения результата
        """
        self.parent = parent
        self.initial_excluded = initial_excluded.copy() if initial_excluded else set()
        self.on_save_callback = on_save_callback
        self._vars: Dict[str, tk.BooleanVar] = {}
        self.result: Optional[Set[str]] = None
        
        self._create_dialog()
    
    def _create_dialog(self):
        """Создаёт модальное диалоговое окно."""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Исключение спутников GPS")
        self.dialog.geometry("550x600")
        self.dialog.resizable(False, False)
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        self.dialog.configure(bg=Theme.BG_PRIMARY)
        
        # Центрирование относительно родителя
        self.dialog.update_idletasks()
        x = self.parent.winfo_rootx() + (self.parent.winfo_width() - 550) // 2
        y = self.parent.winfo_rooty() + (self.parent.winfo_height() - 600) // 2
        self.dialog.geometry(f"+{x}+{y}")
        
        self._create_widgets()
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_cancel)
    
    def _create_widgets(self):
        """Создаёт виджеты диалога."""
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
        
        # Фрейм с прокруткой для списка спутников
        container = tk.Frame(main, bg=Theme.BG_PRIMARY)
        container.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(
            container, 
            bg=Theme.BG_PRIMARY, 
            highlightthickness=0
        )
        scrollbar = tk.Scrollbar(
            container, 
            orient="vertical", 
            command=canvas.yview
        )
        scrollable = tk.Frame(canvas, bg=Theme.BG_PRIMARY)
        
        scrollable.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Создаём чекбоксы - по 5 в ряд
        for i, sat in enumerate(self.ALL_SATELLITES):
            row = i // 5
            col = i % 5
            
            if col == 0:
                row_frame = tk.Frame(scrollable, bg=Theme.BG_PRIMARY)
                row_frame.grid(row=row, column=0, sticky="w", pady=2)
            
            # Логика: True = включён (не исключён), False = исключён
            var = tk.BooleanVar(value=sat not in self.initial_excluded)
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
        
        # Кнопки управления
        btn_frame = tk.Frame(main, bg=Theme.BG_PRIMARY)
        btn_frame.pack(fill=tk.X, pady=(15, 0))
        
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
    
    def _select_all(self):
        """Выбирает все спутники (все включены, ничего не исключено)."""
        for var in self._vars.values():
            var.set(True)
    
    def _deselect_all(self):
        """Сбрасывает все спутники (все исключены)."""
        for var in self._vars.values():
            var.set(False)
    
    def _on_save(self):
        """
        Сохраняет выбор и вызывает callback контроллера.
        
        Преобразует состояние чекбоксов в множество исключённых спутников
        (те, у которых галочка снята) и передаёт контроллеру.
        """
        excluded = {
            sat for sat, var in self._vars.items()
            if not var.get()  # Если галочка снята - исключаем
        }
        
        self.result = excluded
        self.on_save_callback(excluded)  # Вызов контроллера!
        self.dialog.destroy()
    
    def _on_cancel(self):
        """Отменяет выбор и закрывает диалог без сохранения."""
        self.result = None
        self.dialog.destroy()
    
    def show(self) -> Optional[Set[str]]:
        """
        Показывает диалог и ожидает его закрытия.
        
        Returns:
            Множество исключённых спутников или None, если диалог закрыт без сохранения
        """
        self.parent.wait_window(self.dialog)
        return self.result


class TransformFileDialog:
    """
    Диалог выбора файлов для трансформации в формат TBL.
    
    Позволяет пользователю выбрать папку с исходными файлами,
    отметить нужные файлы и запустить трансформацию.
    
    Особенности:
        - Сканирование папки происходит только после явного выбора
        - Отображает информацию о создаваемой папке "tbl"
        - Показывает размер файлов
        - Сохраняет последнюю выбранную папку через UIPersistence
    
    Архитектура:
        Диалог только собирает выбор пользователя и вызывает
        callback контроллера с выбранными файлами и путём.
    """
    
    # Типы файлов для трансформации с описаниями для UI
    FILE_TYPES = [
        ("Phase_L1.VEL", "ROVER_KIN", "📊 Фаза L1"),
        ("Phase_IO.VEL", "ROVER_KIN", "📊 Фаза IO"),
        ("PhaseIOS.VEL", "ROVER_KIN", "📊 Фаза IOS"),
        ("PhaseL1S.VEL", "ROVER_KIN", "📊 Фаза L1S"),
        ("Base_Std.QC", "BASE_STD", "🏠 Стандарт базы"),
        ("Rover_Std.QC", "ROVER_STD", "🚙 Стандарт ровера"),
    ]
    
    def __init__(
        self, 
        parent, 
        initial_dir: str,
        on_transform_callback: Callable[[List[str], str], None]
    ):
        """
        Инициализация диалога трансформации.
        
        Args:
            parent: Родительское окно
            initial_dir: Начальная директория для поиска файлов
            on_transform_callback: Функция контроллера для запуска трансформации
        """
        self.parent = parent
        self.current_dir = Path(initial_dir)
        self.on_transform_callback = on_transform_callback
        
        self._vars: Dict[str, tk.BooleanVar] = {}
        self._checkboxes: Dict[str, tk.Checkbutton] = {}
        self._file_paths: Dict[str, Path] = {}
        
        self._create_dialog()
        # Важно: НЕ сканируем при создании, ждём явного выбора папки
    
    def _create_dialog(self):
        """Создаёт модальное диалоговое окно."""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Трансформация в TBL")
        self.dialog.geometry("750x650")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        self.dialog.configure(bg=Theme.BG_PRIMARY)
        
        self.dialog.update_idletasks()
        x = self.parent.winfo_rootx() + 100
        y = self.parent.winfo_rooty() + 100
        self.dialog.geometry(f"+{x}+{y}")
        
        self._create_widgets()
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _create_widgets(self):
        """Создаёт все виджеты диалога."""
        main = tk.Frame(self.dialog, bg=Theme.BG_PRIMARY, padx=20, pady=20)
        main.pack(fill=tk.BOTH, expand=True)
        
        # Заголовок
        tk.Label(
            main,
            text="🔄 Трансформация файлов в формат TBL",
            font=("Segoe UI", 14, "bold"),
            bg=Theme.BG_PRIMARY,
            fg=Theme.FG_PRIMARY,
        ).pack(anchor="w", pady=(0, 10))
        
        # ============ СЕКЦИЯ ВЫБОРА ПАПКИ ============
        self._create_folder_selection(main)
        
        # Разделитель
        tk.Frame(main, height=1, bg=Theme.BORDER).pack(fill=tk.X, pady=(0, 15))
        
        # ============ ЗАГОЛОВОК СПИСКА ФАЙЛОВ ============
        self._create_file_list_header(main)
        
        # ============ СПИСОК ФАЙЛОВ С ПРОКРУТКОЙ ============
        self._create_file_list(main)
        
        # ============ КНОПКИ ДЕЙСТВИЙ ============
        self._create_action_buttons(main)
    
    def _create_folder_selection(self, parent):
        """Создаёт секцию выбора папки."""
        source_frame = tk.Frame(parent, bg=Theme.BG_PRIMARY)
        source_frame.pack(fill=tk.X, pady=(0, 15))
        
        tk.Label(
            source_frame,
            text="📂 Выберите папку с файлами:",
            font=("Segoe UI", 10, "bold"),
            bg=Theme.BG_PRIMARY,
            fg=Theme.FG_PRIMARY,
        ).pack(anchor="w")
        
        dir_container = tk.Frame(source_frame, bg=Theme.BG_PRIMARY)
        dir_container.pack(fill=tk.X, pady=(5, 0))
        
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
        
        ModernButton(
            dir_container,
            text="📂 Выбрать папку...",
            command=self._on_browse_source_dir,
            width=15,
            font=("Segoe UI", 10),
            bg=Theme.ACCENT_BLUE,
            fg="white",
        ).pack(side=tk.RIGHT)
        
        # Информация о создаваемой папке tbl
        self._tbl_info_label = tk.Label(
            source_frame,
            text="",
            font=("Consolas", 9),
            bg=Theme.BG_PRIMARY,
            fg=Theme.ACCENT_GREEN,
            anchor="w",
        )
        self._tbl_info_label.pack(anchor="w", pady=(5, 0))
    
    def _create_file_list_header(self, parent):
        """Создаёт заголовок списка файлов с счётчиком и кнопками."""
        list_header = tk.Frame(parent, bg=Theme.BG_PRIMARY)
        list_header.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(
            list_header,
            text="📋 Доступные файлы:",
            font=("Segoe UI", 11, "bold"),
            bg=Theme.BG_PRIMARY,
            fg=Theme.FG_PRIMARY,
        ).pack(side=tk.LEFT)
        
        # Счетчик найденных файлов
        self._file_count_label = tk.Label(
            list_header,
            text="(выберите папку)",
            font=("Segoe UI", 10),
            bg=Theme.BG_PRIMARY,
            fg=Theme.FG_SECONDARY,
        )
        self._file_count_label.pack(side=tk.LEFT, padx=(10, 0))
        
        # Кнопки управления списком
        btn_frame = tk.Frame(list_header, bg=Theme.BG_PRIMARY)
        btn_frame.pack(side=tk.RIGHT)
        
        ModernButton(
            btn_frame,
            text="✓ Все",
            command=self._select_all,
            width=5,
            font=("Segoe UI", 9),
            padx=8,
            pady=2,
        ).pack(side=tk.LEFT, padx=2)
        
        ModernButton(
            btn_frame,
            text="✗ Сброс",
            command=self._deselect_all,
            width=5,
            font=("Segoe UI", 9),
            padx=8,
            pady=2,
        ).pack(side=tk.LEFT, padx=2)
    
    def _create_file_list(self, parent):
        """Создаёт прокручиваемый список файлов."""
        container = tk.Frame(parent, bg=Theme.BG_PRIMARY)
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
        self.scrollable = tk.Frame(canvas, bg=Theme.BG_PRIMARY)
        
        self.scrollable.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Текст-заглушка пока папка не выбрана
        self._placeholder = tk.Label(
            self.scrollable,
            text="👆 Выберите папку для отображения файлов",
            font=("Segoe UI", 12),
            bg=Theme.BG_PRIMARY,
            fg=Theme.FG_SECONDARY,
        )
        self._placeholder.pack(expand=True, pady=50)
    
    def _create_action_buttons(self, parent):
        """Создаёт кнопки действий внизу диалога."""
        btn_frame_bottom = tk.Frame(parent, bg=Theme.BG_PRIMARY)
        btn_frame_bottom.pack(fill=tk.X, pady=(20, 0))
        
        ModernButton(
            btn_frame_bottom,
            text="🔄 Обновить список",
            command=self._refresh_file_list,
            width=15,
            font=("Segoe UI", 10),
            bg=Theme.ACCENT_BLUE,
            fg="white",
        ).pack(side="left", padx=(0, 5))
        
        ModernButton(
            btn_frame_bottom,
            text="❌ Закрыть",
            command=self._on_close,
            width=10,
            font=("Segoe UI", 10),
        ).pack(side="right", padx=(5, 0))
        
        ModernButton(
            btn_frame_bottom,
            text="🔄 Трансформировать",
            bg=Theme.ACCENT_GREEN,
            fg="white",
            command=self._on_transform,
            width=18,
            font=("Segoe UI", 10, "bold"),
            padx=16,
            pady=6,
        ).pack(side="right", padx=(0, 5))
    
    def _on_browse_source_dir(self):
        """
        Открывает диалог выбора папки и сразу сканирует её.
        
        Логика:
            1. Запоминаем текущее окно как модальное
            2. Открываем диалог выбора папки
            3. Если папка выбрана - обновляем путь и сканируем
        """
        initial_dir = str(self.current_dir)
        if not os.path.exists(initial_dir):
            initial_dir = UIPersistence.get_last_dir()
        
        # Временно отпускаем захват для диалога
        self.dialog.grab_release()
        
        directory = filedialog.askdirectory(
            title="Выберите папку с файлами",
            initialdir=initial_dir,
            parent=self.dialog
        )
        
        # Восстанавливаем захват
        self.dialog.grab_set()
        
        if directory:
            self.current_dir = Path(directory)
            self._dir_var.set(str(self.current_dir))
            self._update_tbl_info()
            self._refresh_file_list()  # Сканируем ТОЛЬКО после выбора
            UIPersistence.set_last_dir(directory)
    
    def _update_tbl_info(self):
        """Обновляет информацию о том, где будет создана папка tbl."""
        tbl_path = self.current_dir / "tbl"
        self._tbl_info_label.config(
            text=f"📁 Папка 'tbl' будет создана: {tbl_path}",
            fg=Theme.ACCENT_GREEN
        )
    
    def _find_files_in_current_dir(self) -> Dict[str, Path]:
        """
        Ищет файлы нужных типов в текущей папке.
        
        Returns:
            Словарь {имя_файла: Path} для найденных файлов
        """
        found_files = {}
        
        if not self.current_dir.exists():
            return found_files
        
        try:
            files_in_dir = {f.name for f in self.current_dir.iterdir() if f.is_file()}
        except Exception:
            return found_files
        
        for filename, _, _ in self.FILE_TYPES:
            if filename in files_in_dir:
                found_files[filename] = self.current_dir / filename
        
        return found_files
    
    def _refresh_file_list(self):
        """Обновляет список файлов из текущей папки."""
        # Убираем заглушку
        if hasattr(self, '_placeholder') and self._placeholder:
            self._placeholder.destroy()
            self._placeholder = None
        
        # Очищаем старые виджеты
        for widget in self.scrollable.winfo_children():
            widget.destroy()
        
        self._vars.clear()
        self._checkboxes.clear()
        self._file_paths.clear()
        
        if not self.current_dir.exists():
            tk.Label(
                self.scrollable,
                text=f"❌ Папка не существует",
                font=("Segoe UI", 12),
                bg=Theme.BG_PRIMARY,
                fg=Theme.ERROR,
            ).pack(expand=True, pady=50)
            self._file_count_label.config(text="(папка не найдена)")
            return
        
        # Обновляем информацию о tbl
        self._update_tbl_info()
        
        # Ищем файлы
        self._file_paths = self._find_files_in_current_dir()
        
        if not self._file_paths:
            # Показываем что файлы не найдены
            tk.Label(
                self.scrollable,
                text="❌ В папке нет нужных файлов",
                font=("Segoe UI", 12),
                bg=Theme.BG_PRIMARY,
                fg=Theme.WARNING,
            ).pack(expand=True, pady=50)
            self._file_count_label.config(text="(0 файлов)")
            return
        
        # Показываем найденные файлы
        for filename, file_path in sorted(self._file_paths.items()):
            description = next((desc for f, _, desc in self.FILE_TYPES if f == filename), filename)
            
            var = tk.BooleanVar(value=True)
            self._vars[filename] = var
            
            row = tk.Frame(self.scrollable, bg=Theme.BG_PRIMARY)
            row.pack(fill=tk.X, pady=4)
            
            # Чекбокс
            cb = tk.Checkbutton(
                row,
                variable=var,
                bg=Theme.BG_PRIMARY,
                fg=Theme.FG_PRIMARY,
                activebackground=Theme.HOVER,
                selectcolor="white",
                font=("Segoe UI", 11),
            )
            cb.pack(side="left")
            self._checkboxes[filename] = cb
            
            # Информация о файле
            self._create_file_info(row, filename, description, file_path)
        
        self._file_count_label.config(text=f"({len(self._file_paths)} файлов)")
    
    def _create_file_info(self, parent, filename: str, description: str, file_path: Path):
        """
        Создаёт панель с информацией о файле.
        
        Args:
            parent: Родительский фрейм
            filename: Имя файла
            description: Описание типа файла
            file_path: Полный путь к файлу
        """
        info = tk.Frame(parent, bg=Theme.BG_PRIMARY)
        info.pack(side="left", padx=(10, 0), fill=tk.X, expand=True)
        
        tk.Label(
            info,
            text=description,
            font=("Segoe UI", 11, "bold"),
            bg=Theme.BG_PRIMARY,
            fg=Theme.FG_PRIMARY,
            anchor="w",
        ).pack(anchor="w")
        
        tk.Label(
            info,
            text=filename,
            font=("Consolas", 9),
            bg=Theme.BG_PRIMARY,
            fg=Theme.FG_SECONDARY,
            anchor="w",
        ).pack(anchor="w")
        
        # Размер файла
        size = file_path.stat().st_size
        size_str = f"{size / 1024:.0f} KB" if size < 1024*1024 else f"{size / 1024 / 1024:.1f} MB"
        
        tk.Label(
            info,
            text=f"✓ {size_str}",
            font=("Segoe UI", 9),
            bg=Theme.BG_PRIMARY,
            fg=Theme.SUCCESS,
        ).pack(anchor="w")
    
    def _select_all(self):
        """Выбирает все файлы в списке."""
        for var in self._vars.values():
            var.set(True)
    
    def _deselect_all(self):
        """Снимает выбор со всех файлов."""
        for var in self._vars.values():
            var.set(False)
    
    def _on_transform(self):
        """Запускает трансформацию выбранных файлов через контроллер."""
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
        
        if not self.current_dir.exists():
            messagebox.showerror(
                "Ошибка",
                f"Папка не существует",
                parent=self.dialog
            )
            return
        
        # Вызываем callback контроллера
        self.on_transform_callback(selected, str(self.current_dir))
        self._on_close()
    
    def _on_close(self):
        """Закрывает диалог."""
        self.dialog.destroy()
    
    def show(self):
        """Показывает диалог и ожидает его закрытия."""
        self.dialog.wait_window()