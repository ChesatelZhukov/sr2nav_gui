import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
from pathlib import Path
import pyperclip
import math
import gc
import weakref
import logging
from view.themes import LIGHT_THEME
from view.widgets import ModernButton, InteractiveZoom
from core.app_context import APP_CONTEXT
logger = logging.getLogger(__name__)
class InstanceCounter:
    _instances = weakref.WeakSet()
    _count = 0
    def __init__(self):
        self.__class__._count += 1
        self.instance_id = self.__class__._count
        self.__class__._instances.add(self)
        logger.debug(f"[{self.__class__.__name__}] Создан экземпляр #{self.instance_id}. Активных: {self.get_instance_count()}, Всего создано: {self.get_total_created()}")
    def __del__(self):
        logger.debug(f"[{self.__class__.__name__}] Экземпляр #{getattr(self, 'instance_id', 'N/A')} удаляется.")
    @classmethod
    def get_instance_count(cls):
        return len(cls._instances)
    @classmethod
    def get_total_created(cls):
        return cls._count
class VelocityAnalysisWindow(InstanceCounter):
    PLOT_COLORS = [
        LIGHT_THEME.ACCENT_RED,
        LIGHT_THEME.ACCENT_GREEN,
        LIGHT_THEME.WARNING,
        LIGHT_THEME.INFO,
        LIGHT_THEME.ACCENT_ORANGE,
        LIGHT_THEME.ACCENT_PURPLE,
        LIGHT_THEME.ACCENT_CYAN,
        LIGHT_THEME.DEBUG,
        LIGHT_THEME.SUCCESS,
        LIGHT_THEME.FG_SECONDARY,
    ]
    def __init__(self, parent, controller):
        super().__init__()                                      
        self.parent = parent
        self.controller = controller
        self.current_dir = None
        self.available_projects: Dict[str, Path] = {}                                 
        self.analysis_results = None
        self.summary_results = None
        self.interactive_zoom = None
        self.current_fig = None
        self.current_canvas = None
        self.plot_lines = {}
        self.file_vars: Dict[str, tk.BooleanVar] = {}
        self._project_var = None
        self._project_combo = None
        self.progress_frame = None
        self.progress_label = None
        self.progress_bar = None
        self.status_label = None
        self.file_count_label = None
        self.file_frame = None
        self.file_container = None
        self.notebook = None
        self.plot_frame = None
        self.table_frame = None
        self.summary_frame = None
        self.qc_plot_frame = None
        self.qc_fig = None
        self.qc_canvas = None
        self.context_menu = None
        self.last_click_coords = None
        self.last_click_time = None
        self.window = tk.Toplevel(parent)
        self.window.title("Анализ скоростей VEL файлов")
        self.window.geometry("1600x1100")
        self.window.minsize(1400, 900)
        self.window.configure(bg=LIGHT_THEME.BG_PRIMARY)
        self.center_window()
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        self.create_widgets()
        self._scan_available_projects()                                  
    def on_close(self):
        logger.info(f"Закрытие окна VelocityAnalysisWindow #{getattr(self, 'instance_id', 'N/A')}")
        try:
            if self.interactive_zoom:
                self.interactive_zoom.cleanup()
                self.interactive_zoom = None
            if self.current_fig:
                plt.close(self.current_fig)
                self.current_fig = None
            if self.current_canvas:
                self.current_canvas.get_tk_widget().destroy()
                self.current_canvas = None
            self.window.grab_release()
            self.window.destroy()
            gc.collect()
            logger.debug(f"Окно #{self.instance_id} закрыто. Активных окон Velocity: {self.get_instance_count()}")
        except Exception as e:
            logger.error(f"Ошибка при закрытии окна: {e}")
            try:
                self.window.destroy()
            except:
                pass
    def center_window(self):
        self.window.update_idletasks()
        width = self.window.winfo_width() or 1600
        height = self.window.winfo_height() or 1100
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
        main_container = tk.Frame(self.window, bg=LIGHT_THEME.BG_PRIMARY)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.create_header(main_container)
        self.create_folder_selection(main_container)
        self.create_progress_bar(main_container)
        self.create_notebook(main_container)
        self.create_file_selector(main_container)
        self.create_status_bar(main_container)
    def create_header(self, parent):
        header = tk.Frame(parent, bg=LIGHT_THEME.BG_PRIMARY)
        header.pack(fill=tk.X, pady=(0, 10))
        tk.Label(
            header,
            text="Анализ скоростей VEL файлов",
            font=("Arial", 14, "bold"),
            fg=LIGHT_THEME.FG_PRIMARY,
            bg=LIGHT_THEME.BG_PRIMARY,
        ).pack(side=tk.LEFT)
        btn_frame = tk.Frame(header, bg=LIGHT_THEME.BG_PRIMARY)
        btn_frame.pack(side=tk.RIGHT)
        ModernButton(
            btn_frame,
            text="⟲ Сбросить зум",
            command=self.reset_zoom,
            width=12,
            bg=LIGHT_THEME.ACCENT_ORANGE,
            fg="white",
            font=("Segoe UI", 10),
        ).pack(side=tk.LEFT, padx=2)
        ModernButton(
            btn_frame,
            text="📊 Экспорт CSV",
            command=self.on_export,
            width=12,
            bg=LIGHT_THEME.ACCENT_GREEN,
            fg="white",
            font=("Segoe UI", 10),
        ).pack(side=tk.LEFT, padx=2)
        ModernButton(
            btn_frame,
            text="✓ Выбрать все",
            command=self.select_all_files,
            width=12,
            bg=LIGHT_THEME.ACCENT_BLUE,
            fg="white",
            font=("Segoe UI", 10),
        ).pack(side=tk.LEFT, padx=2)
        ModernButton(
            btn_frame,
            text="✗ Сбросить все",
            command=self.deselect_all_files,
            width=12,
            bg=LIGHT_THEME.BG_SECONDARY,
            fg=LIGHT_THEME.FG_PRIMARY,
            font=("Segoe UI", 10),
        ).pack(side=tk.LEFT, padx=2)
    def create_folder_selection(self, parent):
        folder_frame = tk.Frame(parent, bg=LIGHT_THEME.BG_PRIMARY)
        folder_frame.pack(fill=tk.X, pady=(0, 10))
        tk.Label(
            folder_frame,
            text="📂 Выберите проект:",
            font=("Segoe UI", 10, "bold"),
            bg=LIGHT_THEME.BG_PRIMARY,
            fg=LIGHT_THEME.FG_PRIMARY,
        ).pack(anchor="w")
        dir_container = tk.Frame(folder_frame, bg=LIGHT_THEME.BG_PRIMARY)
        dir_container.pack(fill=tk.X, pady=(5, 0))
        self._project_var = tk.StringVar()
        self._project_combo = ttk.Combobox(            dir_container,            textvariable=self._project_var,            state='readonly',            font=("Segoe UI", 10),            width=50        )
        self._project_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self._project_combo.bind('<<ComboboxSelected>>', self._on_project_selected)
        ModernButton(
            dir_container,
            text="📂 Другая папка...",
            command=self._on_browse_folder,
            width=15,
            font=("Segoe UI", 10),
            bg=LIGHT_THEME.ACCENT_BLUE,
            fg="white",
        ).pack(side=tk.RIGHT)
        tk.Frame(parent, height=1, bg=LIGHT_THEME.BORDER).pack(fill=tk.X, pady=(0, 10))
    def _scan_available_projects(self) -> None:
        self.available_projects.clear()
        base_dir = APP_CONTEXT.working_dir
        if not base_dir.exists():
            return
        for item in base_dir.iterdir():
            if item.is_dir():
                vel_files = list(item.glob("*.VEL")) + list(item.glob("*.[Vv][Ee][Ll]"))
                if vel_files:
                    self.available_projects[item.name] = item
        if self.available_projects:
            project_names = sorted(self.available_projects.keys())
            self._project_combo['values'] = project_names
            self._project_var.set(project_names[0])
            self.current_dir = self.available_projects[project_names[0]]
            self._load_data_from_folder()
        else:
            self._project_combo['values'] = ["(Нет проектов)"]
            self._project_var.set("(Нет проектов)")
            self.show_folder_selection_prompt()
    def _on_project_selected(self, event=None) -> None:
        project_name = self._project_var.get()
        if project_name and project_name in self.available_projects:
            self.current_dir = self.available_projects[project_name]
            self._load_data_from_folder()
    def _on_browse_folder(self) -> None:
        from view.main_window import UIPersistence
        initial_dir = UIPersistence.get_last_dir()
        if not initial_dir:
            initial_dir = str(APP_CONTEXT.working_dir)
        directory = filedialog.askdirectory(            title="Выберите папку с VEL файлами",            initialdir=initial_dir,            parent=self.window        )
        if directory:
            self.current_dir = Path(directory)
            UIPersistence.set_last_dir(directory)
            folder_name = self.current_dir.name
            project_key = f"{folder_name} ({self.current_dir.parent.name})"
            self.available_projects[project_key] = self.current_dir
            project_names = sorted(self.available_projects.keys())
            self._project_combo['values'] = project_names
            self._project_var.set(project_key)
            self._load_data_from_folder()
        self.window.lift()
    def _load_data_from_folder(self):
        self.show_loading(f"Сканирование {self.current_dir.name}...")
        self.controller.request_velocity_analysis(self, str(self.current_dir))
    def create_notebook(self, parent):
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        self.plot_frame = tk.Frame(self.notebook, bg=LIGHT_THEME.BG_PRIMARY)
        self.notebook.add(self.plot_frame, text="Графики VEL (RmsVel, Hei, Hei 4th Diff)")
        self.qc_plot_frame = tk.Frame(self.notebook, bg=LIGHT_THEME.BG_PRIMARY)
        self.notebook.add(self.qc_plot_frame, text="QC (PDOP)")
        self.table_frame = tk.Frame(self.notebook, bg=LIGHT_THEME.BG_PRIMARY)
        self.notebook.add(self.table_frame, text="Результаты")
        self.summary_frame = tk.Frame(self.notebook, bg=LIGHT_THEME.BG_PRIMARY)
        self.notebook.add(self.summary_frame, text="Сводка")
    def create_file_selector(self, parent):
        self.file_frame = tk.Frame(parent, bg=LIGHT_THEME.BG_SECONDARY, height=40)
        self.file_frame.pack(fill=tk.X, pady=(10, 0))
        self.file_frame.pack_propagate(False)
        self.file_container = tk.Frame(self.file_frame, bg=LIGHT_THEME.BG_SECONDARY)
        self.file_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
    def create_progress_bar(self, parent):
        self.progress_frame = tk.Frame(parent, bg=LIGHT_THEME.BG_PRIMARY)
        self.progress_frame.pack(fill=tk.X, pady=(0, 10))
        self.progress_label = tk.Label(
            self.progress_frame,
            text="",
            font=("Arial", 9),
            fg=LIGHT_THEME.FG_SECONDARY,
            bg=LIGHT_THEME.BG_PRIMARY,
        )
        self.progress_label.pack()
        self.progress_bar = ttk.Progressbar(            self.progress_frame,            mode='indeterminate'        )
        self.progress_bar.pack(fill=tk.X)
        self.progress_frame.pack_forget()
    def create_status_bar(self, parent):
        status = tk.Frame(parent, bg=LIGHT_THEME.BG_SECONDARY, height=24)
        status.pack(fill=tk.X, pady=(5, 0))
        status.pack_propagate(False)
        self.status_label = tk.Label(
            status,
            text="Готов",
            font=("Arial", 9),
            fg=LIGHT_THEME.FG_SECONDARY,
            bg=LIGHT_THEME.BG_SECONDARY,
        )
        self.status_label.pack(side=tk.LEFT, padx=10)
        self.file_count_label = tk.Label(
            status,
            text="0",
            font=("Arial", 9),
            fg=LIGHT_THEME.FG_SECONDARY,
            bg=LIGHT_THEME.BG_SECONDARY,
        )
        self.file_count_label.pack(side=tk.RIGHT, padx=10)
    def show_folder_selection_prompt(self):
        for frame in [self.plot_frame, self.table_frame, self.summary_frame]:
            for widget in frame.winfo_children():
                widget.destroy()
                tk.Label(
                    frame,
                    text="👆 Выберите папку с VEL файлами в верхней панели",
                    font=("Arial", 12),
                    fg=LIGHT_THEME.FG_SECONDARY,
                    bg=LIGHT_THEME.BG_PRIMARY,
                ).pack(expand=True)
    def show_loading(self, message: str):
        if self.progress_label:
            self.progress_label.config(text=message)
        if self.progress_frame:
            self.progress_frame.pack(fill=tk.X, pady=(0, 10))
        if self.progress_bar:
            self.progress_bar.start(10)
        self.window.update()
    def hide_loading(self):
        if self.progress_bar:
            self.progress_bar.stop()
        if self.progress_frame:
            self.progress_frame.pack_forget()
    def show_error(self, error: str):
        self.hide_loading()
        if self.status_label:
            self.status_label.config(text=f"Ошибка", fg=LIGHT_THEME.ACCENT_RED)
        for frame in [self.table_frame, self.plot_frame, self.summary_frame]:
            if frame:
                for widget in frame.winfo_children():
                    widget.destroy()
                tk.Label(
                    frame,
                    text=f"❌ {error}",
                    font=("Arial", 11),
                    fg=LIGHT_THEME.ACCENT_RED,
                    bg=LIGHT_THEME.BG_PRIMARY,
                ).pack(expand=True)
    def on_refresh(self):
        self.show_loading("Обновление...")
        self.controller.request_velocity_analysis(self, str(self.current_dir))
    def on_export(self):
        if not self.analysis_results:
            messagebox.showwarning("Внимание", "Нет данных", parent=self.window)
            return
        from view.main_window import UIPersistence
        initial_dir = UIPersistence.get_last_dir() or str(self.current_dir)
        filename = filedialog.asksaveasfilename(            title="Сохранить",            defaultextension=".csv",            filetypes=[("CSV", "*.csv"), ("Все", "*.*")],            initialdir=initial_dir,            initialfile=f"velocity_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"        )
        if filename:
            UIPersistence.set_last_dir(filename)
            success = self.controller.export_velocity_analysis(filename)
            if success:
                messagebox.showinfo("Успех", f"Сохранено", parent=self.window)
            else:
                messagebox.showerror("Ошибка", "Не удалось экспортировать", parent=self.window)
    def update_results(self, results: Dict, summary: Dict):
        self.analysis_results = results
        self.summary_results = summary
        self.hide_loading()
        self.update_file_list()
        self.update_results_table()
        self.update_summary(summary)
        self.update_plots()
        self.update_qc_plot()
        file_count = len(results) if results else 0
        if self.file_count_label:
            self.file_count_label.config(text=f"{file_count} файлов")
        if self.status_label:
            if file_count > 0:
                self.status_label.config(
                    text=f"Готово: {file_count} файлов",
                    fg=LIGHT_THEME.SUCCESS,
                )
            else:
                self.status_label.config(
                    text="VEL файлы не найдены",
                    fg=LIGHT_THEME.WARNING,
                )
    def update_file_list(self):
        if self.file_container:
            for widget in self.file_container.winfo_children():
                widget.destroy()
        self.file_vars.clear()
        if not self.analysis_results or not self.file_container:
            if self.file_container:
                tk.Label(
                    self.file_container,
                    text="Нет файлов",
                    font=("Segoe UI", 10),
                    bg=LIGHT_THEME.BG_SECONDARY,
                    fg=LIGHT_THEME.FG_SECONDARY,
                ).pack(side=tk.LEFT, padx=5)
            return
        sorted_files = sorted(self.analysis_results.keys())
        for filename in sorted_files:
            var = tk.BooleanVar(value=True)
            self.file_vars[filename] = var
            display_name = filename
            if len(display_name) > 25:
                display_name = display_name[:22] + "..."
            cb = tk.Checkbutton(
                self.file_container,
                text=display_name,
                variable=var,
                command=self.update_plot_visibility,
                bg=LIGHT_THEME.BG_SECONDARY,
                fg=LIGHT_THEME.FG_PRIMARY,
                activebackground=LIGHT_THEME.HOVER,
                selectcolor=LIGHT_THEME.BG_PRIMARY,
                font=("Consolas", 9),
                anchor="w",
            )
            cb.pack(side=tk.LEFT, padx=8)
            self.create_tooltip(cb, filename)
    def create_tooltip(self, widget, text):
        def show_tooltip(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
            label = tk.Label(
                tooltip,
                text=text,
                bg=LIGHT_THEME.BG_SECONDARY,
                fg=LIGHT_THEME.FG_PRIMARY,
                relief=tk.SOLID,
                borderwidth=1,
                font=("Consolas", 8),
                padx=5,
                pady=2,
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
        for var in self.file_vars.values():
            var.set(True)
        self.update_plot_visibility()
    def deselect_all_files(self):
        for var in self.file_vars.values():
            var.set(False)
        self.update_plot_visibility()
    def get_selected_files(self) -> Set[str]:
        return {            filename for filename, var in self.file_vars.items()            if var.get()        }
    def update_results_table(self):
        if not self.table_frame:
            return
        for widget in self.table_frame.winfo_children():
            widget.destroy()
        if not self.analysis_results:
            tk.Label(
                self.table_frame,
                text="Нет данных",
                font=("Arial", 11),
                fg=LIGHT_THEME.FG_SECONDARY,
                bg=LIGHT_THEME.BG_PRIMARY,
            ).pack(expand=True)
            return
        columns = ['Файл', 'Строк', 'Время', 'V_E', 'V_N', 'V_UP', 'RmsVel', 'Hei 4th Diff']
        tree_frame = tk.Frame(self.table_frame, bg=LIGHT_THEME.BG_PRIMARY)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(
            "Treeview",
            background=LIGHT_THEME.BG_SECONDARY,
            foreground=LIGHT_THEME.FG_PRIMARY,
            fieldbackground=LIGHT_THEME.BG_SECONDARY,
            borderwidth=0,
        )
        style.map("Treeview", background=[("selected", LIGHT_THEME.SELECTED)])
        style.configure(
            "Treeview.Heading",
            background=LIGHT_THEME.BG_TERTIARY,
            foreground=LIGHT_THEME.FG_PRIMARY,
            relief="flat",
        )
        style.map("Treeview.Heading", background=[("active", LIGHT_THEME.HOVER)])
        tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show='headings',
            height=20,
        )
        widths = [200, 60, 120, 70, 70, 70, 80, 120]
        for col, width in zip(columns, widths):
            tree.heading(col, text=col)
            tree.column(col, width=width, minwidth=50, anchor='center')
        for filename, result in self.analysis_results.items():
            if isinstance(result, dict):
                data = result.get('data', {})
                stats = result.get('statistics', {})
            else:
                data = getattr(result, 'data', {})
                stats = getattr(result, 'statistics', {})
            if isinstance(data, dict):
                time_span = data.get('time_span', [0, 0])
                rows = stats.get('rows_analyzed', 0)
                max_v_e = stats.get('max_v_e', 0)
                max_v_n = stats.get('max_v_n', 0)
                max_v_up = stats.get('max_v_up', 0)
                max_rms_vel = stats.get('max_rms_vel', 0)
                max_height_4th_diff = stats.get('max_height_4th_diff', 0)
            else:
                time_span = getattr(data, 'time_span', [0, 0])
                rows = getattr(stats, 'rows_analyzed', 0)
                max_v_e = getattr(stats, 'max_v_e', 0)
                max_v_n = getattr(stats, 'max_v_n', 0)
                max_v_up = getattr(stats, 'max_v_up', 0)
                max_rms_vel = getattr(stats, 'max_rms_vel', 0)
                max_height_4th_diff = getattr(stats, 'max_height_4th_diff', 0)
            time_span_str = f"{time_span[0]:.0f}-{time_span[1]:.0f}с" if time_span and len(time_span) > 1 else "0-0с"
            display_filename = filename[:30] + "..." if len(filename) > 30 else filename
            values = [
                display_filename,
                rows,
                time_span_str,
                f"{max_v_e:.3f}",
                f"{max_v_n:.3f}",
                f"{max_v_up:.3f}",
                f"{max_rms_vel:.3f}",
                f"{max_height_4th_diff:.3f}",
            ]
            tree.insert('', 'end', values=values)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    def update_summary(self, summary: Dict):
        if not self.summary_frame:
            return
        for widget in self.summary_frame.winfo_children():
            widget.destroy()
        if not summary:
            tk.Label(
                self.summary_frame,
                text="Нет данных",
                font=("Arial", 11),
                fg=LIGHT_THEME.FG_SECONDARY,
                bg=LIGHT_THEME.BG_PRIMARY,
            ).pack(expand=True)
            return
        text_widget = tk.Text(
            self.summary_frame,
            font=("Consolas", 10),
            wrap=tk.WORD,
            bg=LIGHT_THEME.BG_SECONDARY,
            fg=LIGHT_THEME.FG_PRIMARY,
            relief=tk.FLAT,
            padx=10,
            pady=10,
        )
        scrollbar = tk.Scrollbar(self.summary_frame, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text_widget.tag_config(
            "header",
            foreground=LIGHT_THEME.ACCENT_BLUE,
            font=("Consolas", 11, "bold"),
        )
        text_widget.tag_config(
            "value",
            foreground=LIGHT_THEME.SUCCESS,
            font=("Consolas", 10, "bold"),
        )
        text_widget.tag_config("warning", foreground=LIGHT_THEME.WARNING)
        max_vel = summary.get('max_velocities', {})
        max_rms_vel = summary.get('max_rms_vel', 0)
        max_height_diff = summary.get('max_height_4th_diff', 0)
        pdop_stats = self._get_qc_pdop_stats()
        text_widget.insert(tk.END, "📊 СВОДНАЯ СТАТИСТИКА\n", "header")
        text_widget.insert(tk.END, "═"*40 + "\n\n")
        text_widget.insert(tk.END, f"📁 Файлов: ")
        text_widget.insert(tk.END, f"{summary.get('total_files', 0)}\n", "value")
        text_widget.insert(tk.END, f"\n📈 МАКСИМАЛЬНЫЕ СКОРОСТИ:\n", "header")
        text_widget.insert(tk.END, f"   V_E (Восток): ")
        text_widget.insert(tk.END, f"{max_vel.get('v_e', 0):.3f} м/с\n", "value")
        text_widget.insert(tk.END, f"   V_N (Север): ")
        text_widget.insert(tk.END, f"{max_vel.get('v_n', 0):.3f} м/с\n", "value")
        text_widget.insert(tk.END, f"   V_UP (Вертикаль): ")
        text_widget.insert(tk.END, f"{max_vel.get('v_up', 0):.3f} м/с\n", "value")
        text_widget.insert(tk.END, f"\n📊 RMS СКОРОСТЬ:\n", "header")
        text_widget.insert(tk.END, f"   Max RmsVel: ")
        text_widget.insert(tk.END, f"{max_rms_vel:.3f} м/с\n", "value")
        text_widget.insert(tk.END, f"\n📏 ВЫСОТА:\n", "header")
        text_widget.insert(tk.END, f"   Макс. 4-я разность: ")
        text_widget.insert(tk.END, f"{max_height_diff:.3f} м\n", "value")
        if pdop_stats is not None:
            text_widget.insert(tk.END, f"\n🛰 PDOP из QC:\n", "header")
            text_widget.insert(tk.END, f"   Min PDOP: ")
            text_widget.insert(tk.END, f"{pdop_stats['min']:.2f}\n", "value")
            text_widget.insert(tk.END, f"   Max PDOP: ")
            text_widget.insert(tk.END, f"{pdop_stats['max']:.2f}\n", "value")
            text_widget.insert(tk.END, f"   Mean PDOP: ")
            text_widget.insert(tk.END, f"{pdop_stats['mean']:.2f}\n", "value")
        text_widget.insert(tk.END, f"\n{'─'*40}\n")
        text_widget.insert(tk.END, f"\n", "warning")
        text_widget.config(state=tk.DISABLED)
    def update_plots(self):
        if self.current_fig:
            plt.close(self.current_fig)
            self.current_fig = None
        if self.interactive_zoom:
            self.interactive_zoom.cleanup()
            self.interactive_zoom = None
        if self.current_canvas:
            self.current_canvas.get_tk_widget().destroy()
            self.current_canvas = None
        if self.plot_frame:
            for widget in self.plot_frame.winfo_children():
                widget.destroy()
        if not self.analysis_results or not self.plot_frame:
            if self.plot_frame:
                tk.Label(
                    self.plot_frame,
                    text="Нет данных",
                    font=("Arial", 11),
                    fg=LIGHT_THEME.FG_SECONDARY,
                    bg=LIGHT_THEME.BG_PRIMARY,
                ).pack(expand=True)
            return
        selected_files = self.get_selected_files()
        if not selected_files:
            if self.plot_frame:
                tk.Label(
                    self.plot_frame,
                    text="Не выбрано файлов",
                    font=("Arial", 11),
                    fg=LIGHT_THEME.WARNING,
                    bg=LIGHT_THEME.BG_PRIMARY,
                ).pack(expand=True)
            return
        try:
            fig, axes = plt.subplots(3, 1, figsize=(20, 8), sharex=True)
            fig.patch.set_facecolor(LIGHT_THEME.BG_SECONDARY)
            self.plot_lines = {}
            axis_titles = {
                0: 'RmsVel [м/с]',
                1: 'Высота (Hei) [м]',
                2: '4-я разность высоты (Hei 4th Diff) [м]',
            }
            for idx, filename in enumerate(sorted(selected_files)):
                if filename not in self.analysis_results:
                    continue
                result = self.analysis_results[filename]
                if isinstance(result, dict):
                    data = result.get('data', {})
                else:
                    data = getattr(result, 'data', {})
                if isinstance(data, dict):
                    time = data.get('time', np.array([]))
                    rms_vel = data.get('rms_vel', np.array([]))
                    height = data.get('height', np.array([]))
                else:
                    time = getattr(data, 'time', np.array([]))
                    rms_vel = getattr(data, 'rms_vel', np.array([]))
                    height = getattr(data, 'height', np.array([]))
                if isinstance(time, list):
                    time = np.array(time)
                if isinstance(rms_vel, list):
                    rms_vel = np.array(rms_vel)
                if isinstance(height, list):
                    height = np.array(height)
                if len(time) == 0:
                    continue
                plot_time = time
                plot_rms_vel = rms_vel
                plot_height = height
                if isinstance(result, dict):
                    stats = result.get('statistics', {})
                    height_4th_diff = stats.get('height_4th_diff_array', np.array([]))
                else:
                    stats = getattr(result, 'statistics', None)
                    height_4th_diff = getattr(stats, 'height_4th_diff_array', np.array([])) if stats else np.array([])
                if height_4th_diff is None or len(height_4th_diff) == 0:
                    height_4th_diff = self.calculate_4th_diff(height)
                # Для 4‑й разности не выполняем прореживание — используем полный ряд
                plot_height_4th_diff = height_4th_diff
                color = self.PLOT_COLORS[idx % len(self.PLOT_COLORS)]
                label = filename[:12] + "..." if len(filename) > 12 else filename
                line0, = axes[0].plot(plot_time, plot_rms_vel, color=color, linewidth=1.2, label=label)
                line1, = axes[1].plot(plot_time, plot_height, color=color, linewidth=1.2, label=label)
                # 4‑я разность строится по полным данным: ось X = исходное время
                line2, = axes[2].plot(time, plot_height_4th_diff, color=color, linewidth=1.2, label=label)
                self.plot_lines[filename] = {
                    'RmsVel': line0,
                    'Hei': line1,
                    'Hei_4th_Diff': line2,
                }
            from matplotlib.ticker import FuncFormatter, MaxNLocator
            def format_time(seconds, pos):
                if seconds is None:
                    return ""
                total_seconds = float(seconds)
                if not np.isfinite(total_seconds):
                    return ""
                hours = int(total_seconds // 3600)
                minutes = int((total_seconds % 3600) // 60)
                sec_total = total_seconds % 60
                return f"{hours:02d}:{minutes:02d}:{sec_total:04.1f}"
            for i in range(3):
                ax = axes[i]
                ax.xaxis.set_major_formatter(FuncFormatter(format_time))
                ax.xaxis.set_major_locator(MaxNLocator(nbins=12))
                ax.set_ylabel(axis_titles[i].split('[')[1].replace(']', ''))
                ax.set_title(axis_titles[i], fontsize=10, fontweight='bold')
                ax.grid(True, alpha=0.3, color=LIGHT_THEME.BORDER)
                ax.set_facecolor(LIGHT_THEME.BG_SECONDARY)
                ax.tick_params(colors=LIGHT_THEME.FG_SECONDARY)
                for spine in ax.spines.values():
                    spine.set_color(LIGHT_THEME.BORDER)
                if i == 0 or i == 2:
                    ax.axhline(
                        y=0,
                        color=LIGHT_THEME.BORDER,
                        linestyle='--',
                        alpha=0.5,
                        linewidth=0.8,
                    )
                if i == 0 and ax.lines:
                    ax.legend(
                        loc="upper right",
                        fontsize=8,
                        ncol=2,
                        facecolor=LIGHT_THEME.BG_SECONDARY,
                        edgecolor=LIGHT_THEME.BORDER,
                        labelcolor=LIGHT_THEME.FG_PRIMARY,
                    )
            axes[2].set_xlabel("Время (часы:минуты:секунды)", color=LIGHT_THEME.FG_PRIMARY)
            plt.tight_layout()
            canvas = FigureCanvasTkAgg(fig, self.plot_frame)
            canvas.draw()
            canvas.mpl_connect('button_press_event', self.on_canvas_click)
            self.interactive_zoom = InteractiveZoom(fig, axes)
            self.current_fig = fig
            self.current_canvas = canvas
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            info_frame = tk.Frame(self.plot_frame, bg=LIGHT_THEME.BG_PRIMARY)
            info_frame.pack(fill=tk.X, padx=5, pady=2)
            tk.Label(
                info_frame,
                text="📊 Вот так вот",
                font=("Segoe UI", 9),
                fg=LIGHT_THEME.ACCENT_BLUE,
                bg=LIGHT_THEME.BG_PRIMARY,
            ).pack()
        except Exception as e:
            import traceback
            traceback.print_exc()
            if self.plot_frame:
                tk.Label(
                    self.plot_frame,
                    text=f"Ошибка построения графика:\n{str(e)}",
                    font=("Arial", 11),
                    fg=LIGHT_THEME.ERROR,
                    bg=LIGHT_THEME.BG_PRIMARY,
                ).pack(expand=True)
    def calculate_4th_diff(self, data: np.ndarray) -> np.ndarray:
        if data is None or len(data) < 5:
            return np.array([])
        try:
            # Центрированная 4‑я разность:
            # diff4[i] = V[i+2] - 4*V[i+1] + 6*V[i] - 4*V[i-1] + V[i-2]
            data = np.asarray(data, dtype=float)
            result = np.zeros_like(data, dtype=float)
            # Индексы 2 .. len(data)-3 имеют полный набор соседей
            result[2:-2] = (
                data[4:]
                - 4.0 * data[3:-1]
                + 6.0 * data[2:-2]
                - 4.0 * data[1:-3]
                + data[0:-4]
            )
            return result
        except Exception as e:
            print(f"Ошибка расчета 4-й разности: {e}")
            return np.array([])
    def on_canvas_click(self, event):
        if event.button == 3 and event.inaxes is not None:
            self.show_context_menu(event)
        elif event.button == 1 and getattr(event, "dblclick", False):
            if self.interactive_zoom:
                self.interactive_zoom.reset_all_zooms()
    def _format_time_label(self, seconds: float) -> str:
        if seconds is None:
            return ""
        total_seconds = float(seconds)
        if not np.isfinite(total_seconds):
            return ""
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        sec_total = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{sec_total:04.1f}"
    def create_context_menu(self):
        if not self.window:
            return
        self.context_menu = tk.Menu(self.window, tearoff=0, bg=LIGHT_THEME.BG_SECONDARY, fg=LIGHT_THEME.FG_PRIMARY)
        self.context_menu.add_command(label="📋 Копировать время", command=self.copy_time_to_clipboard)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="📋 Копировать X,Y", command=self.copy_coords_to_clipboard)
    def show_context_menu(self, event):
        if not self.current_canvas or not event or event.xdata is None or event.ydata is None:
            return
        self.last_click_coords = (event.xdata, event.ydata)
        self.last_click_time = event.xdata
        if not self.context_menu:
            self.create_context_menu()
        try:
            if hasattr(event, "guiEvent") and event.guiEvent:
                self.context_menu.tk_popup(event.guiEvent.x_root, event.guiEvent.y_root)
        finally:
            if self.context_menu:
                self.context_menu.grab_release()
    def copy_time_to_clipboard(self):
        if self.last_click_time is None:
            return
        time_str = self._format_time_label(self.last_click_time)
        try:
            pyperclip.copy(time_str)
            messagebox.showinfo("Скопировано", f"Время: {time_str}", parent=self.window)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось скопировать: {e}", parent=self.window)
    def copy_coords_to_clipboard(self):
        if self.last_click_coords is None:
            return
        x, y = self.last_click_coords
        time_str = self._format_time_label(x)
        text = f"{time_str}\tY={y:.6f}"
        try:
            pyperclip.copy(text)
            messagebox.showinfo("Скопировано", text, parent=self.window)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось скопировать: {e}", parent=self.window)
    def _read_qc_pdop(self, qc_file: Path):
        times = []
        pdops = []
        try:
            with open(qc_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("Time[sec]"):
                        continue
                    parts = line.split()
                    if len(parts) < 4:
                        continue
                    try:
                        t_sec = float(parts[0])
                        pdop = float(parts[3])
                    except ValueError:
                        continue
                    times.append(t_sec)
                    pdops.append(pdop)
        except Exception:
            return None, None
        if not times:
            return None, None
        return np.array(times, dtype=float), np.array(pdops, dtype=float)

    def _get_qc_pdop_stats(self):
        if not self.current_dir or not self.current_dir.exists():
            return None
        qc_file = None
        preferred_names = ["Rover_Std.QC", "ROVER_STD.QC", "rover_std.qc"]
        for name in preferred_names:
            candidate = self.current_dir / name
            if candidate.exists():
                qc_file = candidate
                break
        if qc_file is None:
            candidates = list(self.current_dir.glob("*.QC")) + list(self.current_dir.glob("*.qc"))
            if candidates:
                qc_file = candidates[0]
        if qc_file is None or not qc_file.exists():
            return None
        times, pdops = self._read_qc_pdop(qc_file)
        if times is None or pdops is None or len(pdops) == 0:
            return None
        return {
            "min": float(np.min(pdops)),
            "max": float(np.max(pdops)),
            "mean": float(np.mean(pdops)),
        }
    def update_qc_plot(self):
        if not self.qc_plot_frame:
            return
        if self.qc_fig:
            plt.close(self.qc_fig)
            self.qc_fig = None
        if self.qc_canvas:
            self.qc_canvas.get_tk_widget().destroy()
            self.qc_canvas = None
        for widget in self.qc_plot_frame.winfo_children():
            widget.destroy()
        if not self.current_dir or not self.current_dir.exists():
            tk.Label(
                self.qc_plot_frame,
                text="Папка проекта не выбрана",
                font=("Arial", 11),
                fg=LIGHT_THEME.FG_SECONDARY,
                bg=LIGHT_THEME.BG_PRIMARY,
            ).pack(expand=True)
            return
        qc_file = None
        # Сначала пробуем найти Rover_Std.QC
        preferred_names = ["Rover_Std.QC", "ROVER_STD.QC", "rover_std.qc"]
        for name in preferred_names:
            candidate = self.current_dir / name
            if candidate.exists():
                qc_file = candidate
                break
        # Если не нашли, берем первый попавшийся *.QC
        if qc_file is None:
            candidates = list(self.current_dir.glob("*.QC")) + list(self.current_dir.glob("*.qc"))
            if candidates:
                qc_file = candidates[0]
        if qc_file is None or not qc_file.exists():
            tk.Label(
                self.qc_plot_frame,
                text="QC файл Rover_Std.QC не найден в выбранной папке",
                font=("Arial", 11),
                fg=LIGHT_THEME.WARNING,
                bg=LIGHT_THEME.BG_PRIMARY,
            ).pack(expand=True)
            return
        times, pdops = self._read_qc_pdop(qc_file)
        if times is None or pdops is None:
            tk.Label(
                self.qc_plot_frame,
                text="Ошибка чтения QC файла",
                font=("Arial", 11),
                fg=LIGHT_THEME.ERROR,
                bg=LIGHT_THEME.BG_PRIMARY,
            ).pack(expand=True)
            return
        if len(times) == 0:
            tk.Label(
                self.qc_plot_frame,
                text="В QC файле нет валидных данных для PDOP",
                font=("Arial", 11),
                fg=LIGHT_THEME.WARNING,
                bg=LIGHT_THEME.BG_PRIMARY,
            ).pack(expand=True)
            return
        from matplotlib.ticker import FuncFormatter, MaxNLocator
        def format_time(seconds, pos):
            if seconds is None:
                return ""
            total_seconds = float(seconds)
            if not np.isfinite(total_seconds):
                return ""
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            sec_total = total_seconds % 60
            return f"{hours:02d}:{minutes:02d}:{sec_total:04.1f}"
        fig, ax = plt.subplots(1, 1, figsize=(20, 5), sharex=False)
        fig.patch.set_facecolor(LIGHT_THEME.BG_SECONDARY)
        color = LIGHT_THEME.ACCENT_BLUE
        ax.plot(times, pdops, color=color, linewidth=1.2, label="PDOP")
        ax.xaxis.set_major_formatter(FuncFormatter(format_time))
        ax.xaxis.set_major_locator(MaxNLocator(nbins=10))
        ax.set_xlabel("Время (часы:минуты:секунды)", color=LIGHT_THEME.FG_PRIMARY)
        ax.set_ylabel("PDOP", color=LIGHT_THEME.FG_PRIMARY)
        ax.set_title(f"PDOP из QC файла ({qc_file.name})", fontsize=10, fontweight="bold")
        ax.grid(True, alpha=0.3, color=LIGHT_THEME.BORDER)
        ax.set_facecolor(LIGHT_THEME.BG_SECONDARY)
        ax.tick_params(colors=LIGHT_THEME.FG_SECONDARY)
        for spine in ax.spines.values():
            spine.set_color(LIGHT_THEME.BORDER)
        ax.legend(
            loc="upper right",
            fontsize=8,
            facecolor=LIGHT_THEME.BG_SECONDARY,
            edgecolor=LIGHT_THEME.BORDER,
            labelcolor=LIGHT_THEME.FG_PRIMARY,
        )
        plt.tight_layout()
        canvas = FigureCanvasTkAgg(fig, self.qc_plot_frame)
        canvas.draw()
        self.qc_fig = fig
        self.qc_canvas = canvas
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    def update_plot_visibility(self):
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
        if self.interactive_zoom:
            self.interactive_zoom.reset_all_zooms()