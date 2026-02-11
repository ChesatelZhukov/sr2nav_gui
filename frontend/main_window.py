#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Главное окно приложения.
Только UI, никакой бизнес-логики.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from datetime import datetime

from frontend.themes import Theme
from frontend.widgets import (
    ModernButton,
    FileEntryWidget,
    CollapsibleFrame,
    TransformFileDialog,
    VelocityAnalysisDialog,
    GPSConstellationDialog,
)


class MainWindow:
    """
    Главное окно приложения.
    
    Ответственности:
        - Отображение всех UI элементов
        - Сбор пользовательского ввода
        - Отправка событий в контроллер
        - Обновление интерфейса по сообщениям от контроллера
    """
    
    def __init__(self, controller):
        """
        :param controller: Ссылка на контроллер для callback'ов
        """
        self._controller = controller
        self._root: Optional[tk.Tk] = None
        
        # Виджеты
        self._file_widgets: Dict[str, FileEntryWidget] = {}
        self._entry_start: Optional[tk.Entry] = None
        self._entry_end: Optional[tk.Entry] = None
        self._entry_angle: Optional[tk.Entry] = None
        self._btn_terminate: Optional[ModernButton] = None
        self._progress_bar: Optional[ttk.Progressbar] = None
        self._status_var: Optional[tk.StringVar] = None
        self._output_text: Optional[tk.Text] = None
        
        # Теги для подсветки
        self._TAGS = {
            'debug': Theme.DEBUG,
            'info': Theme.INFO,
            'warning': Theme.WARNING,
            'error': Theme.ERROR,
            'success': Theme.SUCCESS,
            'header': Theme.ACCENT_BLUE,
        }
    
    # ==================== ЗАПУСК ====================
    
    def run(self) -> None:
        """Создаёт окно и запускает главный цикл."""
        self._create_window()
        self._create_menu()
        self._create_widgets()
        self._setup_styles()
        self._auto_fill_standard_files()
        
        # Запуск обработки очереди сообщений
        self._poll_message_queue()
        
        self._root.mainloop()
    
    # ==================== СОЗДАНИЕ ИНТЕРФЕЙСА ====================
    
    def _create_window(self) -> None:
        """Создаёт главное окно."""
        self._root = tk.Tk()
        self._root.title("SR2NAV Studio — Обработка GNSS данных")
        self._root.geometry("1400x750")
        self._root.minsize(1200, 650)
        self._root.configure(bg=Theme.BG_PRIMARY)
        
        # Центрирование
        self._root.update_idletasks()
        width = self._root.winfo_width()
        height = self._root.winfo_height()
        x = (self._root.winfo_screenwidth() // 2) - (width // 2)
        y = (self._root.winfo_screenheight() // 2) - (height // 2)
        self._root.geometry(f'{width}x{height}+{x}+{y}')
    
    def _setup_styles(self) -> None:
        """Настраивает стили ttk виджетов."""
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(
            'Accent.Horizontal.TProgressbar',
            background=Theme.ACCENT_BLUE,
            troughcolor=Theme.BORDER,
            bordercolor=Theme.BORDER,
        )
    
    def _create_menu(self) -> None:
        """Создаёт меню приложения."""
        menubar = tk.Menu(self._root)
        self._root.config(menu=menubar)
        
        # Файл
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Файл", menu=file_menu)
        file_menu.add_command(label="📁 Открыть рабочий каталог", command=self._on_open_working_dir)
        file_menu.add_separator()
        file_menu.add_command(label="🚪 Выход", command=self._root.quit)
        
        # Анализ
        analysis_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Анализ", menu=analysis_menu)
        analysis_menu.add_command(
            label="📊 Анализ скоростей (VEL)",
            command=self._controller.on_analyze_velocities
        )
        analysis_menu.add_command(
            label="🛰️ Анализ GPS созвездия",
            command=self._controller.on_analyze_gps_constellation
        )
        
        # Инструменты
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Инструменты", menu=tools_menu)
        tools_menu.add_command(
            label="🔄 Трансформация в TBL",
            command=self._on_show_transform_dialog
        )
        tools_menu.add_command(
            label="🚫 Исключение спутников",
            command=self._controller.on_show_gps_exclusion_dialog
        )
        
        # Вид
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Вид", menu=view_menu)
        view_menu.add_command(label="🧹 Очистить вывод", command=self.clear_output)
        
        # Справка
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Справка", menu=help_menu)
        help_menu.add_command(label="ℹ️ О программе", command=self._on_about)
    
    def _create_widgets(self) -> None:
        """Создаёт все виджеты окна."""
        # Основной контейнер
        main = tk.Frame(self._root, bg=Theme.BG_PRIMARY)
        main.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        
        # Верхняя панель
        self._create_top_panel(main)
        
        # Контент
        content = tk.Frame(main, bg=Theme.BG_PRIMARY)
        content.pack(fill=tk.BOTH, expand=True, pady=8)
        
        # Левая панель (файлы и параметры)
        left = tk.Frame(content, bg=Theme.BG_PRIMARY, width=600)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))
        left.pack_propagate(False)
        
        self._create_files_panel(left)
        self._create_params_panel(left)
        
        # Правая панель (вывод)
        right = tk.Frame(content, bg=Theme.BG_PRIMARY)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(4, 0))
        
        self._create_output_panel(right)
        
        # Нижняя панель (статус)
        self._create_status_panel(main)
    
    def _create_top_panel(self, parent) -> None:
        """Верхняя панель с заголовком и кнопками."""
        frame = tk.Frame(parent, bg=Theme.BG_SECONDARY, height=60)
        frame.pack(fill=tk.X)
        frame.pack_propagate(False)
        
        # Заголовок
        title_frame = tk.Frame(frame, bg=Theme.BG_SECONDARY)
        title_frame.pack(side=tk.LEFT, padx=15)
        
        tk.Label(
            title_frame,
            text="SR2NAV Studio",
            font=("Segoe UI", 16, "bold"),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY,
        ).pack(anchor="w")
        
        tk.Label(
            title_frame,
            text="Обработка GNSS данных",
            font=("Segoe UI", 9),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_SECONDARY,
        ).pack(anchor="w")
        
        # Кнопки
        btn_frame = tk.Frame(frame, bg=Theme.BG_SECONDARY)
        btn_frame.pack(side=tk.RIGHT, padx=15)
        
        self._btn_terminate = ModernButton(
            btn_frame,
            text="⏹ Остановить",
            bg=Theme.ACCENT_RED,
            fg="white",
            state="disabled",
            command=self._controller.on_terminate_process,
        )
        self._btn_terminate.pack(side=tk.RIGHT, padx=4)
        
        ModernButton(
            btn_frame,
            text="▶ SR2Nav",
            bg=Theme.ACCENT_BLUE,
            fg="white",
            command=self._controller.on_run_sr2nav,
        ).pack(side=tk.RIGHT, padx=4)
        
        ModernButton(
            btn_frame,
            text="▶▶ Полный цикл",
            bg=Theme.ACCENT_GREEN,
            fg="white",
            font=("Segoe UI", 10, "bold"),
            command=self._controller.on_run_full_cycle,
        ).pack(side=tk.RIGHT, padx=4)
        
        ModernButton(
            btn_frame,
            text="⏱ Интервал",
            bg=Theme.ACCENT_ORANGE,
            fg="white",
            command=self._controller.on_run_interval,
        ).pack(side=tk.RIGHT, padx=4)
    
    def _create_files_panel(self, parent) -> None:
        """Панель выбора файлов."""
        frame = CollapsibleFrame(parent, title="📁 Входные файлы")
        frame.pack(fill=tk.X, pady=(0, 8))
        
        content = tk.Frame(frame.content, bg=Theme.BG_PRIMARY)
        content.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        files = [
            ("SR2Nav (exe)", "sr2nav", ".exe"),
            ("Ровер (JPS)", "rover", ".jps"),
            ("База 1 (JPS)", "base1", ".jps"),
            ("База 2 (JPS)", "base2", ".jps"),
            ("POS базы 1", "pos1", ".pos"),
            ("POS базы 2", "pos2", ".pos"),
            ("Конфиг (cfg)", "cfg", ".cfg"),
            ("Гравика (air)", "air", ".air"),
        ]
        
        for label, key, ext in files:
            widget = FileEntryWidget(
                content,
                label_text=label,
                browse_callback=lambda k=key, e=ext: self._on_browse_file(k, e),
                open_callback=self._controller.on_open_file,
                stitch_callback=lambda: self._on_stitch_files() if key in ('rover', 'base1', 'base2') else None,
            )
            widget.pack(fill=tk.X, pady=2)
            self._file_widgets[key] = widget
    
    def _create_params_panel(self, parent) -> None:
        """Панель параметров обработки."""
        frame = CollapsibleFrame(parent, title="⚙️ Параметры обработки")
        frame.pack(fill=tk.X, pady=(0, 8))
        
        content = tk.Frame(frame.content, bg=Theme.BG_PRIMARY)
        content.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Временной интервал
        time_frame = tk.Frame(content, bg=Theme.BG_PRIMARY)
        time_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(
            time_frame,
            text="Интервал:",
            font=("Segoe UI", 9, "bold"),
            bg=Theme.BG_PRIMARY,
            width=10,
            anchor="w",
        ).pack(side=tk.LEFT)
        
        tk.Label(time_frame, text="Начало:", bg=Theme.BG_PRIMARY).pack(side=tk.LEFT, padx=(5, 2))
        self._entry_start = tk.Entry(
            time_frame, 
            width=16, 
            font=("Consolas", 9),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY
        )
        self._entry_start.pack(side=tk.LEFT, padx=(0, 10))
        
        tk.Label(time_frame, text="Конец:", bg=Theme.BG_PRIMARY).pack(side=tk.LEFT, padx=(5, 2))
        self._entry_end = tk.Entry(
            time_frame, 
            width=16, 
            font=("Consolas", 9),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY
        )
        self._entry_end.pack(side=tk.LEFT, padx=(0, 10))
        
        tk.Frame(content, height=1, bg=Theme.BORDER).pack(fill=tk.X, pady=8)
        
        # Угол отсечения
        angle_frame = tk.Frame(content, bg=Theme.BG_PRIMARY)
        angle_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(
            angle_frame,
            text="Угол:",
            font=("Segoe UI", 9, "bold"),
            bg=Theme.BG_PRIMARY,
            width=10,
            anchor="w",
        ).pack(side=tk.LEFT)
        
        self._entry_angle = tk.Entry(
            angle_frame, 
            width=5, 
            font=("Consolas", 9), 
            justify="center",
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY
        )
        self._entry_angle.pack(side=tk.LEFT, padx=(0, 5))
        self._entry_angle.insert(0, "7.0")
        
        tk.Label(angle_frame, text="°", bg=Theme.BG_PRIMARY).pack(side=tk.LEFT, padx=(0, 15))
        
        ModernButton(
            angle_frame,
            text="🚫 Исключить спутники",
            bg=Theme.ACCENT_PURPLE,
            fg="white",
            command=self._controller.on_show_gps_exclusion_dialog,
        ).pack(side=tk.LEFT)
    
    def _create_output_panel(self, parent) -> None:
        """Панель вывода сообщений."""
        frame = tk.Frame(parent, bg=Theme.BG_SECONDARY, bd=1, relief=tk.SOLID)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Заголовок
        header = tk.Frame(frame, bg=Theme.BG_SECONDARY)
        header.pack(fill=tk.X, padx=8, pady=6)
        
        tk.Label(
            header,
            text="📋 Консоль вывода",
            font=("Segoe UI", 10, "bold"),
            bg=Theme.BG_SECONDARY,
        ).pack(side=tk.LEFT)
        
        ModernButton(
            header,
            text="🧹 Очистить",
            command=self.clear_output,
            padx=8,
        ).pack(side=tk.RIGHT, padx=2)
        
        ModernButton(
            header,
            text="📋 Копировать",
            command=self._copy_output,
            padx=8,
        ).pack(side=tk.RIGHT, padx=2)
        
        # Текстовое поле
        self._output_text = tk.Text(
            frame,
            wrap=tk.WORD,
            font=("Consolas", 10),
            bg="white",
            fg=Theme.FG_PRIMARY,
            relief=tk.FLAT,
            padx=8,
            pady=8,
        )
        
        scrollbar = tk.Scrollbar(frame, command=self._output_text.yview)
        self._output_text.configure(yscrollcommand=scrollbar.set)
        
        self._output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Настройка тегов
        self._output_text.tag_config("debug", foreground=Theme.DEBUG)
        self._output_text.tag_config("info", foreground=Theme.INFO)
        self._output_text.tag_config("warning", foreground=Theme.WARNING)
        self._output_text.tag_config("error", foreground=Theme.ERROR, font=("Consolas", 10, "bold"))
        self._output_text.tag_config("success", foreground=Theme.SUCCESS)
        self._output_text.tag_config("header", foreground=Theme.ACCENT_BLUE, font=("Consolas", 10, "bold"))
        
        self._print_welcome()
    
    def _create_status_panel(self, parent) -> None:
        """Нижняя панель статуса."""
        frame = tk.Frame(parent, bg=Theme.BG_SECONDARY, height=28)
        frame.pack(fill=tk.X)
        frame.pack_propagate(False)
        
        self._progress_bar = ttk.Progressbar(
            frame,
            mode='indeterminate',
            style='Accent.Horizontal.TProgressbar',
            length=200,
        )
        self._progress_bar.pack(side=tk.LEFT, padx=10, pady=4)
        
        self._status_var = tk.StringVar(value="✅ Готов к работе")
        
        tk.Label(
            frame,
            textvariable=self._status_var,
            font=("Segoe UI", 9),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_SECONDARY,
        ).pack(side=tk.RIGHT, padx=15)
    
    # ==================== ОБРАБОТЧИКИ СОБЫТИЙ ====================
    
    def _on_browse_file(self, key: str, extension: str) -> str:
        """Открывает диалог выбора файла."""
        path = filedialog.askopenfilename(
            title=f"Выберите файл - {key}",
            filetypes=[(f"{extension} файлы", f"*{extension}"), ("Все файлы", "*.*")],
            initialdir=self._controller.script_dir,
        )
        
        if path:
            # Уведомляем контроллер
            self._controller.on_file_selected(key, path)
        
        return path or ""
    
    def _on_stitch_files(self) -> None:
        """Обработчик сшивания JPS файлов."""
        input_files = filedialog.askopenfilenames(
            title="Выберите JPS файлы для сшивания",
            filetypes=[("JPS файлы", "*.jps"), ("Все файлы", "*.*")],
            initialdir=self._controller.script_dir,
        )
        
        if not input_files or len(input_files) < 2:
            messagebox.showwarning(
                "Внимание",
                "Необходимо выбрать минимум 2 файла",
                parent=self._root
            )
            return
        
        output_file = filedialog.asksaveasfilename(
            title="Сохранить сшитый JPS файл как",
            defaultextension=".jps",
            filetypes=[("JPS файлы", "*.jps"), ("Все файлы", "*.*")],
            initialdir=self._controller.script_dir,
        )
        
        if output_file:
            self._controller.on_stitch_jps(list(input_files), output_file)
    
    def _on_open_working_dir(self) -> None:
        """Открывает рабочий каталог в проводнике."""
        import subprocess
        import os
        
        path = self._controller.script_dir
        if os.path.exists(path):
            try:
                if os.name == 'nt':
                    subprocess.Popen(f'explorer "{path}"')
                else:
                    subprocess.Popen(['xdg-open', path])
            except Exception as e:
                self._append_output(f"❌ Ошибка открытия папки: {e}", "error")
    
    def _on_show_transform_dialog(self) -> None:
        """Показывает диалог трансформации файлов."""
        from core.app_context import APP_CONTEXT
        
        dialog = TransformFileDialog(
            self._root,
            str(APP_CONTEXT.working_dir),
            self._controller.on_transform_files,
        )
        dialog.show()
    
    def _on_about(self) -> None:
        """Показывает диалог 'О программе'."""
        from core.app_context import APP_CONTEXT
        
        about_text = f"""
╔════════════════════════════════════╗
║        SR2NAV Studio v2.0         ║
║     Обработка GNSS данных         ║
╚════════════════════════════════════╝

Рабочая директория:
{APP_CONTEXT.working_dir}

Разработчик: kurakov@aerogeo.ru
© 2024

Версия ядра: 2.0.0
Версия UI: 2.0.0
        """
        
        messagebox.showinfo(
            "О программе",
            about_text.strip(),
            parent=self._root
        )
    
    def _copy_output(self) -> None:
        """Копирует вывод в буфер обмена."""
        if self._output_text:
            content = self._output_text.get(1.0, tk.END)
            self._root.clipboard_clear()
            self._root.clipboard_append(content)
            self.set_status("📋 Скопировано")
            self._root.after(2000, lambda: self.set_status("✅ Готов к работе"))
    
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
                # Уведомляем контроллер
                self._controller.on_file_selected(key, str(path))
    
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
{'═'*70}
🚀 SR2NAV Studio v2.0.0
📅 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
📁 {APP_CONTEXT.working_dir}
{'═'*70}

