#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Главный контроллер приложения - ЧИСТАЯ ОРКЕСТРАЦИЯ.
"""
import asyncio
import queue
import os
import sys
import subprocess
from pathlib import Path
from typing import Tuple, Optional, Dict, List, Set, Any

from core.app_context import APP_CONTEXT, AppContext
from core.message_system import AppMessage, MessageLevel

# MODEL - чистая бизнес-логика
from model.file_manager import FileManager, FileType
from model.process_runner import ProcessRunner, ProcessType
from model.gps_excluder import GPSExcluder
from model.file_transformer import FileTransformer
from model.analyzers.velocity_analyzer import VelocityAnalyzer
from model.analyzers.gps_constellation_analyzer import GPSConstellationAnalyzer

# VIEW - чистое представление
from view.main_window import MainWindow
from view.dialogs import GPSExclusionDialog, TransformFileDialog
from view.analysis_windows.velocity_window import VelocityAnalysisWindow
from view.analysis_windows.gps_window import GPSAnalysisWindow


class ApplicationController:
    """
    ЧИСТЫЙ КОНТРОЛЛЕР в паттерне MVC.
    
    Зоны ответственности:
    1. Получение событий от View
    2. Валидация данных (ЕДИНСТВЕННОЕ МЕСТО!)
    3. Вызов методов Model
    4. Обновление View
    5. Никакой бизнес-логики!
    """
    
    def __init__(self):
        # Инициализация компонентов
        self._message_queue: queue.Queue[AppMessage] = queue.Queue(maxsize=1000)
        
        # MODEL - чистая бизнес-логика
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
        
        # VIEW - будет установлен при запуске
        self._window: Optional[MainWindow] = None
        
        # Асинхронный менеджер
        from async_manager import async_manager
        self._async_manager = async_manager
        self._async_manager.start()
    
    # ==================== ЖИЗНЕННЫЙ ЦИКЛ ====================
    
    def run(self) -> None:
        """Запуск приложения."""
        self._window = MainWindow(self)
        self._window.run()
    
    @property
    def app_context(self) -> AppContext:
        """Доступ к контексту для View."""
        return APP_CONTEXT
    
    # ==================== ЕДИНАЯ ВАЛИДАЦИЯ ====================
    
    def _validate_before_run(
        self, 
        require_rover: bool = False, 
        require_sr2nav: bool = False
    ) -> Tuple[bool, str]:
        """
        ЕДИНСТВЕННОЕ МЕСТО ПРОВЕРКИ СУЩЕСТВОВАНИЯ ФАЙЛОВ!
        """
        # 1. Проверка SR2Nav.exe
        if require_sr2nav:
            path = self._file_manager.get_original_path(FileType.SR2NAV_EXE)
            if not path:
                return False, "SR2Nav.exe не выбран"
            if not path.exists():
                return False, f"SR2Nav.exe не найден:\n{path}"
        
        # 2. Проверка файла ровера
        if require_rover:
            path = self._file_manager.get_original_path(FileType.ROVER)
            if not path:
                return False, "Файл ровера (JPS) не выбран"
            if not path.exists():
                return False, f"Файл ровера не найден:\n{path}"
            if path.suffix.lower() != '.jps':
                return False, f"Файл ровера должен быть .jps:\n{path.name}"
        
        # 3. Проверка угла отсечения
        try:
            angle = float(self._window.get_cutoff_angle())
            if angle < 0 or angle > 90:
                return False, "Угол отсечения должен быть от 0 до 90 градусов"
        except ValueError:
            return False, "Некорректное значение угла отсечения"
        
        return True, ""
    
    # ==================== ОБРАБОТЧИКИ СОБЫТИЙ UI ====================
    
    def on_file_selected(self, file_key: str, path: str) -> None:
        """Выбор файла пользователем."""
        try:
            file_type = FileType(file_key)
            
            # ОСОБАЯ ОБРАБОТКА ДЛЯ РОВЕРА
            if file_type == FileType.ROVER:
                self._file_manager.set_rover_path(path)
                # Обновляем заголовок окна
                if self._window and path:
                    rover_name = Path(path).stem
                    self._window.update_window_title(rover_name)
                    self._publish_message(AppMessage.info(
                        f"📁 Папка результатов: {APP_CONTEXT.results_dir.name}",
                        source="Controller"
                    ))
            else:
                self._file_manager.set_path(file_type, path)
            
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
        """Сшивание JPS файлов."""
        # Валидация
        for file_path in input_files:
            if not os.path.exists(file_path):
                self._publish_message(AppMessage.error(
                    f"Файл не найден: {file_path}",
                    source="Controller"
                ))
                return
        
        # Вызов модели
        success, message = self._file_manager.stitch_jps_files(input_files, output_path)
        
        # Обновление View
        if success:
            self._publish_message(AppMessage.info(message, source="Controller"))
            
            if target_key in ["rover", "base1", "base2"]:
                self._window.set_file_path(target_key, output_path)
                
                # ЕСЛИ ЭТО РОВЕР - ОБНОВЛЯЕМ ПАПКУ РЕЗУЛЬТАТОВ
                if target_key == "rover":
                    self._file_manager.set_rover_path(output_path)
                    rover_name = Path(output_path).stem
                    if self._window:
                        self._window.update_window_title(rover_name)
                    self._publish_message(AppMessage.info(
                        f"📁 Папка результатов: {APP_CONTEXT.results_dir.name}",
                        source="Controller"
                    ))
                
                self._publish_message(AppMessage.info(
                    f"📌 Сшитый файл установлен в поле '{target_key}'",
                    source="Controller"
                ))
        else:
            self._publish_message(AppMessage.error(message, source="Controller"))
    
    def on_open_file(self, path: str) -> None:
        """Открытие файла в программе по умолчанию."""
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
        """Закрытие приложения."""
        print("🛑 Завершение приложения...")
        
        # Останавливаем процесс
        if self._process_runner.is_running:
            future = self._async_manager.run_coroutine(self._process_runner.terminate())
            future.result(timeout=2.0)
        
        # Останавливаем асинхронный менеджер
        self._async_manager.stop(timeout=1.0)
        
        sys.exit(0)
    
    def on_cleanup_working_directory(self) -> None:
        """
        Очистка рабочей директории от временных файлов.
        Не трогает папки, .exe и .py файлы.
        """
        async def _run():
            # Подтверждение от пользователя
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
            
            # Вызываем метод модели
            deleted_count, errors = self._file_manager.cleanup_working_directory()
            
            # Итоговое сообщение
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



    # ==================== ЗАПУСК ПРОЦЕССОВ ====================
    
    def on_run_interval(self) -> None:
        """Запуск Interval.exe."""
        # 1. ВАЛИДАЦИЯ
        success, error_msg = self._validate_before_run(require_rover=True, require_sr2nav=False)
        if not success:
            self._window.show_error("Ошибка", error_msg)
            self._publish_message(AppMessage.error(error_msg, source="Controller"))
            return
        
        async def _run():
            # 2. Синхронизация UI -> Model
            self._sync_files_from_ui()
            angle = self._window.get_cutoff_angle()
            self._file_manager.set_cutoff_angle(angle)
            
            # 3. Подготовка файлов (Model)
            success, msg = await self._file_manager.run_interval()
            if not success:
                self._publish_message(AppMessage.error(msg, source="Controller"))
                return
            
            # 4. Запуск процесса (Model)
            cmd = [str(APP_CONTEXT.interval_exe)]
            await self._process_runner.run(
                cmd,
                str(APP_CONTEXT.working_dir),
                ProcessType.INTERVAL,
                timeout=1.5,
            )
            
            # 5. Парсинг результата (Model)
            success, msg = await self._file_manager.parse_interval_result()
            
            # 6. Обновление View
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
            
            # 7. Синхронизация Model -> UI
            self._sync_paths_to_ui()
        
        self._run_async(_run())
    
    def on_interval_manually_changed(self, start: str, end: str) -> None:
        """Ручное изменение интервала."""
        self._file_manager.update_time_interval(start, end, manual=True)
        self._publish_message(AppMessage.debug(
            f"✏️ Интервал изменён вручную: {start} - {end}",
            source="Controller"
        ))
    
    def on_run_sr2nav(self) -> None:
        """Запуск SR2Nav."""
        # 1. ВАЛИДАЦИЯ
        success, error_msg = self._validate_before_run(require_rover=False, require_sr2nav=True)
        if not success:
            self._window.show_error("Ошибка", error_msg)
            self._publish_message(AppMessage.error(error_msg, source="Controller"))
            return
        
        async def _run():
            # 2. Синхронизация UI -> Model
            self._sync_files_from_ui()
            
            # 3. Подготовка (Model)
            self._file_manager.cleanup_results_dir()
            
            # 4. Обновление View (состояние обработки)
            sr2nav_path = self._file_manager.get_original_path(FileType.SR2NAV_EXE)
            self._window.set_processing_state(True)
            
            # 5. Запуск процесса (Model)
            cmd = [str(sr2nav_path)]
            return_code = await self._process_runner.run(
                cmd,
                str(APP_CONTEXT.working_dir),
                ProcessType.SR2NAV,
                timeout=None,
            )
            
            # 6. Обновление View (состояние обработки)
            self._window.set_processing_state(False)
            
            # 7. Обработка результатов (Model)
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
            
            # 8. Синхронизация Model -> UI
            self._sync_paths_to_ui()
        
        self._run_async(_run())
    
    def on_run_full_cycle(self) -> None:
        """Полный цикл обработки."""
        # 1. ВАЛИДАЦИЯ
        success, error_msg = self._validate_before_run(require_rover=True, require_sr2nav=True)
        if not success:
            self._window.show_error("Ошибка", error_msg)
            self._publish_message(AppMessage.error(error_msg, source="Controller"))
            return
        
        async def _run():
            # 2. Синхронизация UI -> Model
            self._sync_files_from_ui()
            angle = self._window.get_cutoff_angle()
            self._file_manager.set_cutoff_angle(angle)
            
            # 3. Очистка (Model)
            self._file_manager.cleanup_results_dir()
            
            # 4. Шаг 1: Interval.exe
            self._publish_message(AppMessage.info(
                "▶️ Шаг 1/2: Запуск Interval.exe",
                source="Controller"
            ))
            
            success, msg = await self._file_manager.run_interval()
            if not success:
                self._publish_message(AppMessage.error(msg, source="Controller"))
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
                self._window.update_time_interval(interval.start, interval.end)
                self._publish_message(AppMessage.info(msg, source="Controller"))
            
            self._sync_paths_to_ui()
            await asyncio.sleep(0.5)
            
            # 5. Шаг 2: SR2Nav.exe
            self._publish_message(AppMessage.info(
                "▶️ Шаг 2/2: Запуск SR2Nav.exe",
                source="Controller"
            ))
            
            success, msg = await self._file_manager.run_sr2nav()
            if not success:
                self._publish_message(AppMessage.error(msg, source="Controller"))
                return
            
            self._window.set_processing_state(True)
            
            sr2nav_path = self._file_manager.get_original_path(FileType.SR2NAV_EXE)
            cmd = [str(sr2nav_path)]
            return_code = await self._process_runner.run(
                cmd,
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
            self._sync_paths_to_ui()
        
        self._run_async(_run())
    
    def on_terminate_process(self) -> None:
        """Остановка текущего процесса."""
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
    
    # ==================== ДИАЛОГИ ====================
    
    def on_show_gps_exclusion_dialog(self) -> None:
        """Показывает диалог исключения спутников."""
        if not self._window:
            return
        
        # ИСПРАВЛЕНИЕ: загружаем актуальные данные КАЖДЫЙ раз при открытии
        current_excluded = self._gps_excluder.load_excluded()
        
        dialog = GPSExclusionDialog(
            self._window.window,
            current_excluded,  # Передаем свежие данные
            self._on_gps_exclusion_saved
        )
        dialog.show()
    
    def _on_gps_exclusion_saved(self, excluded: Set[str]) -> None:
        """Callback сохранения исключённых спутников."""
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
        """Показывает диалог трансформации файлов."""
        if not self._window:
            return
        
        dialog = TransformFileDialog(
            self._window.window,
            str(APP_CONTEXT.results_dir),
            self.on_transform_files
        )
        dialog.show()
    
    def on_transform_files(self, filenames: List[str], source_dir: str) -> None:
        """
        Callback трансформации файлов.
        ИСПРАВЛЕНО: правильный поиск файлов в подпапках
        """
        async def _run():
            source_path = Path(source_dir)
            
            # Создаем папку tbl внутри исходной директории
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
            
            # Ищем файлы рекурсивно
            files_found = 0
            files_transformed = 0
            
            for filename in filenames:
                # Ищем файл во всех подпапках
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
                        break  # Берём первый найденный файл
                
                if not found:
                    self._publish_message(AppMessage.warning(
                        f"⚠️ Файл не найден: {filename}",
                        source="Controller"
                    ))
            
            # Итоговое сообщение
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
    
    # ==================== АНАЛИЗ ДАННЫХ ====================
    
    def on_analyze_velocities(self) -> None:
        """Запрос на анализ скоростей."""
        if not self._window:
            return
        
        if not APP_CONTEXT.results_dir.exists():
            self._publish_message(AppMessage.error(
                f"Папка {APP_CONTEXT.results_dir.name} не найдена: {APP_CONTEXT.results_dir}",
                source="Controller"
            ))
            return
        
        VelocityAnalysisWindow(self._window.window, self)
    
    def request_velocity_analysis(self, window: VelocityAnalysisWindow) -> None:
        """Обработка запроса от окна анализа скоростей."""
        async def _run():
            try:
                # ИСПРАВЛЕНИЕ: Используем путь из окна, если он есть
                if hasattr(window, 'current_dir') and window.current_dir:
                    folder_path = str(window.current_dir)
                    self._publish_message(AppMessage.info(
                        f"🔍 Анализ скоростей в папке: {folder_path}",
                        source="Controller"
                    ))
                else:
                    folder_path = str(APP_CONTEXT.results_dir)
                    self._publish_message(AppMessage.info(
                        f"🔍 Анализ скоростей в папке результатов: {APP_CONTEXT.results_dir.name}",
                        source="Controller"
                    ))
                
                # Проверяем существование папки
                if not os.path.exists(folder_path):
                    self._publish_message(AppMessage.error(
                        f"Папка не найдена: {folder_path}",
                        source="Controller"
                    ))
                    self._window.window.after(0, lambda: window.show_error(f"Папка не найдена:\n{folder_path}"))
                    return
                
                # Выполняем анализ
                results = self._velocity_analyzer.analyze_all(folder_path)
                
                if not results:
                    self._publish_message(AppMessage.warning(
                        f"В папке {folder_path} не найдено VEL файлов",
                        source="Controller"
                    ))
                    self._window.window.after(0, lambda: window.show_error("VEL файлы не найдены"))
                    return
                
                # Получаем сводную статистику
                summary = self._velocity_analyzer.get_summary_statistics()
                
                # Преобразуем результаты для отображения
                view_results = self._prepare_velocity_results_for_view(results)
                
                # Обновляем UI в главном потоке
                self._window.window.after(0, lambda: window.update_results(view_results, summary))
                
                self._publish_message(AppMessage.success(
                    f"✅ Анализ скоростей завершен. Найдено файлов: {len(results)}",
                    source="Controller"
                ))
                
            except Exception as e:
                error_msg = f"Ошибка анализа скоростей: {str(e)}"
                self._publish_message(AppMessage.error(error_msg, source="Controller"))
                import traceback
                traceback.print_exc()
                self._window.window.after(0, lambda: window.show_error(error_msg))
        
        self._run_async(_run())
    
    def _prepare_velocity_results_for_view(self, results: Dict) -> Dict:
        """Преобразует результаты Model в формат для View."""
        view_results = {}
        for filename, result in results.items():
            view_results[filename] = {
                'data': {
                    'time': result.data.time.tolist() if hasattr(result.data.time, 'tolist') else result.data.time,
                    'v_e': result.data.v_e.tolist() if hasattr(result.data.v_e, 'tolist') else result.data.v_e,
                    'v_n': result.data.v_n.tolist() if hasattr(result.data.v_n, 'tolist') else result.data.v_n,
                    'v_up': result.data.v_up.tolist() if hasattr(result.data.v_up, 'tolist') else result.data.v_up,
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
                    'max_speed_2d': result.statistics.max_speed_2d,
                    'max_speed_3d': result.statistics.max_speed_3d,
                    'mean_speed_2d': result.statistics.mean_speed_2d,
                    'mean_speed_3d': result.statistics.mean_speed_3d,
                }
            }
        return view_results
    
    def export_velocity_analysis(self, output_file: str) -> bool:
        """Экспорт анализа скоростей в CSV."""
        return self._velocity_analyzer.export_to_csv(output_file)
    
    def on_analyze_gps_constellation(self) -> None:
        """Запрос на анализ GPS созвездия."""
        if not self._window:
            return
        
        if not APP_CONTEXT.results_dir.exists():
            self._publish_message(AppMessage.error(
                f"Папка {APP_CONTEXT.results_dir.name} не найдена: {APP_CONTEXT.results_dir}",
                source="Controller"
            ))
            return
        
        GPSAnalysisWindow(self._window.window, self)
    
    def request_gps_analysis(self, window: GPSAnalysisWindow) -> None:
        """Обработка запроса от окна анализа GPS."""
        async def _run():
            try:
                # ИСПРАВЛЕНИЕ: Используем путь из окна, если он есть
                if hasattr(window, 'current_dir') and window.current_dir:
                    folder_path = str(window.current_dir)
                    self._publish_message(AppMessage.info(
                        f"🔍 Анализ GPS созвездия в папке: {folder_path}",
                        source="Controller"
                    ))
                else:
                    folder_path = str(APP_CONTEXT.results_dir)
                    self._publish_message(AppMessage.info(
                        f"🔍 Анализ GPS созвездия в папке результатов: {APP_CONTEXT.results_dir.name}",
                        source="Controller"
                    ))
                
                # Проверяем существование папки
                if not os.path.exists(folder_path):
                    self._publish_message(AppMessage.error(
                        f"Папка не найдена: {folder_path}",
                        source="Controller"
                    ))
                    self._window.window.after(0, lambda: window.show_error(f"Папка не найдена:\n{folder_path}"))
                    return
                
                # Выполняем анализ
                results = self._gps_analyzer.analyze_all(folder_path)
                
                if not results:
                    self._publish_message(AppMessage.warning(
                        f"В папке {folder_path} не найдено SVs файлов",
                        source="Controller"
                    ))
                    self._window.window.after(0, lambda: window.show_error("Файлы .SVs не найдены"))
                    return
                
                # Преобразуем результаты для отображения
                view_results = self._prepare_gps_results_for_view(results)
                
                # Обновляем UI в главном потоке
                self._window.window.after(0, lambda: window.update_results(view_results))
                
                self._publish_message(AppMessage.success(
                    f"✅ Анализ GPS завершен. Найдено файлов: {len(results)}",
                    source="Controller"
                ))
                
            except Exception as e:
                error_msg = f"Ошибка анализа GPS: {str(e)}"
                self._publish_message(AppMessage.error(error_msg, source="Controller"))
                import traceback
                traceback.print_exc()
                self._window.window.after(0, lambda: window.show_error(error_msg))
        
        self._run_async(_run())
    
    def _prepare_gps_results_for_view(self, results: Dict) -> Dict:
        """Преобразует результаты GPS анализа в формат для View."""
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
        return view_results
    
    def export_gps_analysis(self, output_file: str) -> bool:
        """Экспорт анализа GPS созвездия в CSV."""
        return self._gps_analyzer.export_to_csv(output_file)
    
    # ==================== ВНУТРЕННИЕ МЕТОДЫ ====================
    
    def _sync_files_from_ui(self) -> None:
        """Синхронизирует пути из View в Model."""
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
    
    def _sync_paths_to_ui(self) -> None:
        """Синхронизирует пути из Model в View."""
        if not self._window:
            return
        
        paths = self._file_manager.get_all_paths()
        self._window.sync_file_paths(paths)
    
    def _run_async(self, coro) -> None:
        """Запускает корутину асинхронно."""
        self._async_manager.run_coroutine(coro)
    
    def _publish_message(self, message: AppMessage) -> None:
        """Публикует сообщение в очередь."""
        try:
            self._message_queue.put_nowait(message)
        except queue.Full:
            try:
                self._message_queue.get_nowait()
                self._message_queue.put_nowait(message)
            except queue.Empty:
                pass
    
    # ==================== СВОЙСТВА ====================
    
    @property
    def message_queue(self) -> queue.Queue:
        return self._message_queue
    
    @property
    def script_dir(self) -> str:
        return str(APP_CONTEXT.working_dir)