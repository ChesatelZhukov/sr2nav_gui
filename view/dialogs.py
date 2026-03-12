import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Callable, Optional, Dict, List, Any, Set
import os
from view.themes import Theme
from view.widgets import ModernButton
from view.persistence import UIPersistence
class GPSExclusionDialog:
    ALL_SATELLITES = [f"G{i:02d}" for i in range(1, 33)]
    def __init__(        self,         parent: tk.Tk,         initial_excluded: Set[str],        on_save_callback: Callable[[Set[str]], None]    ):
        self.parent = parent
        self.initial_excluded = initial_excluded.copy() if initial_excluded else set()
        self.on_save_callback = on_save_callback
        self._vars: Dict[str, tk.BooleanVar] = {}
        self.result: Optional[Set[str]] = None
        self._create_dialog()
    def _create_dialog(self):
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Исключение спутников GPS")
        self.dialog.geometry("550x600")
        self.dialog.resizable(False, False)
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        self.dialog.configure(bg=Theme.BG_PRIMARY)
        self.dialog.update_idletasks()
        x = self.parent.winfo_rootx() + (self.parent.winfo_width() - 550) // 2
        y = self.parent.winfo_rooty() + (self.parent.winfo_height() - 600) // 2
        self.dialog.geometry(f"+{x}+{y}")
        self._create_widgets()
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_cancel)
    def _create_widgets(self):
        main = tk.Frame(self.dialog, bg=Theme.BG_PRIMARY, padx=20, pady=20)
        main.pack(fill=tk.BOTH, expand=True)
        tk.Label(            main,            text="Выберите спутники для ИСКЛЮЧЕНИЯ",            font=("Segoe UI", 12, "bold"),            bg=Theme.BG_PRIMARY,            fg=Theme.FG_PRIMARY,        ).pack(pady=(0, 10))
        tk.Label(            main,            text="Снимите галочку, чтобы исключить спутник из обработки",            font=("Segoe UI", 9),            bg=Theme.BG_PRIMARY,            fg=Theme.FG_SECONDARY,        ).pack(pady=(0, 15))
        container = tk.Frame(main, bg=Theme.BG_PRIMARY)
        container.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(            container,             bg=Theme.BG_PRIMARY,             highlightthickness=0        )
        scrollbar = tk.Scrollbar(            container,             orient="vertical",             command=canvas.yview        )
        scrollable = tk.Frame(canvas, bg=Theme.BG_PRIMARY)
        scrollable.bind(            "<Configure>",            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))        )
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        for i, sat in enumerate(self.ALL_SATELLITES):
            row = i // 5
            col = i % 5
            if col == 0:
                row_frame = tk.Frame(scrollable, bg=Theme.BG_PRIMARY)
                row_frame.grid(row=row, column=0, sticky="w", pady=2)
            var = tk.BooleanVar(value=sat not in self.initial_excluded)
            self._vars[sat] = var
            cb = tk.Checkbutton(
                row_frame if col == 0 else row_frame,
                text=sat,
                variable=var,
                bg=Theme.BG_PRIMARY,
                fg=Theme.FG_PRIMARY,
                activebackground=Theme.HOVER,
                activeforeground=Theme.FG_PRIMARY,
                selectcolor=Theme.BG_PRIMARY,
                font=("Consolas", 10),
            )
            cb.grid(row=0, column=col, padx=10, pady=2)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        btn_frame = tk.Frame(main, bg=Theme.BG_PRIMARY)
        btn_frame.pack(fill=tk.X, pady=(15, 0))
        ModernButton(            btn_frame,            text="✓ Выбрать все",            command=self._select_all,            width=12,        ).pack(side="left", padx=(0, 5))
        ModernButton(            btn_frame,            text="✗ Сбросить все",            command=self._deselect_all,            width=12,        ).pack(side="left")
        ModernButton(            btn_frame,            text="Отмена",            command=self._on_cancel,            width=12,        ).pack(side="right", padx=(5, 0))
        ModernButton(            btn_frame,            text="Сохранить",            command=self._on_save,            width=12,            bg=Theme.ACCENT_BLUE,            fg="white",        ).pack(side="right")
    def _select_all(self):
        for var in self._vars.values():
            var.set(True)
    def _deselect_all(self):
        for var in self._vars.values():
            var.set(False)
    def _on_save(self):
        excluded = {            sat for sat, var in self._vars.items()            if not var.get()        }
        self.result = excluded
        self.on_save_callback(excluded)                      
        self.dialog.destroy()
    def _on_cancel(self):
        self.result = None
        self.dialog.destroy()
    def show(self) -> Optional[Set[str]]:
        self.parent.wait_window(self.dialog)
        return self.result