✅ Система готова к работе
        """
        self._append_output(welcome.strip(), "header")
    
    # ==================== ПУБЛИЧНЫЙ API ДЛЯ КОНТРОЛЛЕРА ====================
    
    def get_all_file_paths(self) -> Dict[str, str]:
        """Возвращает словарь {тип_файла: путь} из UI."""
        paths = {}
        for key, widget in self._file_widgets.items():
            value = widget.get_value()
            if value:
                paths[key] = value
        return paths
    
    def sync_file_paths(self, paths: Dict[str, str]) -> None:
        """Синхронизирует пути из бэкенда в UI."""
        for key, path in paths.items():
            if key in self._file_widgets and path:
                current = self._file_widgets[key].get_value()
                if current != path:
                    self._file_widgets[key].set_value(path)
    
    def get_cutoff_angle(self) -> float:
        """Возвращает угол отсечения."""
        try:
            return float(self._entry_angle.get()) if self._entry_angle else 7.0
        except (ValueError, AttributeError):
            return 7.0
    
    def update_time_interval(self, start: str, end: str) -> None:
        """Обновляет поля временного интервала."""
        if self._entry_start:
            self._entry_start.delete(0, tk.END)
            self._entry_start.insert(0, start)
        if self._entry_end:
            self._entry_end.delete(0, tk.END)
            self._entry_end.insert(0, end)
        
        self._append_output(f"⏱ Интервал: {start} - {end}", "info")
    
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
    
    def set_status(self, message: str) -> None:
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
    
    @property
    def window(self) -> tk.Tk:
        """Возвращает корневое окно Tkinter."""
        return self._root