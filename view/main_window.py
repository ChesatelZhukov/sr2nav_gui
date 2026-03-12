import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Dict, Optional, List, Tuple, Callable
from datetime import datetime
import os
import sys
import subprocess
from view.themes import (    Theme, ThemeType, get_active_theme, set_active_theme,    get_all_themes, get_theme_name, apply_theme)
from view.widgets import (    ModernButton,    FileEntryWidget,    CollapsibleFrame,)
from view.persistence import UIPersistence
from core.message_system import MessageLevel
try:
    import pywinstyles
    HAS_PYWINSTYLES = True
except ImportError:
    HAS_PYWINSTYLES = False
class MainWindow:
    def __init__(self, controller):
        self._controller = controller
        self._current_stitch_target = "rover"
        self._root: Optional[tk.Tk] = None
        self._titlebar: Optional[tk.Frame] = None
        self._title_label: Optional[tk.Label] = None
        self._is_maximized: bool = False
        self._normal_geometry: Optional[str] = None
        self._drag_offset: Tuple[int, int] = (0, 0)
        self._file_widgets: Dict[str, FileEntryWidget] = {}
        self._entry_start: Optional[tk.Entry] = None
        self._entry_end: Optional[tk.Entry] = None
        self._entry_angle: Optional[tk.Entry] = None
        self._btn_terminate: Optional[ModernButton] = None
        self._progress_bar: Optional[ttk.Progressbar] = None
        self._status_var: Optional[tk.StringVar] = None
        self._output_text: Optional[tk.Text] = None
        self._interval_mode_label: Optional[tk.Label] = None
        self._menu_buttons = []
        self._active_menu = None
        self._menu_popups = {}

    def run(self) -> None:
        self._create_window()
        # Используем стандартный заголовок Windows, а цвет заголовка
        # форсируем в тёмный через pywinstyles (если установлен).
        self._create_custom_menu()
        self._create_widgets()
        self._setup_styles()
        self._auto_fill_standard_files()
        self._setup_output_tags()
        self._poll_message_queue()
        self._root.mainloop()
    def quit_application(self) -> None:
        if self._root:
            UIPersistence.save()
            self._root.quit()
    def update_window_title(self, rover_name: str) -> None:
        if self._root:
            if rover_name and rover_name.strip():
                title = f"SR2NAV GUI — {rover_name} — Обработка GNSS данных"
            else:
                title = "SR2NAV GUI — Обработка GNSS данных"
            self._root.title(title)
            if self._title_label:
                self._title_label.config(text=title)
    def get_all_file_paths(self) -> Dict[str, str]:
        paths = {}
        for key, widget in self._file_widgets.items():
            value = widget.get_value()
            if value:
                paths[key] = value
        return paths
    def get_sr2nav_path(self) -> str:
        widget = self._file_widgets.get('sr2nav')
        return widget.get_value() if widget else ""
    def get_rover_path(self) -> str:
        widget = self._file_widgets.get('rover')
        return widget.get_value() if widget else ""
    def set_file_path(self, key: str, path: str) -> None:
        if key in self._file_widgets and path:
            self._file_widgets[key].set_value(path)
    def get_cutoff_angle(self) -> float:
        try:
            return float(self._entry_angle.get()) if self._entry_angle else 7.0
        except (ValueError, AttributeError):
            return 7.0
    def set_cutoff_angle_value(self, angle: float) -> None:
        if self._entry_angle:
            self._entry_angle.delete(0, tk.END)
            self._entry_angle.insert(0, f"{angle:.1f}")
    def update_time_interval(self, start: str, end: str, is_manual: bool = False) -> None:
        if self._entry_start:
            self._entry_start.delete(0, tk.END)
            self._entry_start.insert(0, start)
        if self._entry_end:
            self._entry_end.delete(0, tk.END)
            self._entry_end.insert(0, end)
        if self._interval_mode_label:
            if is_manual:
                self._interval_mode_label.config(                    text="✏️ ручной",                    fg=Theme.ACCENT_ORANGE                )
                self._append_output(f"⏱ Интервал (ручной): {start} - {end}", "info")
            else:
                self._interval_mode_label.config(                    text="⚡ авто",                    fg=Theme.FG_SECONDARY                )
                self._append_output(f"⏱ Интервал (авто): {start} - {end}", "info")
    def set_processing_state(self, is_processing: bool) -> None:
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
        if self._status_var:
            self._status_var.set(message)
    def clear_output(self) -> None:
        if self._output_text:
            self._output_text.delete(1.0, tk.END)
            self._print_welcome()
            self.set_status("🧹 Вывод очищен")
            self._root.after(2000, lambda: self.set_status("✅ Готов к работе"))
    def show_error(self, title: str, message: str):
        messagebox.showerror(title, message, parent=self._root)
    @property
    def window(self) -> tk.Tk:
        return self._root
    def _create_custom_menu(self) -> None:
        menu_bar = tk.Frame(            self._root,            bg=Theme.BG_SECONDARY,            height=30,            highlightbackground=Theme.BORDER,            highlightthickness=1        )
        menu_bar.pack(fill=tk.X)
        menu_bar.pack_propagate(False)
        menu_items = {
            "📁 Файл": [
                ("📂 Открыть рабочий каталог", self._on_open_working_dir),
                None,
                ("🚪 Выход", self._on_exit),
            ],
            "📊 Анализ": [
                ("📈     Анализ скоростей (VEL)", self._controller.on_analyze_velocities),
                ("🛰️Анализ GPS созвездия", self._controller.on_analyze_gps_constellation),
            ],
            "🔧 Инструменты": [
                ("🔄 Трансформация в TBL", self._on_show_transform_dialog),
                ("🚫 Исключение спутников", self._controller.on_show_gps_exclusion_dialog),
                None,
                ("🧹 Очистить рабочую директорию", self._controller.on_cleanup_working_directory),
            ],
            "❓ Справка": [
                ("ℹ️ О программе", self._on_about),
                ("📖 Помощь", self._on_help_readme_exe),
            ],
        }
        for menu_text in menu_items.keys():
            btn = tk.Button(
                menu_bar,
                text=menu_text,
                font=("Segoe UI", 10),
                bg=Theme.BG_SECONDARY,
                fg=Theme.FG_PRIMARY,
                activebackground=Theme.HOVER,
                activeforeground=Theme.FG_PRIMARY,
                relief=tk.FLAT,
                bd=0,
                padx=15,
                pady=2,
                cursor="hand2",
            )
            btn.pack(side=tk.LEFT, padx=2)
            # Открываем меню по клику, а не по наведению
            btn.bind(
                "<Button-1>",
                lambda e, m=menu_text, items=menu_items[menu_text]: self._show_menu(
                    e, m, items
                ),
            )
            btn.bind("<Leave>", self._hide_menu_delayed)
            self._menu_buttons.append(btn)
        theme_btn = tk.Button(            menu_bar,            text="🎨",            font=("Segoe UI", 12),            bg=Theme.BG_SECONDARY,            fg=Theme.FG_PRIMARY,            activebackground=Theme.HOVER,            activeforeground=Theme.FG_PRIMARY,            relief=tk.FLAT,            bd=0,            padx=10,            pady=2,            cursor="hand2"        )
        theme_btn.pack(side=tk.RIGHT, padx=5)
        theme_btn.bind("<Button-1>", self._show_theme_menu)
        version_label = tk.Label(            menu_bar,            text="v1.0",            font=("Segoe UI", 9),            bg=Theme.BG_SECONDARY,            fg=Theme.FG_SECONDARY        )
        version_label.pack(side=tk.RIGHT, padx=10)
    def _show_menu(self, event, menu_title: str, items: list) -> None:
        self._hide_menu()
        menu = tk.Menu(            self._root,            tearoff=0,            bg=Theme.BG_SECONDARY,            fg=Theme.FG_PRIMARY,            activebackground=Theme.HOVER,            activeforeground=Theme.FG_PRIMARY,            borderwidth=1,            relief=tk.SOLID        )
        for item in items:
            if item is None:
                menu.add_separator()
            else:
                text, command = item
                menu.add_command(                    label=text,                    command=command,                    font=("Segoe UI", 10)                )
        try:
            x = event.widget.winfo_rootx()
            y = event.widget.winfo_rooty() + event.widget.winfo_height()
            menu.tk_popup(x, y)
            self._active_menu = menu
        except:
            pass
    def _show_theme_menu(self, event):
        menu = tk.Menu(            self._root,            tearoff=0,            bg=Theme.BG_SECONDARY,            fg=Theme.FG_PRIMARY,            activebackground=Theme.HOVER,            activeforeground=Theme.FG_PRIMARY,            borderwidth=1,            relief=tk.SOLID        )
        themes = get_all_themes()
        current_theme = UIPersistence.get_theme()
        for theme_type, theme_name in themes.items():
            prefix = "✓ " if theme_type == current_theme else "  "
            menu.add_command(                label=f"{prefix}{theme_name}",                command=lambda t=theme_type: self._on_theme_selected(t),                font=("Segoe UI", 10)            )
        try:
            x = event.widget.winfo_rootx()
            y = event.widget.winfo_rooty() + event.widget.winfo_height()
            menu.tk_popup(x, y)
            self._active_menu = menu
        except:
            pass
    def _hide_menu(self, event=None):
        if self._active_menu:
            try:
                self._active_menu.unpost()
            except:
                pass
            self._active_menu = None
    def _hide_menu_delayed(self, event):
        self._root.after(200, self._hide_menu)
    def _create_window(self) -> None:
        self._root = tk.Tk()
        saved_theme = UIPersistence.get_theme()
        set_active_theme(saved_theme)
        if hasattr(self._root, 'tk'):
            try:
                self._root.tk.call('tk', 'theme_use', 'clam')
            except:
                pass
        if HAS_PYWINSTYLES:
            try:
                pywinstyles.apply_style(self._root, 'dark')
            except Exception as e:
                print(f"Не удалось применить тёмный заголовок: {e}")
        self._root.title("SR2NAV GUI — Обработка GNSS данных")
        width, height = UIPersistence.get_window_size()
        self._root.geometry(f"{width}x{height}")
        self._root.minsize(1400, 850)
        self._root.configure(bg=Theme.BG_PRIMARY)
        self._root.bind('<Configure>', self._on_window_resize)
        self._center_window()
        # ВАЖНО: не отключаем полностью стандартный заголовок через overrideredirect,
        # чтобы окно корректно отображалось на панели задач Windows.
        # Кастомный заголовок остаётся, но приложение теперь видно в панели задач.
        self._root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _create_custom_titlebar(self) -> None:
        if not self._root or self._titlebar:
            return

        self._titlebar = tk.Frame(
            self._root,
            bg=Theme.BG_SECONDARY,
            height=32,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
        )
        self._titlebar.pack(fill=tk.X, side=tk.TOP)
        self._titlebar.pack_propagate(False)

        # Область для перетаскивания окна
        drag_frame = tk.Frame(self._titlebar, bg=Theme.BG_SECONDARY)
        drag_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))

        self._title_label = tk.Label(
            drag_frame,
            text=self._root.title(),
            font=("Segoe UI", 10),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY,
            anchor="w",
        )
        self._title_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        drag_frame.bind("<Button-1>", self._start_move)
        drag_frame.bind("<B1-Motion>", self._on_move)
        self._title_label.bind("<Button-1>", self._start_move)
        self._title_label.bind("<B1-Motion>", self._on_move)
        drag_frame.bind("<Double-Button-1>", self._toggle_maximize)
        self._title_label.bind("<Double-Button-1>", self._toggle_maximize)

        # Кнопки управления окном
        btn_container = tk.Frame(self._titlebar, bg=Theme.BG_SECONDARY)
        btn_container.pack(side=tk.RIGHT, padx=4)

        def create_caption_button(text: str, command: Callable, hover_bg: str) -> tk.Button:
            btn = tk.Button(
                btn_container,
                text=text,
                font=("Segoe UI", 9),
                width=4,
                bd=0,
                relief=tk.FLAT,
                bg=Theme.BG_SECONDARY,
                fg=Theme.FG_PRIMARY,
                activebackground=hover_bg,
                activeforeground=Theme.FG_PRIMARY,
                cursor="hand2",
                command=command,
            )

            def on_enter(e):
                btn.configure(bg=hover_bg)

            def on_leave(e):
                btn.configure(bg=Theme.BG_SECONDARY)

            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)
            return btn

        minimize_btn = create_caption_button("─", self._minimize_window, Theme.BG_TERTIARY)
        maximize_btn = create_caption_button("▢", self._toggle_maximize, Theme.BG_TERTIARY)
        close_btn = create_caption_button("✕", self._on_closing, Theme.ACCENT_RED)

        minimize_btn.pack(side=tk.LEFT, padx=1, pady=3)
        maximize_btn.pack(side=tk.LEFT, padx=1, pady=3)
        close_btn.pack(side=tk.LEFT, padx=(4, 6), pady=3)

    def _start_move(self, event) -> None:
        if not self._root:
            return
        self._drag_offset = (event.x_root - self._root.winfo_x(), event.y_root - self._root.winfo_y())

    def _on_move(self, event) -> None:
        if not self._root:
            return
        dx, dy = self._drag_offset
        x = event.x_root - dx
        y = event.y_root - dy
        self._root.geometry(f"+{x}+{y}")

    def _toggle_maximize(self, event=None) -> None:
        if not self._root:
            return

        if not self._is_maximized:
            # Запоминаем текущее положение/размер
            self._normal_geometry = self._root.geometry()
            screen_w = self._root.winfo_screenwidth()
            screen_h = self._root.winfo_screenheight()
            self._root.geometry(f"{screen_w}x{screen_h}+0+0")
            self._is_maximized = True
        else:
            if self._normal_geometry:
                self._root.geometry(self._normal_geometry)
            self._is_maximized = False

    def _minimize_window(self) -> None:
        if self._root:
            self._root.iconify()
    def _center_window(self) -> None:
        self._root.update_idletasks()
        width = self._root.winfo_width()
        height = self._root.winfo_height()
        x = (self._root.winfo_screenwidth() // 2) - (width // 2)
        y = (self._root.winfo_screenheight() // 2) - (height // 2)
        self._root.geometry(f'{width}x{height}+{x}+{y}')
    def _on_window_resize(self, event):
        if event.widget == self._root:
            if event.width > 100 and event.height > 100:
                UIPersistence.set_window_size(event.width, event.height)
    def _on_closing(self):
        UIPersistence.save()
        self._controller.on_app_closing()
    def _setup_styles(self) -> None:
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(            'Accent.Horizontal.TProgressbar',            background=Theme.ACCENT_BLUE,            troughcolor=Theme.BORDER,            bordercolor=Theme.BORDER,        )
    def _setup_output_tags(self) -> None:
        if self._output_text:
            for tag in self._output_text.tag_names():
                self._output_text.tag_delete(tag)
            self._output_text.tag_config("debug", foreground=Theme.DEBUG)
            self._output_text.tag_config("info", foreground=Theme.INFO)
            self._output_text.tag_config("success", foreground=Theme.SUCCESS)
            self._output_text.tag_config("warning", foreground=Theme.WARNING)
            self._output_text.tag_config("error", foreground=Theme.ERROR, font=("Consolas", 11, "bold"))
            self._output_text.tag_config("header", foreground=Theme.ACCENT_BLUE, font=("Consolas", 11, "bold"))
    def _on_theme_selected(self, theme_type: ThemeType) -> None:
        UIPersistence.set_theme(theme_type)
        UIPersistence.save()
        set_active_theme(theme_type)
        self._apply_theme_to_all_widgets()
        theme_name = get_theme_name(theme_type)
        self._append_output(f"🎨 Тема изменена: {theme_name}", "info")
    def _apply_theme_to_all_widgets(self) -> None:
        try:
            apply_theme(self._root, get_active_theme())
            self._update_widgets_colors(self._root)
            self._setup_styles()
            self._root.update_idletasks()
            self._setup_output_tags()
        except Exception as e:
            print(f"Ошибка применения темы: {e}")
    def _update_widgets_colors(self, widget):
        try:
            if isinstance(widget, (tk.Frame, tk.LabelFrame, tk.Canvas, tk.Button)):
                try:
                    current_bg = widget.cget('bg')
                    if current_bg in ('SystemButtonFace', 'SystemWindow', '#f0f0f0'):
                        widget.configure(bg=Theme.BG_PRIMARY)
                except:
                    pass
            if isinstance(widget, tk.Label):
                try:
                    if widget.cget('bg') in ('SystemButtonFace', 'SystemWindow', '#f0f0f0'):
                        widget.configure(bg=Theme.BG_PRIMARY)
                except:
                    pass
            if isinstance(widget, tk.Entry):
                try:
                    widget.configure(                        bg=Theme.BG_SECONDARY,                        fg=Theme.FG_PRIMARY,                        highlightcolor=Theme.ACCENT_BLUE                    )
                except:
                    pass
            if isinstance(widget, tk.Button) and widget not in self._menu_buttons:
                try:
                    current_bg = widget.cget('bg')
                    # Только "системные" кнопки перекрашиваем в общий фон,
                    # кнопки с акцентными цветами (ACCENT_*) оставляем, чтобы не терять контраст
                    if current_bg in ('SystemButtonFace', 'SystemWindow', '#f0f0f0'):
                        widget.configure(                            bg=Theme.BG_SECONDARY,                            fg=Theme.FG_PRIMARY,                            activebackground=Theme.HOVER,                            activeforeground=Theme.FG_PRIMARY                        )
                    # Обновляем "оригинальные" цвета, чтобы hover-логика ModernButton не откатывала старую тему
                    if hasattr(widget, "_original_bg"):
                        widget._original_bg = widget.cget("bg")
                    if hasattr(widget, "_original_fg"):
                        widget._original_fg = widget.cget("fg")
                except:
                    pass
            for child in widget.winfo_children():
                self._update_widgets_colors(child)
        except Exception:
            pass
    def _create_widgets(self) -> None:
        main = tk.Frame(self._root, bg=Theme.BG_PRIMARY)
        main.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        self._create_top_panel(main)
        content = tk.Frame(main, bg=Theme.BG_PRIMARY)
        content.pack(fill=tk.BOTH, expand=True, pady=12)
        left = tk.Frame(content, bg=Theme.BG_PRIMARY, width=650)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        left.pack_propagate(False)
        self._create_files_panel(left)
        self._create_params_panel(left)
        right = tk.Frame(content, bg=Theme.BG_PRIMARY)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(6, 0))
        self._create_output_panel(right)
        self._create_status_panel(main)
        self._controller.on_window_ready()
    def _create_top_panel(self, parent) -> None:
        frame = tk.Frame(            parent,             bg=Theme.BG_SECONDARY,            height=70,            highlightbackground=Theme.BORDER,            highlightthickness=1        )
        frame.pack(fill=tk.X)
        frame.pack_propagate(False)
        self._create_title_section(frame)
        self._create_action_buttons(frame)
        separator = tk.Frame(parent, bg=Theme.BORDER, height=1)
        separator.pack(fill=tk.X)
    def _create_title_section(self, parent) -> None:
        title_frame = tk.Frame(parent, bg=Theme.BG_SECONDARY)
        title_frame.pack(side=tk.LEFT, padx=20)
        tk.Label(            title_frame,            text="🚀 SR2NAV GUI",            font=("Segoe UI", 20, "bold"),            bg=Theme.BG_SECONDARY,            fg=Theme.FG_PRIMARY,        ).pack(anchor="w")
        tk.Label(            title_frame,            text="Обработка GNSS данных",            font=("Segoe UI", 11),            bg=Theme.BG_SECONDARY,            fg=Theme.FG_SECONDARY,        ).pack(anchor="w")
    def _create_action_buttons(self, parent) -> None:
        btn_frame = tk.Frame(parent, bg=Theme.BG_SECONDARY)
        btn_frame.pack(side=tk.RIGHT, padx=20)
        self._btn_terminate = ModernButton(            btn_frame,            text="⏹ Стоп",            bg=Theme.ACCENT_RED,            fg="white",            state="disabled",            command=self._on_terminate_with_confirmation,            font=("Segoe UI", 11),            padx=12,            pady=4,        )
        self._btn_terminate.pack(side=tk.RIGHT, padx=4)
        ModernButton(            btn_frame,            text="▶ SR2Nav",            bg=Theme.ACCENT_BLUE,            fg="white",            command=self._controller.on_run_sr2nav,            font=("Segoe UI", 11),            padx=16,            pady=6,        ).pack(side=tk.RIGHT, padx=4)
        ModernButton(            btn_frame,            text="▶▶ Полный цикл",            bg=Theme.ACCENT_GREEN,            fg="white",            font=("Segoe UI", 11, "bold"),            command=self._controller.on_run_full_cycle,            padx=20,            pady=8,        ).pack(side=tk.RIGHT, padx=4)
        ModernButton(            btn_frame,            text="⏱ Интервал",            bg=Theme.ACCENT_ORANGE,            fg="white",            command=self._controller.on_run_interval,            font=("Segoe UI", 11),            padx=16,            pady=6,        ).pack(side=tk.RIGHT, padx=4)
    def _create_files_panel(self, parent) -> None:
        frame = CollapsibleFrame(parent, title="📁 Входные файлы")
        frame.pack(fill=tk.X, pady=(0, 10))
        if hasattr(frame, '_header'):
            frame._header.configure(bg=Theme.BG_TERTIARY)
        if hasattr(frame, '_title_label'):
            frame._title_label.configure(bg=Theme.BG_TERTIARY)
        if hasattr(frame, '_toggle_btn'):
            frame._toggle_btn.configure(bg=Theme.BG_TERTIARY)
        content = tk.Frame(frame.content, bg=Theme.BG_PRIMARY)
        content.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        files = [            ("📦 SR2Nav (exe)", "sr2nav", ".exe", False, True),            ("🚙 Ровер (JPS)", "rover", ".jps", True, False),            ("🏠 База 1 (JPS)", "base1", ".jps", True, False),            ("🏠 База 2 (JPS)", "base2", ".jps", True, False),            ("📍 POS базы 1", "pos1", ".pos", False, False),            ("📍 POS базы 2", "pos2", ".pos", False, False),            ("⚙️ Конфиг (cfg)", "cfg", ".cfg", False, False),            ("🌍 Гравика (air)", "air", ".air", False, False),        ]
        for label, key, ext, can_stitch, is_exe in files:
            widget = FileEntryWidget(                content,                label_text=label,                browse_callback=lambda k=key, e=ext: self._on_browse_file(k, e),                open_callback=self._controller.on_open_file,                stitch_callback=self._on_stitch_files if can_stitch else None,                expected_extension=ext,                file_key=key,            )
            widget.pack(fill=tk.X, pady=3)
            self._file_widgets[key] = widget
    def _create_params_panel(self, parent):
        frame = CollapsibleFrame(parent, title="⚙️ Параметры обработки")
        frame.pack(fill=tk.X, pady=(0, 10))
        if hasattr(frame, '_header'):
            frame._header.configure(bg=Theme.BG_TERTIARY)
        if hasattr(frame, '_title_label'):
            frame._title_label.configure(bg=Theme.BG_TERTIARY)
        if hasattr(frame, '_toggle_btn'):
            frame._toggle_btn.configure(bg=Theme.BG_TERTIARY)
        frame.content.configure(bg=Theme.BG_PRIMARY)
        content = tk.Frame(frame.content, bg=Theme.BG_PRIMARY)
        content.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self._create_time_interval_section(content)
        self._create_angle_section(content)
    def _create_time_interval_section(self, parent):
        time_frame = tk.Frame(parent, bg=Theme.BG_PRIMARY)
        time_frame.pack(fill=tk.X, pady=8)
        tk.Label(            time_frame,            text="⏰",            font=("Segoe UI", 11, "bold"),            bg=Theme.BG_PRIMARY,            width=2,            anchor="w",        ).pack(side=tk.LEFT)
        tk.Label(            time_frame,            text="Начало:",            font=("Segoe UI", 10),            bg=Theme.BG_PRIMARY,            fg=Theme.FG_PRIMARY,        ).pack(side=tk.LEFT, padx=(0, 1))
        self._entry_start = tk.Entry(            time_frame,            width=21,            font=("Consolas", 11),            bg=Theme.BG_SECONDARY,            fg=Theme.FG_PRIMARY,            bd=1,            relief=tk.SOLID,            highlightcolor=Theme.ACCENT_BLUE,            highlightthickness=1,        )
        self._entry_start.pack(side=tk.LEFT, padx=(0, 12))
        tk.Label(            time_frame,            text="Конец:",            font=("Segoe UI", 10),            bg=Theme.BG_PRIMARY,            fg=Theme.FG_PRIMARY,        ).pack(side=tk.LEFT, padx=(0, 1))
        self._entry_end = tk.Entry(            time_frame,            width=21,            font=("Consolas", 11),            bg=Theme.BG_SECONDARY,            fg=Theme.FG_PRIMARY,            bd=1,            relief=tk.SOLID,            highlightcolor=Theme.ACCENT_BLUE,            highlightthickness=1,        )
        self._entry_end.pack(side=tk.LEFT, padx=(0, 10))
        self._btn_interval_confirm = ModernButton(            time_frame,            text="💾",            width=3,            bg=Theme.ACCENT_BLUE,            fg="white",            command=self._on_interval_confirm,            font=("Segoe UI", 10),            padx=8,            pady=2,        )
        self._btn_interval_confirm.pack(side=tk.LEFT, padx=(0, 5))
        self._interval_mode_label = tk.Label(            time_frame,            text="⚡ авто",            font=("Segoe UI", 9),            bg=Theme.BG_PRIMARY,            fg=Theme.FG_SECONDARY,        )
        self._interval_mode_label.pack(side=tk.LEFT, padx=(0, 0))
        tk.Frame(parent, height=1, bg=Theme.BORDER).pack(fill=tk.X, pady=12)
    def _on_interval_confirm(self):
        if not self._entry_start or not self._entry_end:
            return
        start = self._entry_start.get().strip()
        end = self._entry_end.get().strip()
        if start and end:
            import re
            gps_time_pattern = r'^\d{4}:\d{2}:\d{2}:\d{2}:\d{2}:\d{2}\.\d+$'
            if not re.match(gps_time_pattern, start):
                self._append_output(                    f"⚠️ Неверный формат начала: {start}\n"                    f"   Ожидается формат GPS времени: YYYY:MM:DD:HH:MM:SS.f\n"                    f"   Например: 2024:09:22:00:30:01.0",                     "warning"                )
                return
            if not re.match(gps_time_pattern, end):
                self._append_output(                    f"⚠️ Неверный формат конца: {end}\n"                    f"   Ожидается формат GPS времени: YYYY:MM:DD:HH:MM:SS.f\n"                    f"   Например: 2024:09:22:01:30:01.0",                     "warning"                )
                return
        self._controller.on_interval_manually_changed(start, end)
        self._btn_interval_confirm.config(bg=Theme.ACCENT_GREEN)
        self._root.after(200, lambda: self._btn_interval_confirm.config(bg=Theme.ACCENT_BLUE))
        self._append_output(f"💾 Интервал сохранён: {start} - {end}", "success")
    def _create_angle_section(self, parent):
        angle_frame = tk.Frame(parent, bg=Theme.BG_PRIMARY)
        angle_frame.pack(fill=tk.X, pady=8)
        tk.Label(            angle_frame,            text="📐 Угол отсечения:",            font=("Segoe UI", 11, "bold"),            bg=Theme.BG_PRIMARY,            fg=Theme.FG_PRIMARY,            width=18,            anchor="w",        ).pack(side=tk.LEFT)
        self._entry_angle = tk.Entry(            angle_frame,            width=6,            font=("Consolas", 12, "bold"),            justify="center",            bg=Theme.BG_SECONDARY,            fg=Theme.ACCENT_BLUE,            bd=1,            relief=tk.SOLID,            highlightcolor=Theme.ACCENT_BLUE,            highlightthickness=1,        )
        self._entry_angle.pack(side=tk.LEFT, padx=(0, 5))
        self._entry_angle.insert(0, "7.0")
        tk.Label(            angle_frame,            text="°",            font=("Segoe UI", 12, "bold"),            bg=Theme.BG_PRIMARY,            fg=Theme.FG_PRIMARY        ).pack(side=tk.LEFT, padx=(0, 20))
        ModernButton(
            angle_frame,
            text="💾 Угол",
            bg=Theme.ACCENT_BLUE,
            fg="white",
            command=self._controller.on_update_cutoff_angle,
            font=("Segoe UI", 10),
            padx=10,
            pady=4,
        ).pack(side=tk.LEFT, padx=(0, 10))
        ModernButton(            angle_frame,            text="🚫 Исключить спутники",            bg=Theme.ACCENT_PURPLE,            fg="white",            command=self._controller.on_show_gps_exclusion_dialog,            font=("Segoe UI", 10),            padx=16,            pady=6,        ).pack(side=tk.LEFT)
    def _create_output_panel(self, parent) -> None:
        frame = tk.Frame(            parent,             bg=Theme.BG_SECONDARY,             bd=1,             relief=tk.SOLID,            highlightbackground=Theme.BORDER,            highlightthickness=1        )
        frame.pack(fill=tk.BOTH, expand=True)
        self._create_output_header(frame)
        self._create_output_text_area(frame)
        self._print_welcome()
    def _create_output_header(self, parent):
        header = tk.Frame(parent, bg=Theme.BG_SECONDARY)
        header.pack(fill=tk.X, padx=12, pady=8)
        tk.Label(            header,            text="📋 Консоль вывода",            font=("Segoe UI", 13, "bold"),            bg=Theme.BG_SECONDARY,            fg=Theme.FG_PRIMARY,        ).pack(side=tk.LEFT)
        ModernButton(            header,            text="🧹 Очистить",            command=self.clear_output,            padx=12,            pady=4,            font=("Segoe UI", 10),        ).pack(side=tk.RIGHT, padx=2)
        ModernButton(            header,            text="📋 Копировать",            command=self._copy_output,            padx=12,            pady=4,            font=("Segoe UI", 10),        ).pack(side=tk.RIGHT, padx=2)
    def _create_output_text_area(self, parent):
        self._output_text = tk.Text(            parent,            wrap=tk.WORD,            font=("Consolas", 11),            bg=Theme.BG_SECONDARY,            fg=Theme.FG_PRIMARY,            relief=tk.FLAT,            padx=12,            pady=12,        )
        scrollbar = tk.Scrollbar(parent, command=self._output_text.yview)
        self._output_text.configure(yscrollcommand=scrollbar.set)
        self._output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    def _create_status_panel(self, parent) -> None:
        frame = tk.Frame(            parent,             bg=Theme.BG_SECONDARY,             height=32,            highlightbackground=Theme.BORDER,            highlightthickness=1        )
        frame.pack(fill=tk.X)
        frame.pack_propagate(False)
        self._progress_bar = ttk.Progressbar(            frame,            mode='indeterminate',            style='Accent.Horizontal.TProgressbar',            length=220,        )
        self._progress_bar.pack(side=tk.LEFT, padx=15, pady=5)
        self._status_var = tk.StringVar(value="✅ Готов к работе")
        tk.Label(            frame,            textvariable=self._status_var,            font=("Segoe UI", 10),            bg=Theme.BG_SECONDARY,            fg=Theme.FG_SECONDARY,        ).pack(side=tk.RIGHT, padx=20)
    def _on_browse_file(self, key: str, extension: str) -> str:
        initial_dir = UIPersistence.get_last_dir()
        if not initial_dir:
            initial_dir = self._controller.script_dir
        path = filedialog.askopenfilename(            title=f"Выберите файл - {key}",            filetypes=[(f"{extension} файлы", f"*{extension}"), ("Все файлы", "*.*")],            initialdir=initial_dir,        )
        if path:
            UIPersistence.set_last_dir(path)
            self._controller.on_file_selected(key, path)
        return path or ""
    def _on_stitch_files(self, source_key: str = "rover") -> None:
        self._current_stitch_target = source_key
        initial_dir = UIPersistence.get_last_dir()
        if not initial_dir:
            initial_dir = self._controller.script_dir
        input_files = filedialog.askopenfilenames(            title="Выберите JPS файлы для сшивания",            filetypes=[("JPS файлы", "*.jps"), ("Все файлы", "*.*")],            initialdir=initial_dir,        )
        if not input_files or len(input_files) < 2:
            messagebox.showwarning(                "Внимание",                "Необходимо выбрать минимум 2 файла",                parent=self._root            )
            return
        UIPersistence.set_last_dir(input_files[0])
        output_file = filedialog.asksaveasfilename(            title="Сохранить сшитый JPS файл как",            defaultextension=".jps",            filetypes=[("JPS файлы", "*.jps"), ("Все файлы", "*.*")],            initialdir=UIPersistence.get_last_dir(),            initialfile="merged.jps",        )
        if output_file:
            UIPersistence.set_last_dir(output_file)
            self._controller.on_stitch_jps(                list(input_files),                output_file,                target_key=source_key            )
    def _on_open_working_dir(self) -> None:
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
        from view.dialogs import TransformFileDialog
        initial_dir = UIPersistence.get_last_dir()
        if not initial_dir:
            from core.app_context import APP_CONTEXT
            initial_dir = str(APP_CONTEXT.working_dir)
        dialog = TransformFileDialog(            self._root,            initial_dir,            self._controller.on_transform_files,        )
        dialog.show()
    def _on_about(self) -> None:
        from core.app_context import APP_CONTEXT
        about_text = f"""
🚀 SR2NAV GUI версия 1.0.0              
Обработка GNSS данных           
👨‍💻 kurakov@aerogeo.ru
📅 © 2026
        """
        messagebox.showinfo(
            "О программе",
            about_text.strip(),
            parent=self._root
            )
    def _on_help_readme_exe(self) -> None:
        """
        Показывает справку для пользователя .exe из файла README_EXE.md.
        """
        try:
            from core.app_context import APP_CONTEXT
            help_path = APP_CONTEXT.working_dir / "README_EXE.md"
            if not help_path.exists():
                messagebox.showwarning(
                    "Справка",
                    "Файл README_EXE.md не найден в рабочей директории.\n"
                    "Положите его рядом с программой и повторите попытку.",
                    parent=self._root,
                )
                return
            content = help_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            messagebox.showerror(
                "Справка",
                f"Не удалось прочитать README_EXE.md:\n{e}",
                parent=self._root,
            )
            return
        help_window = tk.Toplevel(self._root)
        help_window.title("Помощь — SR2NAV GUI (.exe)")
        help_window.configure(bg=Theme.BG_PRIMARY)
        help_window.geometry("900x700")
        help_window.minsize(700, 500)
        help_window.transient(self._root)
        main = tk.Frame(help_window, bg=Theme.BG_PRIMARY, padx=10, pady=10)
        main.pack(fill=tk.BOTH, expand=True)
        title_label = tk.Label(
            main,
            text="SR2NAV GUI — инструкция по запуску .exe",
            font=("Segoe UI", 12, "bold"),
            bg=Theme.BG_PRIMARY,
            fg=Theme.FG_PRIMARY,
            anchor="w",
        )
        title_label.pack(fill=tk.X, pady=(0, 8))
        container = tk.Frame(main, bg=Theme.BG_PRIMARY)
        container.pack(fill=tk.BOTH, expand=True)
        text_widget = tk.Text(
            container,
            wrap=tk.WORD,
            font=("Consolas", 10),
            bg=Theme.BG_SECONDARY,
            fg=Theme.FG_PRIMARY,
            relief=tk.FLAT,
            padx=10,
            pady=10,
        )
        scrollbar = tk.Scrollbar(container, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text_widget.insert(tk.END, content)
        text_widget.config(state=tk.DISABLED)
        btn_frame = tk.Frame(main, bg=Theme.BG_PRIMARY)
        btn_frame.pack(fill=tk.X, pady=(8, 0))
        ModernButton(
            btn_frame,
            text="Закрыть",
            command=help_window.destroy,
            width=12,
        ).pack(side=tk.RIGHT)
    def _on_terminate_with_confirmation(self):
        result = messagebox.askyesno(
            "⏹ Подтверждение остановки",
            "Вы действительно хотите остановить текущий процесс?\n\n",
            "⚠️ ВНИМАНИЕ:\n",
            "• Все незавершенные расчеты будут прерваны\n",
            "• Результаты могут быть неполными\n\n",
            "Продолжить?",
            parent=self._root,
            icon='warning'
            )
        if result:
            self.set_status("⏹ Остановка процесса...")
            self._controller.on_terminate_process()
    def _copy_output(self) -> None:
        if self._output_text:
            content = self._output_text.get(1.0, tk.END)
            self._root.clipboard_clear()
            self._root.clipboard_append(content)
            self.set_status("📋 Скопировано")
            self._root.after(2000, lambda: self.set_status("✅ Готов к работе"))
    def _on_exit(self):
        self._on_closing()
    def _auto_fill_standard_files(self) -> None:
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
        try:
            queue = self._controller.message_queue
            processed = 0
            while not queue.empty() and processed < 20:
                try:
                    msg = queue.get_nowait()
                    # DEBUG-сообщения оставляем в логике приложения, но не выводим в окно UI
                    if msg.level != MessageLevel.DEBUG:
                        self._append_output(msg.formatted, msg.level.tk_tag)
                    processed += 1
                except queue.Empty:
                    break
        except Exception as e:
            print(f"Ошибка в poll_message_queue: {e}")
        self._root.after(100, self._poll_message_queue)
    def _append_output(self, text: str, tag: str = None) -> None:
        if self._output_text:
            self._output_text.insert(tk.END, text + "\n", tag if tag else ())
            self._output_text.see(tk.END)
    def _print_welcome(self) -> None:
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