class TransformFileDialog:
    FILE_TYPES = [        ("Phase_L1.VEL", "ROVER_KIN", "📊 Фазовое L1"),        ("Phase_IO.VEL", "ROVER_KIN", "📊 Фазовое IO"),        ("PhaseIOS.VEL", "ROVER_KIN", "📊 Фазовое IOS"),        ("PhaseL1S.VEL", "ROVER_KIN", "📊 Фазовое L1S"),        ("Base_Std.QC", "BASE_STD", "🏠 Стандарт базы"),        ("Rover_Std.QC", "ROVER_STD", "🚙 Стандарт ровера"),    ]
    def __init__(        self,         parent,         initial_dir: str,        on_transform_callback: Callable[[List[str], str], None]    ):
        self.parent = parent
        self.current_dir = Path(initial_dir)
        self.on_transform_callback = on_transform_callback
        self._vars: Dict[str, tk.BooleanVar] = {}
        self._checkboxes: Dict[str, tk.Checkbutton] = {}
        self._file_paths: Dict[str, Path] = {}
        self._create_dialog()
    def _create_dialog(self):
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
        main = tk.Frame(self.dialog, bg=Theme.BG_PRIMARY, padx=20, pady=20)
        main.pack(fill=tk.BOTH, expand=True)
        tk.Label(            main,            text="🔄 Трансформация файлов в формат TBL",            font=("Segoe UI", 14, "bold"),            bg=Theme.BG_PRIMARY,            fg=Theme.FG_PRIMARY,        ).pack(anchor="w", pady=(0, 10))
        self._create_folder_selection(main)
        tk.Frame(main, height=1, bg=Theme.BORDER).pack(fill=tk.X, pady=(0, 15))
        self._create_file_list_header(main)
        self._create_file_list(main)
        self._create_action_buttons(main)
    def _create_folder_selection(self, parent):
        source_frame = tk.Frame(parent, bg=Theme.BG_PRIMARY)
        source_frame.pack(fill=tk.X, pady=(0, 15))
        tk.Label(            source_frame,            text="📂 Выберите папку с файлами:",            font=("Segoe UI", 10, "bold"),            bg=Theme.BG_PRIMARY,            fg=Theme.FG_PRIMARY,        ).pack(anchor="w")
        dir_container = tk.Frame(source_frame, bg=Theme.BG_PRIMARY)
        dir_container.pack(fill=tk.X, pady=(5, 0))
        self._dir_var = tk.StringVar(value=str(self.current_dir))
        self._dir_entry = tk.Entry(            dir_container,            textvariable=self._dir_var,            font=("Consolas", 10),            bg=Theme.BG_SECONDARY,            fg=Theme.FG_PRIMARY,            relief=tk.SOLID,            bd=1,            state='readonly',            readonlybackground=Theme.BG_SECONDARY,        )
        self._dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ModernButton(            dir_container,            text="📂 Выбрать папку...",            command=self._on_browse_source_dir,            width=15,            font=("Segoe UI", 10),            bg=Theme.ACCENT_BLUE,            fg="white",        ).pack(side=tk.RIGHT)
        self._tbl_info_label = tk.Label(            source_frame,            text="",            font=("Consolas", 9),            bg=Theme.BG_PRIMARY,            fg=Theme.ACCENT_GREEN,            anchor="w",        )
        self._tbl_info_label.pack(anchor="w", pady=(5, 0))
    def _create_file_list_header(self, parent):
        list_header = tk.Frame(parent, bg=Theme.BG_PRIMARY)
        list_header.pack(fill=tk.X, pady=(0, 10))
        tk.Label(            list_header,            text="📋 Доступные файлы:",            font=("Segoe UI", 11, "bold"),            bg=Theme.BG_PRIMARY,            fg=Theme.FG_PRIMARY,        ).pack(side=tk.LEFT)
        self._file_count_label = tk.Label(            list_header,            text="(выберите папку)",            font=("Segoe UI", 10),            bg=Theme.BG_PRIMARY,            fg=Theme.FG_SECONDARY,        )
        self._file_count_label.pack(side=tk.LEFT, padx=(10, 0))
        btn_frame = tk.Frame(list_header, bg=Theme.BG_PRIMARY)
        btn_frame.pack(side=tk.RIGHT)
        ModernButton(            btn_frame,            text="✓ Все",            command=self._select_all,            width=5,            font=("Segoe UI", 9),            padx=8,            pady=2,        ).pack(side=tk.LEFT, padx=2)
        ModernButton(            btn_frame,            text="✗ Сброс",            command=self._deselect_all,            width=5,            font=("Segoe UI", 9),            padx=8,            pady=2,        ).pack(side=tk.LEFT, padx=2)
    def _create_file_list(self, parent):
        container = tk.Frame(parent, bg=Theme.BG_PRIMARY)
        container.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(            container,            bg=Theme.BG_PRIMARY,            highlightthickness=0,        )
        scrollbar = tk.Scrollbar(            container,            orient="vertical",            command=canvas.yview,        )
        self.scrollable = tk.Frame(canvas, bg=Theme.BG_PRIMARY)
        self.scrollable.bind(            "<Configure>",            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))        )
        canvas.create_window((0, 0), window=self.scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._placeholder = tk.Label(            self.scrollable,            text="👆 Выберите папку для отображения файлов",            font=("Segoe UI", 12),            bg=Theme.BG_PRIMARY,            fg=Theme.FG_SECONDARY,        )
        self._placeholder.pack(expand=True, pady=50)
    def _create_action_buttons(self, parent):
        btn_frame_bottom = tk.Frame(parent, bg=Theme.BG_PRIMARY)
        btn_frame_bottom.pack(fill=tk.X, pady=(20, 0))
        ModernButton(            btn_frame_bottom,            text="🔄 Обновить список",            command=self._refresh_file_list,            width=15,            font=("Segoe UI", 10),            bg=Theme.ACCENT_BLUE,            fg="white",        ).pack(side="left", padx=(0, 5))
        ModernButton(            btn_frame_bottom,            text="❌ Закрыть",            command=self._on_close,            width=10,            font=("Segoe UI", 10),        ).pack(side="right", padx=(5, 0))
        ModernButton(            btn_frame_bottom,            text="🔄 Трансформировать",            bg=Theme.ACCENT_GREEN,            fg="white",            command=self._on_transform,            width=18,            font=("Segoe UI", 10, "bold"),            padx=16,            pady=6,        ).pack(side="right", padx=(0, 5))
    def _on_browse_source_dir(self):
        initial_dir = str(self.current_dir)
        if not os.path.exists(initial_dir):
            initial_dir = UIPersistence.get_last_dir()
        self.dialog.grab_release()
        directory = filedialog.askdirectory(            title="Выберите папку с файлами",            initialdir=initial_dir,            parent=self.dialog        )
        self.dialog.grab_set()
        if directory:
            self.current_dir = Path(directory)
            self._dir_var.set(str(self.current_dir))
            self._update_tbl_info()
            self._refresh_file_list()                                 
            UIPersistence.set_last_dir(directory)
    def _update_tbl_info(self):
        tbl_path = self.current_dir / "tbl"
        self._tbl_info_label.config(            text=f"📁 Папка 'tbl' будет создана: {tbl_path}",            fg=Theme.ACCENT_GREEN        )
    def _find_files_in_current_dir(self) -> Dict[str, Path]:
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
        if hasattr(self, '_placeholder') and self._placeholder:
            self._placeholder.destroy()
            self._placeholder = None
        for widget in self.scrollable.winfo_children():
            widget.destroy()
        self._vars.clear()
        self._checkboxes.clear()
        self._file_paths.clear()
        if not self.current_dir.exists():
            tk.Label(                self.scrollable,                text=f"❌ Папка не существует",                font=("Segoe UI", 12),                bg=Theme.BG_PRIMARY,                fg=Theme.ERROR,            ).pack(expand=True, pady=50)
            self._file_count_label.config(text="(папка не найдена)")
            return
        self._update_tbl_info()
        self._file_paths = self._find_files_in_current_dir()
        if not self._file_paths:
            tk.Label(                self.scrollable,                text="❌ В папке нет нужных файлов",                font=("Segoe UI", 12),                bg=Theme.BG_PRIMARY,                fg=Theme.WARNING,            ).pack(expand=True, pady=50)
            self._file_count_label.config(text="(0 файлов)")
            return
        for filename, file_path in sorted(self._file_paths.items()):
            description = next((desc for f, _, desc in self.FILE_TYPES if f == filename), filename)
            var = tk.BooleanVar(value=True)
            self._vars[filename] = var
            row = tk.Frame(self.scrollable, bg=Theme.BG_PRIMARY)
            row.pack(fill=tk.X, pady=4)
            cb = tk.Checkbutton(                row,                variable=var,                bg=Theme.BG_PRIMARY,                fg=Theme.FG_PRIMARY,                activebackground=Theme.HOVER,                selectcolor="white",                font=("Segoe UI", 11),            )
            cb.pack(side="left")
            self._checkboxes[filename] = cb
            self._create_file_info(row, filename, description, file_path)
        self._file_count_label.config(text=f"({len(self._file_paths)} файлов)")
    def _create_file_info(self, parent, filename: str, description: str, file_path: Path):
        info = tk.Frame(parent, bg=Theme.BG_PRIMARY)
        info.pack(side="left", padx=(10, 0), fill=tk.X, expand=True)
        tk.Label(            info,            text=description,            font=("Segoe UI", 11, "bold"),            bg=Theme.BG_PRIMARY,            fg=Theme.FG_PRIMARY,            anchor="w",        ).pack(anchor="w")
        tk.Label(            info,            text=filename,            font=("Consolas", 9),            bg=Theme.BG_PRIMARY,            fg=Theme.FG_SECONDARY,            anchor="w",        ).pack(anchor="w")
        size = file_path.stat().st_size
        size_str = f"{size / 1024:.0f} KB" if size < 1024*1024 else f"{size / 1024 / 1024:.1f} MB"
        tk.Label(            info,            text=f"✓ {size_str}",            font=("Segoe UI", 9),            bg=Theme.BG_PRIMARY,            fg=Theme.SUCCESS,        ).pack(anchor="w")
    def _select_all(self):
        for var in self._vars.values():
            var.set(True)
    def _deselect_all(self):
        for var in self._vars.values():
            var.set(False)
    def _on_transform(self):
        selected = [            f for f, var in self._vars.items()            if var.get()        ]
        if not selected:
            messagebox.showwarning(                "Внимание",                "Не выбрано ни одного файла",                parent=self.dialog            )
            return
        if not self.current_dir.exists():
            messagebox.showerror(                "Ошибка",                f"Папка не существует",                parent=self.dialog            )
            return
        self.on_transform_callback(selected, str(self.current_dir))
        self._on_close()
    def _on_close(self):
        self.dialog.destroy()
    def show(self):
        self.dialog.wait_window()