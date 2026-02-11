#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Главный контроллер приложения.
Оркестрирует взаимодействие между Backend и Frontend.
Никакой бизнес-логики, только координация.
"""
import asyncio
import queue
from typing import Optional

from core.app_context import APP_CONTEXT, AppContext
from core.message_system import AppMessage, MessageLevel

from backend.file_manager import FileManager, FileType
from backend.process_runner import ProcessRunner, ProcessType
from backend.gps_excluder import GPSExcluder
from backend.file_transformer import FileTransformer
from backend.analyzers.velocity_analyzer import VelocityFileAnalyzer
from backend.analyzers.gps_constellation_analyzer import GPSConstellationAnalyzer


class ApplicationController:
    """
    Контроллер в паттерне MVC.
    
    Ответственности:
        - Инициализация компонентов
        - Маршрутизация событий от UI к Backend
        - Управление очередью сообщений
        - Запуск асинхронных задач
    """
    
    def __init__(self):
        # Потокобезопасная очередь сообщений
        self._message_queue: queue.Queue[AppMessage] = queue.Queue(maxsize=1000)
        
        # Инициализация Backend компонентов
        self._file_manager = FileManager(APP_CONTEXT, self._publish_message)
        self._process_runner = ProcessRunner(self._publish_message)
        self._gps_excluder = GPSExcluder(APP_CONTEXT)
        self._file_transformer = FileTransformer(self._publish_message)
        
        # Frontend (инициализируется в run())
        self._window = None
        
        # Async менеджер
        self._async_manager = None
    
    # ==================== ЖИЗНЕННЫЙ ЦИКЛ ====================
    
    def run(self) -> None:
        """Запускает приложение."""
        # Импортируем асинхронный менеджер (чтобы избежать циклических импортов)
        from async_manager import async_manager
        
        self._async_manager = async_manager
        self._async_manager.start()
        
        # Импортируем и создаём главное окно
        from frontend.main_window import MainWindow
        
        self._window = MainWindow(self)
        self._window.run()
    
    # ==================== ОБРАБОТЧИКИ СОБЫТИЙ ИЗ UI ====================
    
    # ----- Файлы -----
    
    def on_file_selected(self, file_key: str, path: str) -> None:
        """Обработчик выбора файла в UI."""
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
    
    def on_stitch_jps(self, input_files: list, output_path: str) -> None:
        """Обработчик сшивания JPS файлов."""
        success, message = self._file_manager.stitch_jps_files(input_files, output_path)
        
        if success:
            self._publish_message(AppMessage.info(message, source="Controller"))
        else:
            self._publish_message(AppMessage.error(message, source="Controller"))
    
    # ----- Запуск процессов -----
    
    def on_run_interval(self) -> None:
        """Запуск Interval.exe."""
        async def _run():
            # 1. Синхронизация путей из UI
            self._sync_files_from_ui()
            
            # 2. Установка угла отсечения
            angle = self._window.get_cutoff_angle()
            self._file_manager.set_cutoff_angle(angle)
            
            # 3. Подготовка и запуск
            success, msg = await self._file_manager.run_interval()
            if not success:
                self._publish_message(AppMessage.error(msg, source="Controller"))
                return
            
            # 4. Запуск процесса
            cmd = [str(APP_CONTEXT.interval_exe)]
            return_code = await self._process_runner.run(
                cmd,
                str(APP_CONTEXT.working_dir),
                ProcessType.INTERVAL,
                timeout=1.5,
            )
            
            # 5. Парсинг результата
            success, msg = await self._file_manager.parse_interval_result()
            
            if success:
                interval = self._file_manager.time_interval
                self._window.update_time_interval(interval.start, interval.end)
                self._publish_message(AppMessage.info(msg, source="Controller"))
            else:
                self._publish_message(AppMessage.error(msg, source="Controller"))
            
            # 6. Синхронизация путей обратно в UI
            self._sync_paths_to_ui()
        
        self._run_async(_run())
    
    def on_run_sr2nav(self) -> None:
        """Запуск SR2Nav.exe."""
        async def _run():
            # 1. Синхронизация
            self._sync_files_from_ui()
            
            # 2. Подготовка
            success, msg = await self._file_manager.run_sr2nav()
            if not success:
                self._publish_message(AppMessage.error(msg, source="Controller"))
                return
            
            # 3. Применение исключённых спутников
            self._gps_excluder.save_excluded(self._gps_excluder.load_excluded())
            
            # 4. UI индикация
            self._window.set_processing_state(True)
            
            # 5. Запуск процесса
            sr2nav_path = self._file_manager.get_path(FileType.SR2NAV_EXE)
            if not sr2nav_path:
                self._window.set_processing_state(False)
                self._publish_message(AppMessage.error(
                    "SR2Nav.exe не найден",
                    source="Controller"
                ))
                return
            
            cmd = [str(sr2nav_path)]
            return_code = await self._process_runner.run(
                cmd,
                str(APP_CONTEXT.working_dir),
                ProcessType.SR2NAV,
                timeout=None,
            )
            
            # 6. Завершение
            self._window.set_processing_state(False)
            
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
            
            # 7. Синхронизация путей
            self._sync_paths_to_ui()
        
        self._run_async(_run())
    
    def on_run_full_cycle(self) -> None:
        """Полный цикл: Interval.exe → SR2Nav.exe."""
        async def _run():
            # 1. Синхронизация
            self._sync_files_from_ui()
            
            # 2. Угол отсечения
            angle = self._window.get_cutoff_angle()
            self._file_manager.set_cutoff_angle(angle)
            
            # 3. Interval.exe
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
            
            # 4. SR2Nav.exe
            self._publish_message(AppMessage.info(
                "▶️ Шаг 2/2: Запуск SR2Nav.exe",
                source="Controller"
            ))
            
            success, msg = await self._file_manager.run_sr2nav()
            if not success:
                self._publish_message(AppMessage.error(msg, source="Controller"))
                return
            
            self._window.set_processing_state(True)
            
            sr2nav_path = self._file_manager.get_path(FileType.SR2NAV_EXE)
            if sr2nav_path:
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
        """Принудительная остановка текущего процесса."""
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
    
    # ----- Анализ данных -----
    
    def on_analyze_velocities(self) -> None:
        """Анализ VEL файлов."""
        try:
            analyzer = VelocityFileAnalyzer(APP_CONTEXT.results_dir)
            results = analyzer.analyze_all()
            
            from frontend.widgets import VelocityAnalysisDialog
            
            dialog = VelocityAnalysisDialog(
                self._window.window,
                results,
                self._publish_message,
            )
            dialog.show()
            
        except Exception as e:
            self._publish_message(AppMessage.error(
                f"Ошибка анализа скоростей: {e}",
                source="Controller"
            ))
    
    def on_analyze_gps_constellation(self) -> None:
        """Анализ GPS созвездия."""
        try:
            analyzer = GPSConstellationAnalyzer(APP_CONTEXT.results_dir)
            results = analyzer.analyze_all()
            
            from frontend.widgets import GPSConstellationDialog
            
            dialog = GPSConstellationDialog(
                self._window.window,
                results,
                self._publish_message,
            )
            dialog.show()
            
        except Exception as e:
            self._publish_message(AppMessage.error(
                f"Ошибка анализа GPS созвездия: {e}",
                source="Controller"
            ))
    
    def on_transform_files(self, filenames: list) -> None:
        """Трансформация файлов в TBL."""
        async def _run():
            for filename in filenames:
                src = APP_CONTEXT.results_dir / filename
                dst = APP_CONTEXT.tbl_dir / f"{src.stem}.tbl"
                
                file_type = self._file_transformer.detect_file_type(filename)
                if file_type:
                    success = await self._file_transformer.transform(src, dst, file_type)
                    if success:
                        self._publish_message(AppMessage.info(
                            f"✓ {filename} → {dst.name}",
                            source="Controller"
                        ))
        
        self._run_async(_run())
    
    def on_show_gps_exclusion_dialog(self) -> None:
        """Показывает диалог исключения спутников."""
        if self._window:
            excluded = self._gps_excluder.show_dialog(self._window.window)
            
            if excluded is not None:
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
    
    # ----- Файловые операции -----
    
    def on_open_file(self, path: str) -> None:
        """Открывает файл в системном приложении."""
        import subprocess
        import os
        
        if os.path.exists(path):
            try:
                if os.name == 'nt':
                    subprocess.Popen(['start', path], shell=True)
                else:
                    subprocess.Popen(['xdg-open', path])
            except Exception as e:
                self._publish_message(AppMessage.error(
                    f"Не удалось открыть файл: {e}",
                    source="Controller"
                ))
    
    # ==================== ВНУТРЕННИЕ МЕТОДЫ ====================
    
    def _sync_files_from_ui(self) -> None:
        """Синхронизирует пути из UI в FileManager."""
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
        """Синхронизирует пути из FileManager в UI."""
        if not self._window:
            return
        
        paths = self._file_manager.get_all_paths()
        self._window.sync_file_paths(paths)
    
    def _run_async(self, coro) -> None:
        """Запускает корутину в асинхронном менеджере."""
        if self._async_manager:
            self._async_manager.run_coroutine(coro)
    
    def _publish_message(self, message: AppMessage) -> None:
        """
        Публикует сообщение в очередь.
        Thread-safe.
        """
        try:
            self._message_queue.put_nowait(message)
        except queue.Full:
            try:
                self._message_queue.get_nowait()
                self._message_queue.put_nowait(message)
            except queue.Empty:
                pass
    
    # ==================== СВОЙСТВА ДЛЯ FRONTEND ====================
    
    @property
    def message_queue(self) -> queue.Queue:
        """Очередь сообщений для UI."""
        return self._message_queue
    
    @property
    def script_dir(self) -> str:
        """Рабочая директория (для обратной совместимости)."""
        return str(APP_CONTEXT.working_dir)