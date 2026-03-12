import asyncio
import queue
import os
import sys
import subprocess
from pathlib import Path
from typing import Tuple, Optional, Dict, List, Set, Any
from core.app_context import APP_CONTEXT, AppContext
from core.message_system import AppMessage, MessageLevel
from model.file_manager import FileManager, FileType
from model.process_runner import ProcessRunner, ProcessType
from model.gps_excluder import GPSExcluder
from model.file_transformer import FileTransformer
from model.analyzers.velocity_analyzer import VelocityAnalyzer
from model.analyzers.gps_constellation_analyzer import GPSConstellationAnalyzer
from model.user_paths_storage import UserPathsStorage
from view.main_window import MainWindow
from view.dialogs import GPSExclusionDialog, TransformFileDialog
from view.analysis_windows.velocity_window import VelocityAnalysisWindow
from view.analysis_windows.gps_window import GPSAnalysisWindow
class ApplicationController:
    def __init__(self):
        self._message_queue: queue.Queue[AppMessage] = queue.Queue(maxsize=1000)
        self._file_manager = FileManager(APP_CONTEXT, self._publish_message)
        self._process_runner = ProcessRunner(self._publish_message)
        self._gps_excluder = GPSExcluder(APP_CONTEXT)
        self._file_transformer = FileTransformer(self._publish_message)
        self._velocity_analyzer = VelocityAnalyzer()
        self._gps_analyzer = GPSConstellationAnalyzer(
            target_points=5000,
            min_gap_duration=2.0,
            merge_gap=5.0
        )
        self._user_paths_storage = UserPathsStorage(APP_CONTEXT.working_dir, "user_paths.txt")
        self._window: Optional[MainWindow] = None
        from async_manager import async_manager
        self._async_manager = async_manager
        self._async_manager.start()
    def run(self) -> None:
        self._window = MainWindow(self)
        self._window.run()                                  
    def on_window_ready(self) -> None:
        self._load_initial_paths()
        self._load_initial_angle()
    def _load_initial_angle(self) -> None:
        """
        При старте пробуем прочитать угол отсечения из Mask.Ang и
        синхронизировать его с FileManager и UI.
        """
        try:
            mask_path = APP_CONTEXT.mask_ang
            if not mask_path.exists():
                return
            raw = mask_path.read_text(encoding="utf-8", errors="ignore").strip()
            if not raw:
                return
            try:
                angle = float(raw.split()[0].replace(",", "."))
            except ValueError:
                return
            if angle < 0 or angle > 90:
                return
            self._file_manager.set_cutoff_angle(angle)
            if self._window and hasattr(self._window, "set_cutoff_angle_value"):
                self._window.set_cutoff_angle_value(angle)
        except Exception:
            # Повреждённый Mask.Ang не должен ломать запуск
            return
    def _load_initial_paths(self) -> None:
        self._publish_message(AppMessage.info("🔄 Загрузка последних путей...", source="Controller"))
        saved_paths = self._user_paths_storage.get_all_paths()
        for key, path in saved_paths.items():
            if path and Path(path).exists():
                try:
                    file_type = FileType(key)
                    if file_type == FileType.ROVER:
                        self._file_manager.set_rover_path(path)
                    elif file_type == FileType.SR2NAV_EXE:
                        self._file_manager.set_path(file_type, path)
                    else:
                        self._file_manager.set_path(file_type, path)
                    if self._window:
                        self._window.set_file_path(key, path)
                    self._publish_message(AppMessage.debug(
                        f"Загружен путь для {file_type.description}: {path}",
                        source="Controller"
                    ))
                except ValueError:
                    pass
            elif path:
                self._publish_message(AppMessage.warning(
                    f"Сохраненный путь не существует и будет пропущен: {path}",
                    source="Controller"
                ))
        self._publish_message(AppMessage.info("✅ Загрузка путей завершена.", source="Controller"))
    @property
    def app_context(self) -> AppContext:
        return APP_CONTEXT
    def _validate_before_run(
        self,
        require_rover: bool = False,
        require_sr2nav: bool = False
    ) -> Tuple[bool, str]:
        if require_sr2nav:
            path = self._file_manager.get_original_path(FileType.SR2NAV_EXE)
            if not path:
                return False, "SR2Nav.exe не выбран"
            if not path.exists():
                return False, f"SR2Nav.exe не найден:\n{path}"
        if require_rover:
            path = self._file_manager.get_original_path(FileType.ROVER)
            if not path:
                return False, "Файл ровера (JPS) не выбран"
            if not path.exists():
                return False, f"Файл ровера не найден:\n{path}"
            if path.suffix.lower() != '.jps':
                return False, f"Файл ровера должен быть .jps:\n{path.name}"
        try:
            angle = float(self._window.get_cutoff_angle())
            if angle < 0 or angle > 90:
                return False, "Угол отсечения должен быть от 0 до 90 градусов"
        except ValueError:
            return False, "Некорректное значение угла отсечения"
        return True, ""
    def on_update_cutoff_angle(self) -> None:
        """
        Обновление только угла отсечения (Mask.Ang) без запуска Interval.exe.
        """
        if not self._window:
            return
        try:
            angle = float(self._window.get_cutoff_angle())
        except ValueError:
            self._window.show_error("Ошибка", "Некорректное значение угла отсечения")
            return
        if angle < 0 or angle > 90:
            self._window.show_error("Ошибка", "Угол отсечения должен быть от 0 до 90 градусов")
            return
        self._file_manager.set_cutoff_angle(angle)
        ok, msg = self._file_manager.update_mask_file()
        if ok:
            self._publish_message(AppMessage.info(msg, source="Controller"))
            try:
                from tkinter import messagebox
                messagebox.showinfo("Готово", "Угол отсечения обновлён в Mask.Ang", parent=self._window.window)
            except Exception:
                pass
        else:
            self._publish_message(AppMessage.error(msg, source="Controller"))
            self._window.show_error("Ошибка", msg)
    def on_file_selected(self, file_key: str, path: str) -> None:
        try:
            file_type = FileType(file_key)
            if file_type == FileType.ROVER:
                self._file_manager.set_rover_path(path)
                self._user_paths_storage.set_rover_path(path)
                if self._window and path:
                    rover_name = Path(path).stem
                    self._window.update_window_title(rover_name)
                    self._publish_message(AppMessage.info(
                        f"📁 Папка результатов: {APP_CONTEXT.results_dir.name}",
                        source="Controller"
                    ))
            elif file_type == FileType.SR2NAV_EXE:
                self._file_manager.set_path(file_type, path)
                self._user_paths_storage.set_sr2nav_path(path)
            else:
                self._file_manager.set_path(file_type, path)
                if file_type == FileType.BASE1:
                    self._user_paths_storage.set_base1_path(path)
                elif file_type == FileType.BASE2:
                    self._user_paths_storage.set_base2_path(path)
            self._user_paths_storage.save()
            self._publish_message(AppMessage.debug(
                f"Установлен путь: {file_type.description}",
                source="Controller"
            ))
        except ValueError:
            self._publish_message(AppMessage.warning(
                f"Неизвестный тип файла: {file_key}",
                source="Controller"
            ))
    def on_stitch_jps(self, input_files: list, output_path: str, target_key: str = "rover") -> None:
        for file_path in input_files:
            if not os.path.exists(file_path):
                self._publish_message(AppMessage.error(
                    f"Файл не найден: {file_path}",
                    source="Controller"
                ))
                return
        success, message = self._file_manager.stitch_jps_files(input_files, output_path)
        if success:
            self._publish_message(AppMessage.info(message, source="Controller"))
            if target_key in ["rover", "base1", "base2"]:
                self._window.set_file_path(target_key, output_path)
                if target_key == "rover":
                    self._file_manager.set_rover_path(output_path)
                    self._user_paths_storage.set_rover_path(output_path)
                    rover_name = Path(output_path).stem
                    if self._window:
                        self._window.update_window_title(rover_name)
                    self._publish_message(AppMessage.info(
                        f"📁 Папка результатов: {APP_CONTEXT.results_dir.name}",
                        source="Controller"
                    ))
                elif target_key == "base1":
                    self._user_paths_storage.set_base1_path(output_path)
                elif target_key == "base2":
                    self._user_paths_storage.set_base2_path(output_path)
                self._user_paths_storage.save()
                self._publish_message(AppMessage.info(
                    f"📌 Сшитый файл установлен в поле '{target_key}'",
                    source="Controller"
                ))
        else:
            self._publish_message(AppMessage.error(message, source="Controller"))
    def on_open_file(self, path: str) -> None:
        if not path or not os.path.exists(path):
            self._publish_message(AppMessage.error(
                f"Файл не найден: {path}",
                source="Controller"
            ))
            return
        try:
            if sys.platform == 'win32':
                os.startfile(path)
            elif sys.platform == 'darwin':
                subprocess.run(['open', path], check=False)
            else:
                subprocess.run(['xdg-open', path], check=False)
        except Exception as e:
            self._publish_message(AppMessage.error(
                f"Не удалось открыть файл: {e}",
                source="Controller"
            ))
    def on_app_closing(self) -> None:
        print("🛑 Завершение приложения...")
        if self._process_runner.is_running:
            future = self._async_manager.run_coroutine(self._process_runner.terminate())
            future.result(timeout=2.0)
        self._async_manager.stop(timeout=1.0)
        sys.exit(0)
    def on_cleanup_working_directory(self) -> None:
        async def _run():
            if self._window:
                from tkinter import messagebox
                result = messagebox.askyesno(
                    "🧹 Очистка рабочей директории",
                    "Это удалит ВСЕ ФАЙЛЫ (кроме .exe и .py) из рабочей директории.\n\n"
                    "Папки (results, tbl и др.) не будут затронуты.\n\n"
                    "Продолжить?",
                    parent=self._window.window,
                    icon='warning'
                )
                if not result:
                    self._publish_message(AppMessage.info(
                        "Очистка отменена пользователем",
                        source="Controller"
                    ))
                    return
            self._publish_message(AppMessage.info(
                "🧹 Начинаю очистку рабочей директории...",
                source="Controller"
            ))
            deleted_count, errors = self._file_manager.cleanup_working_directory()
            if errors:
                self._publish_message(AppMessage.warning(
                    f"⚠️ Очистка завершена с {len(errors)} ошибками. "
                    f"Удалено файлов: {deleted_count}",
                    source="Controller"
                ))
            else:
                self._publish_message(AppMessage.info(
                    f"✅ Рабочая директория очищена. Удалено файлов: {deleted_count}",
                    source="Controller"
                ))
        self._run_async(_run())
    def on_run_interval(self) -> None:
        success, error_msg = self._validate_before_run(require_rover=True, require_sr2nav=False)
        if not success:
            self._window.show_error("Ошибка", error_msg)
            self._publish_message(AppMessage.error(error_msg, source="Controller"))
            return
        async def _run():
            self._sync_files_from_ui()
            angle = self._window.get_cutoff_angle()
            self._file_manager.set_cutoff_angle(angle)
            self._file_manager.reset_manual_mode()
            success, msg, prepared_paths = await self._file_manager.run_interval()
            if not success:
                self._publish_message(AppMessage.error(msg, source="Controller"))
                return
            if not prepared_paths:
                self._publish_message(AppMessage.error("Не удалось подготовить файлы для Interval.", source="Controller"))
                return
            cmd = [str(APP_CONTEXT.interval_exe)]
            await self._process_runner.run(
                cmd,
                str(APP_CONTEXT.working_dir),
                ProcessType.INTERVAL,
                timeout=1.5,
            )
            success, msg = await self._file_manager.parse_interval_result()
            if success:
                interval = self._file_manager.time_interval
                self._window.update_time_interval(
                    interval.start,
                    interval.end,
                    is_manual=interval.manual
                )
                self._publish_message(AppMessage.info(msg, source="Controller"))
            else:
                self._publish_message(AppMessage.error(msg, source="Controller"))
        self._run_async(_run())
    def on_interval_manually_changed(self, start: str, end: str) -> None:
        if not start.strip() and not end.strip():
            self._file_manager.reset_manual_mode()
            self._publish_message(AppMessage.debug(
                "🔄 Ручной режим интервала сброшен (поля очищены)",
                source="Controller"
            ))
            if self._window:
                self._window.update_time_interval("", "", is_manual=False)
            return
        if start.strip() and end.strip():
            self._file_manager.update_time_interval(start, end, manual=True)
            self._publish_message(AppMessage.debug(
                f"✏️ Интервал изменён вручную: {start} - {end}",
                source="Controller"
            ))
            if self._window:
                self._window.update_time_interval(start, end, is_manual=True)
    def on_run_sr2nav(self) -> None:
        success, error_msg = self._validate_before_run(require_rover=False, require_sr2nav=True)
        if not success:
            self._window.show_error("Ошибка", error_msg)
            self._publish_message(AppMessage.error(error_msg, source="Controller"))
            return
        async def _run():
            self._sync_files_from_ui()
            self._file_manager.cleanup_results_dir()
            self._window.set_processing_state(True)
            success, msg, prepared_paths = await self._file_manager.run_sr2nav()
            if not success:
                self._publish_message(AppMessage.error(msg, source="Controller"))
                self._window.set_processing_state(False)
                return
            if not prepared_paths:
                self._publish_message(AppMessage.error("Не удалось подготовить файлы для SR2Nav.", source="Controller"))
                self._window.set_processing_state(False)
                return
            sr2nav_path_to_use = prepared_paths.get(FileType.SR2NAV_EXE)
            if not sr2nav_path_to_use:
                self._publish_message(AppMessage.error("SR2Nav.exe не был подготовлен.", source="Controller"))
                self._window.set_processing_state(False)
                return
            cmd = [str(sr2nav_path_to_use)]
            return_code = await self._process_runner.run(
                cmd,
                str(APP_CONTEXT.working_dir),
                ProcessType.SR2NAV,
                timeout=None,
            )
            self._window.set_processing_state(False)
            if return_code == 0:
                self._publish_message(AppMessage.info(
                    "✅ SR2Nav успешно завершён",
                    source="Controller"
                ))
                moved = self._file_manager.move_results_to_results_dir()
                self._publish_message(AppMessage.info(
                    f"📁 Результаты ({moved} файлов) сохранены в: {APP_CONTEXT.results_dir.name}",
                    source="Controller"
                ))
            else:
                self._publish_message(AppMessage.warning(
                    f"⚠️ SR2Nav завершён с кодом: {return_code}",
                    source="Controller"
                ))
        self._run_async(_run())
    def on_run_full_cycle(self) -> None:
        success, error_msg = self._validate_before_run(require_rover=True, require_sr2nav=True)
        if not success:
            self._window.show_error("Ошибка", error_msg)
            self._publish_message(AppMessage.error(error_msg, source="Controller"))
            return
        async def _run():
            self._sync_files_from_ui()
            angle = self._window.get_cutoff_angle()
            self._file_manager.set_cutoff_angle(angle)
            self._file_manager.cleanup_results_dir()
            self._publish_message(AppMessage.info(
                "▶️ Шаг 1/2: Запуск Interval.exe",
                source="Controller"
            ))
            success, msg, prepared_paths_interval = await self._file_manager.run_interval()
            if not success:
                self._publish_message(AppMessage.error(msg, source="Controller"))
                return
            if not prepared_paths_interval:
                self._publish_message(AppMessage.error("Не удалось подготовить файлы для Interval.", source="Controller"))
                return
            cmd_interval = [str(APP_CONTEXT.interval_exe)]
            await self._process_runner.run(
                cmd_interval,
                str(APP_CONTEXT.working_dir),
                ProcessType.INTERVAL,
                timeout=1.5,
            )
            success, msg = await self._file_manager.parse_interval_result()
            if success:
                interval = self._file_manager.time_interval
                self._window.update_time_interval(interval.start, interval.end)
                self._publish_message(AppMessage.info(msg, source="Controller"))
            await asyncio.sleep(0.5)                                                    
            self._publish_message(AppMessage.info(
                "▶️ Шаг 2/2: Запуск SR2Nav.exe",
                source="Controller"
            ))
            self._window.set_processing_state(True)
            success, msg, prepared_paths_sr2nav = await self._file_manager.run_sr2nav()
            if not success:
                self._publish_message(AppMessage.error(msg, source="Controller"))
                self._window.set_processing_state(False)
                return
            if not prepared_paths_sr2nav:
                self._publish_message(AppMessage.error("Не удалось подготовить файлы для SR2Nav.", source="Controller"))
                self._window.set_processing_state(False)
                return
            sr2nav_path_to_use = prepared_paths_sr2nav.get(FileType.SR2NAV_EXE)
            if not sr2nav_path_to_use:
                self._publish_message(AppMessage.error("SR2Nav.exe не был подготовлен.", source="Controller"))
                self._window.set_processing_state(False)
                return
            cmd_sr2nav = [str(sr2nav_path_to_use)]
            return_code = await self._process_runner.run(
                cmd_sr2nav,
                str(APP_CONTEXT.working_dir),
                ProcessType.SR2NAV,
                timeout=None,
            )
            if return_code == 0:
                moved = self._file_manager.move_results_to_results_dir()
                self._publish_message(AppMessage.info(
                    f"📁 Результаты ({moved} файлов) сохранены в: {APP_CONTEXT.results_dir.name}",
                    source="Controller"
                ))
            self._window.set_processing_state(False)
        self._run_async(_run())
    def on_terminate_process(self) -> None:
        async def _run():
            if not self._process_runner.is_running:
                self._publish_message(AppMessage.info(
                    "Нет запущенных процессов",
                    source="Controller"
                ))
                return
            self._publish_message(AppMessage.warning(
                "🛑 Остановка процесса...",
                source="Controller"
            ))
            await self._process_runner.terminate()
            self._window.set_processing_state(False)
        self._run_async(_run())
    def on_show_gps_exclusion_dialog(self) -> None:
        if not self._window:
            return
        current_excluded = self._gps_excluder.load_excluded()
        dialog = GPSExclusionDialog(
            self._window.window,
            current_excluded,
            self._on_gps_exclusion_saved
        )
        dialog.show()
    def _on_gps_exclusion_saved(self, excluded: Set[str]) -> None:
        success = self._gps_excluder.save_excluded(excluded)
        if success:
            count = len(excluded)
            if count == 0:
                self._publish_message(AppMessage.info(
                    "Все спутники включены",
                    source="Controller"
                ))
            else:
                self._publish_message(AppMessage.warning(
                    f"Исключено спутников: {count}",
                    source="Controller"
                ))
    def on_show_transform_dialog(self) -> None:
        if not self._window:
            return
        dialog = TransformFileDialog(
            self._window.window,
            str(APP_CONTEXT.results_dir),
            self.on_transform_files
        )
        dialog.show()
    def on_transform_files(self, filenames: List[str], source_dir: str) -> None:
        async def _run():
            source_path = Path(source_dir)
            tbl_dir = source_path / "tbl"
            tbl_dir.mkdir(parents=True, exist_ok=True)
            self._publish_message(AppMessage.info(
                f"📁 Исходная папка: {source_path}",
                source="Controller"
            ))
            self._publish_message(AppMessage.info(
                f"📁 TBL файлы будут сохранены в: {tbl_dir}",
                source="Controller"
            ))
            files_found = 0
            files_transformed = 0
            for filename in filenames:
                found = False
                for root, dirs, files in os.walk(str(source_path)):
                    if filename in files:
                        src = Path(root) / filename
                        dst = tbl_dir / f"{Path(filename).stem}.tbl"
                        self._publish_message(AppMessage.info(
                            f"🔍 Найден: {src}",
                            source="Controller"
                        ))
                        files_found += 1
                        file_type = self._file_transformer.detect_file_type(filename)
                        if file_type:
                            success = await self._file_transformer.transform(src, dst, file_type)
                            if success:
                                files_transformed += 1
                                self._publish_message(AppMessage.info(
                                    f"✓ {filename} → {dst.name}",
                                    source="Controller"
                                ))
                        found = True
                        break                               
                if not found:
                    self._publish_message(AppMessage.warning(
                        f"⚠️ Файл не найден: {filename}",
                        source="Controller"
                    ))
            if files_transformed > 0:
                self._publish_message(AppMessage.info(
                    f"✅ Трансформация завершена. "
                    f"Преобразовано {files_transformed} из {files_found} файлов. "
                    f"Сохранено в: {tbl_dir}",
                    source="Controller"
                ))
            else:
                self._publish_message(AppMessage.warning(
                    f"⚠️ Ни один файл не был преобразован",
                    source="Controller"
                ))
        self._run_async(_run())
    def _perform_analysis(self,
                        window: Any,
                        analysis_name: str,
                        analyze_func: callable,
                        prepare_results_func: callable) -> None:
        async def _run():
            try:
                folder_path = str(window.current_dir)
                self._publish_message(AppMessage.info(
                    f"🔍 {analysis_name} в папке: {folder_path}",
                    source="Controller"
                ))
                if not os.path.exists(folder_path):
                    error_msg = f"Папка не найдена: {folder_path}"
                    self._publish_message(AppMessage.error(error_msg, source="Controller"))
                    self._window.window.after(0, lambda: window.show_error(error_msg))
                    return
                results = analyze_func(folder_path)
                if not results:
                    self._publish_message(AppMessage.warning(
                        f"В папке {folder_path} не найдено файлов для анализа",
                        source="Controller"
                    ))
                    self._window.window.after(0, lambda: window.show_error("Файлы не найдены"))
                    return
                view_results, extra = prepare_results_func(results)
                if extra:
                    self._window.window.after(0, lambda: window.update_results(view_results, extra))
                else:
                    self._window.window.after(0, lambda: window.update_results(view_results))
                self._publish_message(AppMessage.success(
                    f"✅ {analysis_name} завершен. Найдено файлов: {len(results)}",
                    source="Controller"
                ))
            except Exception as e:
                error_msg = f"Ошибка {analysis_name.lower()}: {str(e)}"
                self._publish_message(AppMessage.error(error_msg, source="Controller"))
                import traceback
                traceback.print_exc()
                self._window.window.after(0, lambda: window.show_error(error_msg))
        self._run_async(_run())
    def on_analyze_velocities(self) -> None:
        if not self._window:
            return
        VelocityAnalysisWindow(self._window.window, self)
    def request_velocity_analysis(self, window: VelocityAnalysisWindow, folder_path: str) -> None:
        window.current_dir = Path(folder_path)
        self._perform_analysis(
            window=window,
            analysis_name="Анализ скоростей",
            analyze_func=lambda path: self._velocity_analyzer.analyze_all(path),
            prepare_results_func=self._prepare_velocity_results_for_view
        )
    def _prepare_velocity_results_for_view(self, results: Dict) -> Tuple[Dict, Dict]:
        view_results = {}
        for filename, result in results.items():
            view_results[filename] = {
                'data': {
                    'time': result.data.time.tolist() if hasattr(result.data.time, 'tolist') else result.data.time,
                    'v_e': result.data.v_e.tolist() if hasattr(result.data.v_e, 'tolist') else result.data.v_e,
                    'v_n': result.data.v_n.tolist() if hasattr(result.data.v_n, 'tolist') else result.data.v_n,
                    'v_up': result.data.v_up.tolist() if hasattr(result.data.v_up, 'tolist') else result.data.v_up,
                    'height': result.data.height.tolist() if hasattr(result.data.height, 'tolist') else result.data.height,
                    'rms_vel': result.data.rms_vel.tolist() if hasattr(result.data.rms_vel, 'tolist') else result.data.rms_vel,
                    'rows': result.data.rows,
                    'time_span': result.data.time_span,
                },
                'statistics': {
                    'rows_analyzed': result.statistics.rows_analyzed,
                    'max_v_e': result.statistics.max_v_e,
                    'max_v_n': result.statistics.max_v_n,
                    'max_v_up': result.statistics.max_v_up,
                    'mean_v_e': result.statistics.mean_v_e,
                    'mean_v_n': result.statistics.mean_v_n,
                    'mean_v_up': result.statistics.mean_v_up,
                    'std_v_e': result.statistics.std_v_e,
                    'std_v_n': result.statistics.std_v_n,
                    'std_v_up': result.statistics.std_v_up,
                    'max_rms_vel': getattr(result.statistics, 'max_rms_vel', 0.0),
                    'max_height_4th_diff': result.statistics.max_height_4th_diff,
                }
            }
        summary = self._velocity_analyzer.get_summary_statistics()
        return view_results, summary
    def export_velocity_analysis(self, output_file: str) -> bool:
        return self._velocity_analyzer.export_to_csv(output_file)
    def on_analyze_gps_constellation(self) -> None:
        if not self._window:
            return
        GPSAnalysisWindow(self._window.window, self)
    def request_gps_analysis(self, window: GPSAnalysisWindow, folder_path: Optional[str] = None) -> None:
        if folder_path is None:
            folder_path = str(APP_CONTEXT.results_dir)
        window.current_dir = Path(folder_path)
        self._perform_analysis(
            window=window,
            analysis_name="Анализ GPS созвездия",
            analyze_func=lambda path: self._gps_analyzer.analyze_all(path),
            prepare_results_func=self._prepare_gps_results_for_view
        )
    def _prepare_gps_results_for_view(self, results: Dict) -> Tuple[Dict, None]:
        view_results = {}
        for filename, result in results.items():
            satellite_stats = {}
            for sat, stats in result.satellite_stats.items():
                satellite_stats[sat] = {
                    'num_intervals': stats.num_intervals,
                    'total_visible_time': stats.total_visible_time,
                    'avg_duration': stats.avg_duration,
                    'max_duration': stats.max_duration,
                    'min_duration': stats.min_duration,
                    'visibility_percent': stats.visibility_percent,
                    'is_visible': stats.is_visible,
                    'stability_index': stats.stability_index,
                    'stability_category': stats.stability_category,
                    'warning_message': stats.warning_message,
                    'is_problematic': stats.is_problematic,
                    'intervals_per_minute': stats.intervals_per_minute,
                    'intervals': [
                        {'start': i.start, 'end': i.end, 'duration': i.duration}
                        for i in stats.intervals
                    ]
                }
            summary = result.summary_report
            view_results[filename] = {
                'data': {
                    'filename': result.data.filename,
                    'filepath': result.data.filepath,
                    'time_range': result.data.time_range,
                    'total_duration': result.data.total_duration,
                    'rows_original': result.data.rows_original,
                    'rows_sampled': result.data.rows_sampled,
                    'sampling_rate': result.data.sampling_rate,
                },
                'satellite_stats': satellite_stats,
                'visible_satellites': result.visible_satellites,
                'mean_satellites': result.mean_satellites,
                'problem_satellites': [
                    {'prn': sat, **stats.__dict__}
                    for sat, stats in result.problem_satellites
                ],
                'critical_satellites': [
                    {'prn': sat, **stats.__dict__}
                    for sat, stats in result.critical_satellites
                ],
                'excellent_satellites': [
                    {'prn': sat, **stats.__dict__}
                    for sat, stats in result.excellent_satellites
                ],
                'overall_quality': {
                    'score': result.overall_quality_score,
                    'category': result.overall_quality_category[0],
                    'color': result.overall_quality_category[1],
                    'needs_attention': summary['needs_attention']
                },
                'summary': summary
            }
        return view_results, None
    def export_gps_analysis(self, output_file: str) -> bool:
        return self._gps_analyzer.export_to_csv(output_file)
    def _sync_files_from_ui(self) -> None:
        if not self._window:
            return
        paths = self._window.get_all_file_paths()
        for key, path in paths.items():
            try:
                file_type = FileType(key)
                if file_type == FileType.ROVER:
                    self._file_manager.set_rover_path(path)
                else:
                    self._file_manager.set_path(file_type, path)
            except ValueError:
                pass
    def _run_async(self, coro) -> None:
        self._async_manager.run_coroutine(coro)
    def _publish_message(self, message: AppMessage) -> None:
        try:
            self._message_queue.put_nowait(message)
        except queue.Full:
            try:
                self._message_queue.get_nowait()
                self._message_queue.put_nowait(message)
            except queue.Empty:
                pass
    @property
    def message_queue(self) -> queue.Queue:
        return self._message_queue
    @property
    def script_dir(self) -> str:
        return str(APP_CONTEXT.working_dir)