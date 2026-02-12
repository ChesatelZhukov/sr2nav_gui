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
        """
        Сшивание JPS файлов.
        
        Args:
            input_files: Список входных файлов
            output_path: Путь к выходному файлу
            target_key: Ключ файла, в который подставить результат (rover/base1/base2)
        """
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
            
            # ИСПРАВЛЕНО: автоматически подставляем путь в соответствующий виджет
            if target_key in ["rover", "base1", "base2"]:
                self._window.set_file_path(target_key, output_path)
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
            self._gps_excluder.save_excluded(self._gps_excluder.load_excluded())
            
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
                self._file_manager.move_results_to_results_dir()
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
                self._file_manager.move_results_to_results_dir()
            
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
        
        # 1. Получаем текущие исключённые спутники из Model
        current_excluded = self._gps_excluder.load_excluded()
        
        # 2. Создаём View с callback на сохранение
        dialog = GPSExclusionDialog(
            self._window.window,
            current_excluded,
            self._on_gps_exclusion_saved  # Callback в контроллер
        )
        
        # 3. Показываем диалог
        dialog.show()
    
    def _on_gps_exclusion_saved(self, excluded: Set[str]) -> None:
        """Callback сохранения исключённых спутников."""
        # Сохраняем в Model
        success = self._gps_excluder.save_excluded(excluded)
        
        # Обновляем View
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
            self._on_transform_files  # Callback в контроллер
        )
        dialog.show()
    
    def _on_transform_files(self, filenames: List[str]) -> None:
        """Callback трансформации файлов."""
        async def _run():
            for filename in filenames:
                src = APP_CONTEXT.results_dir / filename
                dst = APP_CONTEXT.tbl_dir / f"{src.stem}.tbl"
                
                if not src.exists():
                    self._publish_message(AppMessage.error(
                        f"Файл не найден: {filename}",
                        source="Controller"
                    ))
                    continue
                
                file_type = self._file_transformer.detect_file_type(filename)
                if file_type:
                    success = await self._file_transformer.transform(src, dst, file_type)
                    if success:
                        self._publish_message(AppMessage.info(
                            f"✓ {filename} → {dst.name}",
                            source="Controller"
                        ))
        
        self._run_async(_run())
    
    # ==================== АНАЛИЗ ДАННЫХ ====================
    
    def on_analyze_velocities(self) -> None:
        """Запрос на анализ скоростей."""
        if not self._window:
            return
        
        # Проверяем существование папки results
        if not APP_CONTEXT.results_dir.exists():
            self._publish_message(AppMessage.error(
                f"Папка results не найдена: {APP_CONTEXT.results_dir}",
                source="Controller"
            ))
            return
        
        # Создаём окно анализа (View)
        # Оно само запросит данные через request_velocity_analysis()
        VelocityAnalysisWindow(self._window.window, self)
    
    def request_velocity_analysis(self, window: VelocityAnalysisWindow) -> None:
        """
        Обработка запроса от окна анализа скоростей.
        Выполняется асинхронно, чтобы не блокировать UI.
        """
        async def _run():
            # 1. Анализ данных (Model)
            results = self._velocity_analyzer.analyze_all(str(APP_CONTEXT.results_dir))
            
            # 2. Получение сводной статистики (Model)
            summary = self._velocity_analyzer.get_summary_statistics()
            
            # 3. Преобразование данных для View
            view_results = self._prepare_velocity_results_for_view(results)
            
            # 4. Обновление View (в главном потоке Tkinter)
            self._window.window.after(0, lambda: window.update_results(view_results, summary))
        
        self._run_async(_run())
    
    def _prepare_velocity_results_for_view(self, results: Dict) -> Dict:
        """
        Преобразует результаты Model в формат для View.
        View не должно знать о структуре Model!
        """
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
                f"Папка results не найдена: {APP_CONTEXT.results_dir}",
                source="Controller"
            ))
            return
        
        # Создаём окно анализа (View)
        GPSAnalysisWindow(self._window.window, self)
    
    def request_gps_analysis(self, window: GPSAnalysisWindow) -> None:
        """
        Обработка запроса от окна анализа GPS созвездия.
        ИСПРАВЛЕНО: корректная обработка ошибок и скрытие индикатора загрузки.
        """
        async def _run():
            try:
                # 1. Анализ данных (Model)
                results = self._gps_analyzer.analyze_all(str(APP_CONTEXT.results_dir))
                
                # 2. Преобразование данных для View
                view_results = self._prepare_gps_results_for_view(results)
                
                # 3. Обновление View (в главном потоке Tkinter)
                self._window.window.after(0, lambda: window.update_results(view_results))
                
            except Exception as e:
                # 4. КРИТИЧЕСКИ ВАЖНО: скрываем загрузку и показываем ошибку
                error_msg = f"Ошибка анализа GPS созвездия: {str(e)}"
                self._publish_message(AppMessage.error(error_msg, source="Controller"))
                
                # Передаём ошибку в окно
                self._window.window.after(0, lambda: window.show_error(error_msg))
        
        self._run_async(_run())
    
    def _prepare_gps_results_for_view(self, results: Dict) -> Dict:
        """
        Преобразует результаты GPS анализа в формат для View.
        ИСПРАВЛЕНО: добавлено intervals_per_minute!
        """
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
                    'intervals_per_minute': stats.intervals_per_minute,  # <-- ЭТО БЫЛО ПОТЕРЯНО!
                    'intervals': [
                        {'start': i.start, 'end': i.end, 'duration': i.duration}
                        for i in stats.intervals
                    ]
                }
            
            
            # Добавляем сводный отчет
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