#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Главный контроллер приложения, реализующий паттерн MVC.

Обеспечивает оркестрацию между моделью (бизнес-логика) и представлением (UI).
Контроллер принимает события от пользовательского интерфейса, валидирует данные,
вызывает соответствующие методы модели и обновляет представление.

Координация потоков:
    - Синхронные операции UI выполняются в главном потоке
    - Длительные операции (анализ, обработка файлов) делегируются асинхронным методам
    - Сообщения для UI передаются через потокобезопасную очередь
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

# MODEL - бизнес-логика приложения
from model.file_manager import FileManager, FileType
from model.process_runner import ProcessRunner, ProcessType
from model.gps_excluder import GPSExcluder
from model.file_transformer import FileTransformer
from model.analyzers.velocity_analyzer import VelocityAnalyzer
from model.analyzers.gps_constellation_analyzer import GPSConstellationAnalyzer
from model.user_paths_storage import UserPathsStorage

# VIEW - компоненты пользовательского интерфейса
from view.main_window import MainWindow
from view.dialogs import GPSExclusionDialog, TransformFileDialog
from view.analysis_windows.velocity_window import VelocityAnalysisWindow
from view.analysis_windows.gps_window import GPSAnalysisWindow


class ApplicationController:
    """
    Координатор взаимодействия между моделью и представлением.

    Контроллер принимает пользовательские действия из UI (методы on_*),
    выполняет единую валидацию данных и делегирует выполнение модели.
    Результаты работы модели передаются обратно в UI для отображения.

    Асинхронные операции запускаются через AsyncManager для сохранения
    отзывчивости интерфейса.

    Attributes:
        _message_queue: Потокобезопасная очередь сообщений для UI
        _file_manager: Менеджер файлов (модель)
        _process_runner: Управление внешними процессами (модель)
        _gps_excluder: Работа с исключёнными спутниками (модель)
        _file_transformer: Трансформация файлов (модель)
        _velocity_analyzer: Анализ скоростей (модель)
        _gps_analyzer: Анализ GPS созвездия (модель)
        _user_paths_storage: Хранилище последних путей пользователя (модель)
        _window: Главное окно приложения (представление)
        _async_manager: Менеджер асинхронных операций
    """

    def __init__(self):
        # Инициализация компонентов
        self._message_queue: queue.Queue[AppMessage] = queue.Queue(maxsize=1000)

        # MODEL - компоненты бизнес-логики
        self._file_manager = FileManager(APP_CONTEXT, self._publish_message)
        self._process_runner = ProcessRunner(self._publish_message)
        self._gps_excluder = GPSExcluder(APP_CONTEXT)
        self._file_transformer = FileTransformer(self._publish_message)
        self._velocity_analyzer = VelocityAnalyzer()
        self._gps_analyzer = GPSConstellationAnalyzer(
            target_points=5000,      # Целевое количество точек для сэмплирования
            min_gap_duration=2.0,    # Минимальная длительность разрыва (сек)
            merge_gap=5.0            # Интервал для объединения разрывов (сек)
        )

        # Инициализация хранилища путей
        self._user_paths_storage = UserPathsStorage(APP_CONTEXT.working_dir, "user_paths.txt")

        # VIEW - будет установлен при запуске
        self._window: Optional[MainWindow] = None

        # Асинхронный менеджер для длительных операций
        from async_manager import async_manager
        self._async_manager = async_manager
        self._async_manager.start()

    # ==================== ЖИЗНЕННЫЙ ЦИКЛ ПРИЛОЖЕНИЯ ====================

    def run(self) -> None:
        """Запускает главное окно приложения и входит в цикл обработки событий."""
        self._window = MainWindow(self)
        self._window.run()  # Виджеты создаются внутри run()

    def on_window_ready(self) -> None:
        """
        Вызывается из MainWindow после того, как все виджеты созданы.
        """
        self._load_initial_paths()

    def _load_initial_paths(self) -> None:
        """Загружает последние пути пользователя из хранилища и устанавливает их в FileManager и MainWindow."""
        self._publish_message(AppMessage.info("🔄 Загрузка последних путей...", source="Controller"))

        # Загружаем пути из хранилища
        saved_paths = self._user_paths_storage.get_all_paths()

        # Устанавливаем пути в FileManager и UI, если они существуют
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

                    # Обновляем UI, если окно уже создано
                    if self._window:
                        self._window.set_file_path(key, path)

                    self._publish_message(AppMessage.debug(
                        f"Загружен путь для {file_type.description}: {path}",
                        source="Controller"
                    ))
                except ValueError:
                    # Игнорируем неизвестные ключи
                    pass
            elif path:
                self._publish_message(AppMessage.warning(
                    f"Сохраненный путь не существует и будет пропущен: {path}",
                    source="Controller"
                ))

        self._publish_message(AppMessage.info("✅ Загрузка путей завершена.", source="Controller"))

    @property
    def app_context(self) -> AppContext:
        """Возвращает глобальный контекст приложения для доступа из представления."""
        return APP_CONTEXT

    # ==================== ЦЕНТРАЛИЗОВАННАЯ ВАЛИДАЦИЯ ====================

    def _validate_before_run(
        self,
        require_rover: bool = False,
        require_sr2nav: bool = False
    ) -> Tuple[bool, str]:
        """
        Проверяет наличие необходимых файлов перед запуском процесса.

        Единая точка валидации для всех операций, требующих файловой проверки.

        Args:
            require_rover: Если True, проверяет наличие файла ровера (.jps)
            require_sr2nav: Если True, проверяет наличие исполняемого файла SR2Nav.exe

        Returns:
            Кортеж (успех, сообщение_об_ошибке). При успехе сообщение пустое.
        """
        # Проверка наличия SR2Nav.exe
        if require_sr2nav:
            path = self._file_manager.get_original_path(FileType.SR2NAV_EXE)
            if not path:
                return False, "SR2Nav.exe не выбран"
            if not path.exists():
                return False, f"SR2Nav.exe не найден:\n{path}"

        # Проверка наличия файла ровера
        if require_rover:
            path = self._file_manager.get_original_path(FileType.ROVER)
            if not path:
                return False, "Файл ровера (JPS) не выбран"
            if not path.exists():
                return False, f"Файл ровера не найден:\n{path}"
            if path.suffix.lower() != '.jps':
                return False, f"Файл ровера должен быть .jps:\n{path.name}"

        # Проверка корректности угла отсечения
        try:
            angle = float(self._window.get_cutoff_angle())
            if angle < 0 or angle > 90:
                return False, "Угол отсечения должен быть от 0 до 90 градусов"
        except ValueError:
            return False, "Некорректное значение угла отсечения"

        return True, ""

    # ==================== ОБРАБОТЧИКИ СОБЫТИЙ ПОЛЬЗОВАТЕЛЬСКОГО ИНТЕРФЕЙСА ====================

    def on_file_selected(self, file_key: str, path: str) -> None:
        """
        Обрабатывает выбор файла пользователем через диалог открытия.

        Args:
            file_key: Строковый идентификатор типа файла (должен соответствовать FileType)
            path: Путь к выбранному файлу
        """
        try:
            file_type = FileType(file_key)

            # Особая обработка для файла ровера
            if file_type == FileType.ROVER:
                self._file_manager.set_rover_path(path)
                self._user_paths_storage.set_rover_path(path)
                # Обновляем заголовок окна именем файла ровера
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
                # Сохраняем путь для базы
                if file_type == FileType.BASE1:
                    self._user_paths_storage.set_base1_path(path)
                elif file_type == FileType.BASE2:
                    self._user_paths_storage.set_base2_path(path)
                # Для других типов файлов можно не сохранять

            # Сохраняем изменения в файл
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
        """
        Объединяет несколько JPS файлов в один.

        Args:
            input_files: Список путей к исходным JPS файлам
            output_path: Путь для сохранения объединённого файла
            target_key: Ключ поля в UI, куда установить результат (rover/base1/base2)
        """
        # Валидация существования входных файлов
        for file_path in input_files:
            if not os.path.exists(file_path):
                self._publish_message(AppMessage.error(
                    f"Файл не найден: {file_path}",
                    source="Controller"
                ))
                return

        # Вызов модели для объединения файлов
        success, message = self._file_manager.stitch_jps_files(input_files, output_path)

        # Обновление интерфейса в зависимости от результата
        if success:
            self._publish_message(AppMessage.info(message, source="Controller"))

            if target_key in ["rover", "base1", "base2"]:
                self._window.set_file_path(target_key, output_path)

                # Для ровера дополнительно обновляем заголовок и папку результатов
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
        """
        Открывает файл в программе, ассоциированной с его типом в ОС.

        Args:
            path: Путь к файлу для открытия
        """
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
        """Выполняет корректное завершение приложения при закрытии окна."""
        print("🛑 Завершение приложения...")

        # Останавливаем выполняющийся процесс, если он есть
        if self._process_runner.is_running:
            future = self._async_manager.run_coroutine(self._process_runner.terminate())
            future.result(timeout=2.0)

        # Останавливаем асинхронный менеджер
        self._async_manager.stop(timeout=1.0)

        sys.exit(0)

    def on_cleanup_working_directory(self) -> None:
        """
        Очищает рабочую директорию от временных файлов.

        Запрашивает подтверждение у пользователя, затем удаляет все файлы,
        кроме .exe, .py и защищённых папок (results, tbl и др.).
        """
        async def _run():
            # Запрашиваем подтверждение у пользователя
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

            # Вызываем метод модели для очистки
            deleted_count, errors = self._file_manager.cleanup_working_directory()

            # Формируем итоговое сообщение
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

    # ==================== ЗАПУСК ВНЕШНИХ ПРОЦЕССОВ ====================

    def on_run_interval(self) -> None:
        """Запускает Interval.exe для определения временного интервала."""
        # 1. Валидация наличия необходимых файлов
        success, error_msg = self._validate_before_run(require_rover=True, require_sr2nav=False)
        if not success:
            self._window.show_error("Ошибка", error_msg)
            self._publish_message(AppMessage.error(error_msg, source="Controller"))
            return

        async def _run():
            # 2. Переносим данные из UI в модель
            self._sync_files_from_ui()
            angle = self._window.get_cutoff_angle()
            self._file_manager.set_cutoff_angle(angle)
            
            # !!! ВАЖНО: Сбрасываем ручной режим перед запуском Interval
            self._file_manager.reset_manual_mode()

            # 3. Подготовка входных файлов для Interval
            success, msg, prepared_paths = await self._file_manager.run_interval()
            if not success:
                self._publish_message(AppMessage.error(msg, source="Controller"))
                return
            if not prepared_paths:
                self._publish_message(AppMessage.error("Не удалось подготовить файлы для Interval.", source="Controller"))
                return

            # 4. Запуск процесса Interval
            cmd = [str(APP_CONTEXT.interval_exe)]
            await self._process_runner.run(
                cmd,
                str(APP_CONTEXT.working_dir),
                ProcessType.INTERVAL,
                timeout=1.5,  # Интервал обычно работает быстро
            )

            # 5. Парсинг результата работы Interval
            success, msg = await self._file_manager.parse_interval_result()

            # 6. Обновляем интерфейс с полученным интервалом
            if success:
                interval = self._file_manager.time_interval
                self._window.update_time_interval(
                    interval.start,
                    interval.end,
                    is_manual=interval.manual  # теперь manual будет False
                )
                self._publish_message(AppMessage.info(msg, source="Controller"))
            else:
                self._publish_message(AppMessage.error(msg, source="Controller"))

            # 7. Пути в UI не обновляются, так как они всегда указывают на исходные файлы.

        self._run_async(_run())

    def on_interval_manually_changed(self, start: str, end: str) -> None:
        """
        Обрабатывает ручное изменение временного интервала пользователем.

        Args:
            start: Начало интервала в формате "HH:MM:SS"
            end: Конец интервала в формате "HH:MM:SS"
        """
        # Если оба поля пустые - сбрасываем ручной режим
        if not start.strip() and not end.strip():
            self._file_manager.reset_manual_mode()
            self._publish_message(AppMessage.debug(
                "🔄 Ручной режим интервала сброшен (поля очищены)",
                source="Controller"
            ))
            # Обновляем UI, чтобы убрать индикатор ручного режима
            if self._window:
                self._window.update_time_interval("", "", is_manual=False)
            return
        
        # Только если оба поля заполнены - устанавливаем ручной режим
        if start.strip() and end.strip():
            self._file_manager.update_time_interval(start, end, manual=True)
            self._publish_message(AppMessage.debug(
                f"✏️ Интервал изменён вручную: {start} - {end}",
                source="Controller"
            ))
            # Обновляем UI с флагом ручного режима
            if self._window:
                self._window.update_time_interval(start, end, is_manual=True)
        # Если одно поле пустое, а другое нет - игнорируем (неполный интервал)

    def on_run_sr2nav(self) -> None:
        """Запускает SR2Nav.exe для основной обработки данных."""
        # 1. Валидация наличия SR2Nav.exe
        success, error_msg = self._validate_before_run(require_rover=False, require_sr2nav=True)
        if not success:
            self._window.show_error("Ошибка", error_msg)
            self._publish_message(AppMessage.error(error_msg, source="Controller"))
            return

        async def _run():
            # 2. Переносим данные из UI в модель
            self._sync_files_from_ui()

            # 3. Очищаем директорию результатов перед запуском
            self._file_manager.cleanup_results_dir()

            # 4. Обновляем состояние UI (показываем индикатор выполнения)
            self._window.set_processing_state(True)

            # 5. Подготовка файлов для SR2Nav
            success, msg, prepared_paths = await self._file_manager.run_sr2nav()
            if not success:
                self._publish_message(AppMessage.error(msg, source="Controller"))
                self._window.set_processing_state(False)
                return
            if not prepared_paths:
                self._publish_message(AppMessage.error("Не удалось подготовить файлы для SR2Nav.", source="Controller"))
                self._window.set_processing_state(False)
                return

            # 6. Запуск процесса SR2Nav (может выполняться долго)
            # <-- ИЗМЕНЕНО: Путь к exe берём из prepared_paths, так как prepare_files теперь может
            # вернуть путь к оригинальному файлу, если он уже в рабочей директории.
            sr2nav_path_to_use = prepared_paths.get(FileType.SR2NAV_EXE)
            if not sr2nav_path_to_use:
                self._publish_message(AppMessage.error("SR2Nav.exe не был подготовлен.", source="Controller"))
                self._window.set_processing_state(False)
                return

            cmd = [str(sr2nav_path_to_use)]
            # <-- ИЗМЕНЕНО: Процесс запускается из рабочей директории. Это корректно,
            # даже если сам exe находится в другом месте, т.к. ему нужны файлы из рабочей директории.
            return_code = await self._process_runner.run(
                cmd,
                str(APP_CONTEXT.working_dir),
                ProcessType.SR2NAV,
                timeout=None,  # Без таймаута, процесс может быть длительным
            )

            # 7. Скрываем индикатор выполнения
            self._window.set_processing_state(False)

            # 8. Обработка результатов
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

            # 9. Пути в UI не обновляются.

        self._run_async(_run())

    def on_run_full_cycle(self) -> None:
        """Выполняет полный цикл обработки: Interval → SR2Nav."""
        # 1. Валидация наличия всех необходимых файлов
        success, error_msg = self._validate_before_run(require_rover=True, require_sr2nav=True)
        if not success:
            self._window.show_error("Ошибка", error_msg)
            self._publish_message(AppMessage.error(error_msg, source="Controller"))
            return

        async def _run():
            # 2. Переносим данные из UI в модель
            self._sync_files_from_ui()
            angle = self._window.get_cutoff_angle()
            self._file_manager.set_cutoff_angle(angle)

            # 3. Очищаем директорию результатов
            self._file_manager.cleanup_results_dir()

            # 4. Шаг 1: Запуск Interval.exe
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

            await asyncio.sleep(0.5)  # Небольшая пауза для визуального разделения шагов

            # 5. Шаг 2: Запуск SR2Nav.exe
            self._publish_message(AppMessage.info(
                "▶️ Шаг 2/2: Запуск SR2Nav.exe",
                source="Controller"
            ))

            # SR2Nav требует свои файлы. run_sr2nav подготовит их (скопирует или использует существующие).
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

            # <-- ИЗМЕНЕНО: Путь к exe берём из prepared_paths_sr2nav
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
            # Пути в UI не обновляются.

        self._run_async(_run())

    def on_terminate_process(self) -> None:
        """Принудительно останавливает выполняющийся внешний процесс."""
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

    # ==================== ДИАЛОГОВЫЕ ОКНА ====================

    def on_show_gps_exclusion_dialog(self) -> None:
        """Открывает диалог для настройки исключённых спутников."""
        if not self._window:
            return

        # Загружаем актуальный список исключённых спутников при каждом открытии
        current_excluded = self._gps_excluder.load_excluded()

        dialog = GPSExclusionDialog(
            self._window.window,
            current_excluded,
            self._on_gps_exclusion_saved
        )
        dialog.show()

    def _on_gps_exclusion_saved(self, excluded: Set[str]) -> None:
        """
        Сохраняет обновлённый список исключённых спутников.

        Args:
            excluded: Множество PRN номеров исключённых спутников
        """
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
        """Открывает диалог для трансформации файлов в формат TBL."""
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
        Преобразует выбранные файлы в формат TBL.

        Ищет файлы рекурсивно в исходной директории и сохраняет
        результаты в подпапке 'tbl'.

        Args:
            filenames: Список имён файлов для преобразования
            source_dir: Корневая директория для поиска файлов
        """
        async def _run():
            source_path = Path(source_dir)

            # Создаём папку tbl внутри исходной директории
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

            # Рекурсивный поиск и преобразование файлов
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

    def _perform_analysis(self,
                        window: Any,
                        analysis_name: str,
                        analyze_func: callable,
                        prepare_results_func: callable) -> None:
        """
        Общий метод для выполнения любого типа анализа данных.

        Инкапсулирует общую логику: проверку существования папки,
        выполнение анализа, обработку ошибок и обновление UI.

        Args:
            window: Окно анализа, которое будет обновлено результатами
            analysis_name: Название анализа для сообщений пользователю
            analyze_func: Функция модели, выполняющая анализ (принимает путь)
            prepare_results_func: Функция подготовки данных для отображения
        """
        async def _run():
            try:
                # Получаем путь из окна (он уже должен быть актуальным)
                folder_path = str(window.current_dir)

                self._publish_message(AppMessage.info(
                    f"🔍 {analysis_name} в папке: {folder_path}",
                    source="Controller"
                ))

                # Проверяем существование папки
                if not os.path.exists(folder_path):
                    error_msg = f"Папка не найдена: {folder_path}"
                    self._publish_message(AppMessage.error(error_msg, source="Controller"))
                    self._window.window.after(0, lambda: window.show_error(error_msg))
                    return

                # Выполняем анализ
                results = analyze_func(folder_path)

                if not results:
                    self._publish_message(AppMessage.warning(
                        f"В папке {folder_path} не найдено файлов для анализа",
                        source="Controller"
                    ))
                    self._window.window.after(0, lambda: window.show_error("Файлы не найдены"))
                    return

                # Подготавливаем результаты для отображения
                view_results, extra = prepare_results_func(results)

                # Обновляем UI в главном потоке (thread-safe)
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
        """Открывает окно для анализа скоростей."""
        if not self._window:
            return

        if not APP_CONTEXT.results_dir.exists():
            error_msg = f"Папка {APP_CONTEXT.results_dir.name} не найдена: {APP_CONTEXT.results_dir}"
            self._publish_message(AppMessage.error(error_msg, source="Controller"))
            from tkinter import messagebox
            messagebox.showerror("Ошибка", error_msg, parent=self._window.window)
            return

        VelocityAnalysisWindow(self._window.window, self)

    def request_velocity_analysis(self, window: VelocityAnalysisWindow, folder_path: str) -> None:
        """
        Выполняет анализ скоростей по запросу из окна анализа.

        Args:
            window: Экземпляр окна анализа скоростей
            folder_path: Путь к папке с данными для анализа
        """
        window.current_dir = Path(folder_path)

        self._perform_analysis(
            window=window,
            analysis_name="Анализ скоростей",
            analyze_func=lambda path: self._velocity_analyzer.analyze_all(path),
            prepare_results_func=self._prepare_velocity_results_for_view
        )

    def _prepare_velocity_results_for_view(self, results: Dict) -> Tuple[Dict, Dict]:
        """
        Преобразует результаты анализа скоростей из формата модели в формат представления.

        Args:
            results: Сырые результаты от VelocityAnalyzer

        Returns:
            Кортеж (данные_для_таблицы, сводная_статистика)
        """
        view_results = {}
        for filename, result in results.items():
            # Убеждаемся, что у нас есть объект результата, а не сырой словарь
            # В текущей реализации result - это VelocityAnalysisResult
            view_results[filename] = {
                'data': {
                    'time': result.data.time.tolist() if hasattr(result.data.time, 'tolist') else result.data.time,
                    'v_e': result.data.v_e.tolist() if hasattr(result.data.v_e, 'tolist') else result.data.v_e,
                    'v_n': result.data.v_n.tolist() if hasattr(result.data.v_n, 'tolist') else result.data.v_n,
                    'v_up': result.data.v_up.tolist() if hasattr(result.data.v_up, 'tolist') else result.data.v_up,
                    'height': result.data.height.tolist() if hasattr(result.data.height, 'tolist') else result.data.height,
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
                    'max_height_4th_diff': result.statistics.max_height_4th_diff,
                }
            }

        # Получаем сводную статистику по всем файлам
        summary = self._velocity_analyzer.get_summary_statistics()

        return view_results, summary

    def export_velocity_analysis(self, output_file: str) -> bool:
        """
        Экспортирует результаты анализа скоростей в CSV файл.

        Args:
            output_file: Путь для сохранения CSV файла

        Returns:
            True если экспорт успешен, иначе False
        """
        return self._velocity_analyzer.export_to_csv(output_file)

    def on_analyze_gps_constellation(self) -> None:
        """Открывает окно для анализа GPS созвездия."""
        if not self._window:
            return

        if not APP_CONTEXT.results_dir.exists():
            error_msg = f"Папка {APP_CONTEXT.results_dir.name} не найдена: {APP_CONTEXT.results_dir}"
            self._publish_message(AppMessage.error(error_msg, source="Controller"))
            from tkinter import messagebox
            messagebox.showerror("Ошибка", error_msg, parent=self._window.window)
            return

        GPSAnalysisWindow(self._window.window, self)

    def request_gps_analysis(self, window: GPSAnalysisWindow, folder_path: str) -> None:
        """
        Выполняет анализ GPS созвездия по запросу из окна анализа.

        Args:
            window: Экземпляр окна анализа GPS
            folder_path: Путь к папке с данными для анализа
        """
        window.current_dir = Path(folder_path)

        self._perform_analysis(
            window=window,
            analysis_name="Анализ GPS созвездия",
            analyze_func=lambda path: self._gps_analyzer.analyze_all(path),
            prepare_results_func=self._prepare_gps_results_for_view
        )

    def _prepare_gps_results_for_view(self, results: Dict) -> Tuple[Dict, None]:
        """
        Преобразует результаты GPS анализа из формата модели в формат представления.

        Args:
            results: Сырые результаты от GPSConstellationAnalyzer

        Returns:
            Кортеж (данные_для_отображения, None) - второй элемент не используется
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
        """
        Экспортирует результаты анализа GPS созвездия в CSV файл.

        Args:
            output_file: Путь для сохранения CSV файла

        Returns:
            True если экспорт успешен, иначе False
        """
        return self._gps_analyzer.export_to_csv(output_file)

    # ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================

    def _sync_files_from_ui(self) -> None:
        """Переносит актуальные пути из пользовательского интерфейса в модель."""
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
        """
        Запускает корутину асинхронно, не блокируя основной поток UI.

        Args:
            coro: Корутина для асинхронного выполнения
        """
        self._async_manager.run_coroutine(coro)

    def _publish_message(self, message: AppMessage) -> None:
        """
        Помещает сообщение в очередь для отображения в UI.

        Очередь имеет ограниченный размер (1000). При переполнении
        удаляется самое старое сообщение.

        Args:
            message: Сообщение для публикации
        """
        try:
            self._message_queue.put_nowait(message)
        except queue.Full:
            # При переполнении удаляем одно сообщение и добавляем новое
            try:
                self._message_queue.get_nowait()
                self._message_queue.put_nowait(message)
            except queue.Empty:
                pass

    # ==================== СВОЙСТВА ДЛЯ ДОСТУПА ИЗ ВНЕШНИХ КОМПОНЕНТОВ ====================

    @property
    def message_queue(self) -> queue.Queue:
        """Очередь сообщений для отображения в пользовательском интерфейсе."""
        return self._message_queue

    @property
    def script_dir(self) -> str:
        """Рабочая директория скрипта (устаревшее свойство, лучше использовать app_context)."""
        return str(APP_CONTEXT.working_dir)