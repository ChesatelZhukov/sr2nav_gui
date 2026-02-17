#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Менеджер файлов - центральный компонент для всех файловых операций.

Отвечает за:
    - Управление исходными путями к файлам, выбранными пользователем.
    - Копирование файлов в рабочую директорию для обработки (по запросу), если это необходимо.
    - Проверку и исправление JPS заголовков.
    - Создание конфигурационных файлов (Mask.Ang, SR2Nav.cfg).
    - Обработку временных интервалов.
    - Сшивание JPS файлов.
    - Очистку рабочей директории.

Важное архитектурное решение:
    Класс НЕ ПРОВЕРЯЕТ существование файлов - это ответственность контроллера.
    Контроллер гарантирует, что все переданные пути валидны.
    Методы prepare_files, run_interval, run_sr2nav теперь возвращают пути
    к скопированным файлам (или оригинальным, если они уже в рабочей директории),
    не изменяя внутреннее состояние _working_paths без необходимости.
"""
import os
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Tuple, List, Callable
import re

from core.app_context import APP_CONTEXT, AppContext
from core.message_system import AppMessage


class FileType(Enum):
    """
    Типы файлов, используемые в приложении.

    Каждый тип имеет:
        - Расширение файла (extension)
        - Человекочитаемое описание (description)
        - Флаг обязательности (is_required)

    Значения используются как ключи для синхронизации с UI.
    """
    ROVER = "rover"
    BASE1 = "base1"
    BASE2 = "base2"
    POS1 = "pos1"
    POS2 = "pos2"
    CFG = "cfg"
    AIR = "air"
    SR2NAV_EXE = "sr2nav"

    @property
    def extension(self) -> str:
        """Ожидаемое расширение файла для данного типа."""
        return {
            FileType.ROVER: '.jps',
            FileType.BASE1: '.jps',
            FileType.BASE2: '.jps',
            FileType.POS1: '.pos',
            FileType.POS2: '.pos',
            FileType.CFG: '.cfg',
            FileType.AIR: '.air',
            FileType.SR2NAV_EXE: '.exe',
        }[self]

    @property
    def description(self) -> str:
        """Человекочитаемое описание для отображения в UI."""
        return {
            FileType.ROVER: "Файл ровера (JPS)",
            FileType.BASE1: "Файл базы 1 (JPS)",
            FileType.BASE2: "Файл базы 2 (JPS)",
            FileType.POS1: "POS файл базы 1",
            FileType.POS2: "POS файл базы 2",
            FileType.CFG: "Конфигурационный файл",
            FileType.AIR: "Файл гравики",
            FileType.SR2NAV_EXE: "Исполняемый файл SR2Nav",
        }[self]

    @property
    def is_required(self) -> bool:
        """
        Флаг обязательности файла для базовой работы.

        Returns:
            True для критических файлов (ровер, SR2Nav.exe)
        """
        return self in (FileType.ROVER, FileType.SR2NAV_EXE)


@dataclass
class TimeInterval:
    """
    Временной интервал для обработки данных.

    Поддерживает два режима:
        - Ручной: установлен пользователем через UI
        - Автоматический: получен от Interval.exe

    Attributes:
        start: Начало интервала в формате "HH:MM:SS"
        end: Конец интервала в формате "HH:MM:SS"
        manual: True если интервал установлен вручную
    """
    start: str = ""
    end: str = ""
    manual: bool = False  # True = ручной режим, False = из Interval.exe

    @property
    def is_valid(self) -> bool:
        """Проверяет, задан ли интервал (не пустой)."""
        return bool(self.start and self.end)

    def set_manual(self, start: str, end: str) -> None:
        """Устанавливает интервал вручную (пользовательский режим)."""
        self.start = start
        self.end = end
        self.manual = True

    def set_auto(self, start: str, end: str) -> None:
        """Устанавливает интервал из результатов Interval.exe."""
        self.start = start
        self.end = end
        self.manual = False


class FileManager:
    """
    Менеджер файлов - центральный компонент файловых операций.

    Управляет двумя наборами путей:
        - _original_paths: пути, указанные пользователем (могут быть где угодно). Это единственное место,
          которое хранит исходные пути, отображаемые в UI.
        - _working_paths: внутренний словарь, который используется для временного хранения
          путей к файлам, скопированным в рабочую директорию. Он обновляется только в момент
          подготовки к запуску (prepare_files) и НЕ синхронизируется с UI.

    Принципы работы:
        1. Контроллер гарантирует существование файлов перед вызовом методов.
        2. Методы set_* обновляют только _original_paths.
        3. Метод prepare_files() создает копии в рабочей директории, ЕСЛИ ИСХОДНЫЙ ФАЙЛ НЕ В РАБОЧЕЙ ДИРЕКТОРИИ,
           и возвращает словарь путей к этим копиям (или оригинальным файлам, если они уже в рабочей директории).
           Он же обновляет _working_paths для внутреннего использования в других методах
           (например, create_config_files), которые ожидают файлы в рабочей директории.
        4. После завершения обработки состояние _working_paths сбрасывается.
    """

    # Паттерны файлов, создаваемых SR2Nav
    RESULT_FILE_PATTERNS = [
        '*.ins',
        'Phase*.VEL',
        '*_Std.QC',
        'Phase.QC',
        '*.EXIT',
        'Visible*.SVs',
    ]

    # Заголовок JPS файла в разных кодировках
    JPS_HEADER = "JP055"
    JPS_HEADER_BYTES = JPS_HEADER.encode('cp1251')

    def __init__(self, context: AppContext, message_callback: Callable[[AppMessage], None]):
        """
        Инициализация менеджера файлов.

        Args:
            context: Контекст приложения с базовыми путями
            message_callback: Функция для отправки сообщений в систему логирования
        """
        self._ctx = context
        self._message_callback = message_callback

        # Словарь исходных путей к файлам (от пользователя). Отображается в UI.
        self._original_paths: Dict[FileType, Path] = {}

        # Внутренний словарь путей в рабочей директории (после копирования). НЕ отображается в UI.
        self._working_paths: Dict[FileType, Path] = {}

        # Параметры обработки
        self._cutoff_angle: float = 7.0
        self._time_interval = TimeInterval()

    # ==================== ПУБЛИЧНЫЙ API ДЛЯ УПРАВЛЕНИЯ ПУТЯМИ ====================

    def set_path(self, file_type: FileType, path: str | Path) -> None:
        """
        Устанавливает исходный путь к файлу.

        Этот метод обновляет только _original_paths. Он больше не копирует файл
        и не обновляет _working_paths.

        Args:
            file_type: Тип файла
            path: Путь к файлу (пустая строка или None для сброса)
        """
        if not path or str(path).strip() == '':
            self._original_paths.pop(file_type, None)
            return

        path_obj = Path(path)
        self._original_paths[file_type] = path_obj

    def set_rover_path(self, path: str | Path) -> None:
        """
        Специализированный метод для установки исходного пути к роверу.

        Кроме базового обновления пути, также создаёт именованную папку результатов
        на основе имени файла и обновляет контекст приложения.

        Args:
            path: Путь к JPS файлу ровера (пустая строка для сброса)
        """
        if not path or str(path).strip() == '':
            self._original_paths.pop(FileType.ROVER, None)
            return

        path_obj = Path(path)
        self._original_paths[FileType.ROVER] = path_obj

        # Создаём папку результатов на основе имени файла ровера
        new_dir = self._ctx.set_results_dir_from_rover(str(path))
        self._send_message(AppMessage.info(
            f"📁 Папка результатов: {new_dir.name}",
            source="FileManager"
        ))

    def get_original_path(self, file_type: FileType) -> Optional[Path]:
        """
        Возвращает исходный путь к файлу (указанный пользователем).

        Args:
            file_type: Тип файла

        Returns:
            Оригинальный Path или None, если файл не выбран
        """
        return self._original_paths.get(file_type)

    def get_all_original_paths(self) -> Dict[str, str]:
        """
        Возвращает словарь исходных путей для синхронизации с UI.

        Returns:
            Словарь {ключ_файла: путь} для всех типов файлов, где путь не пустой
        """
        result = {}
        for file_type in FileType:  # Итерируемся по всем типам
            path = self._original_paths.get(file_type)
            if path:  # Возвращаем только непустые пути
                result[file_type.value] = str(path)
        return result

    # ==================== ПАРАМЕТРЫ ОБРАБОТКИ ====================

    @property
    def cutoff_angle(self) -> float:
        """Угол отсечения в градусах (7.0 по умолчанию)."""
        return self._cutoff_angle

    def set_cutoff_angle(self, angle: float) -> None:
        """Устанавливает угол отсечения с округлением до 0.1°."""
        self._cutoff_angle = round(angle, 1)

    @property
    def time_interval(self) -> TimeInterval:
        """Текущий временной интервал с указанием режима (ручной/авто)."""
        return self._time_interval

    # ==================== ПОДГОТОВКА ФАЙЛОВ К ЗАПУСКУ ====================

    def cleanup_results_dir(self, force: bool = False) -> Tuple[int, bool]:
        """
        Очищает папку результатов от старых файлов перед новым запуском.

        Алгоритм:
            1. Проверяет наличие файлов по паттернам RESULT_FILE_PATTERNS
            2. Если файлы есть и не force=True - запрашивает подтверждение
            3. Удаляет найденные файлы

        Args:
            force: Если False, проверяет наличие файлов и возвращает флаг подтверждения

        Returns:
            (количество удаленных файлов, нужно_ли_подтверждение)
        """
        patterns = self.RESULT_FILE_PATTERNS
        deleted = 0
        existing_files = []

        results_dir = self._ctx.results_dir

        if not results_dir.exists():
            results_dir.mkdir(parents=True, exist_ok=True)
            return 0, False

        # Сбор существующих файлов
        for pattern in patterns:
            existing_files.extend(list(results_dir.glob(pattern)))

        # Запрос подтверждения при наличии файлов
        if existing_files and not force:
            self._send_message(AppMessage.warning(
                f"⚠️ В папке {results_dir.name} найдены файлы ({len(existing_files)} шт.)\n"
                f"Очистка удалит их перед запуском.",
                source="FileManager"
            ))
            return 0, True

        # Удаление файлов
        for pattern in patterns:
            for file_path in results_dir.glob(pattern):
                try:
                    file_path.unlink()
                    deleted += 1
                    self._send_message(AppMessage.debug(
                        f"🧹 Удалён старый результат: {file_path.name}",
                        source="FileManager"
                    ))
                except Exception as e:
                    self._send_message(AppMessage.warning(
                        f"Не удалось удалить {file_path.name}: {e}",
                        source="FileManager"
                    ))

        return deleted, False

    def _is_path_in_working_dir(self, path: Path) -> bool:
        """
        Проверяет, находится ли указанный путь в рабочей директории или её подпапке.

        Args:
            path: Путь для проверки

        Returns:
            True, если путь находится внутри рабочей директории.
        """
        try:
            # resolve() для обработки символических ссылок и нормализации
            working_dir_resolved = self._ctx.working_dir.resolve()
            path_resolved = path.resolve()
            
            # Проверяем, является ли путь родительским для рабочей директории или наоборот
            return (working_dir_resolved == path_resolved or 
                    working_dir_resolved in path_resolved.parents)
        except Exception:
            # В случае ошибки (например, path не существует) считаем, что не в рабочей директории
            return False

    def prepare_files(self, files_to_copy: List[FileType]) -> Tuple[bool, str, Dict[FileType, Path]]:
        """
        Подготавливает указанные файлы для работы в рабочей директории.

        Алгоритм для каждого файла:
            1. Если файл уже находится в рабочей директории (или подпапке),
               используем его как есть, без копирования.
            2. В противном случае копируем файл в корень рабочей директории.

        Args:
            files_to_copy: Список типов файлов (FileType), которые нужно подготовить.

        Returns:
            (успех, сообщение, словарь {тип_файла: путь_для_использования})
        """
        self._send_message(AppMessage.info("📋 Подготовка файлов к обработке..."))
        prepared_paths: Dict[FileType, Path] = {}
        self._working_paths.clear()  # Сбрасываем предыдущее состояние

        for file_type in files_to_copy:
            src_path = self._original_paths.get(file_type)
            if not src_path:
                self._send_message(AppMessage.warning(
                    f"Пропуск {file_type.description}: исходный файл не выбран.",
                    source="FileManager"
                ))
                continue

            if not src_path.exists():
                return False, f"Исходный файл не найден: {src_path}", prepared_paths

            # <-- НОВАЯ ЛОГИКА: Проверяем, не находится ли файл уже в рабочей директории
            if self._is_path_in_working_dir(src_path):
                # Файл уже в рабочей директории. Используем исходный путь.
                use_path = src_path
                self._send_message(AppMessage.debug(
                    f"✓ {src_path.name} уже в рабочей директории, копирование не требуется.",
                    source="FileManager"
                ))
            else:
                # Файл вне рабочей директории. Копируем.
                dst_path = self._ctx.working_dir / src_path.name

                # Защита от случайной перезаписи, если файл с таким именем уже есть (из другой папки)
                if dst_path.exists():
                    self._send_message(AppMessage.warning(
                        f"⚠️ Файл {dst_path.name} уже существует в рабочей директории и будет перезаписан.",
                        source="FileManager"
                    ))
                try:
                    # Для больших JPS файлов - копирование с прогрессом
                    if file_type in (FileType.ROVER, FileType.BASE1, FileType.BASE2):
                        self._copy_large_file(src_path, dst_path)
                    else:
                        shutil.copy2(src_path, dst_path)
                    use_path = dst_path
                    self._send_message(AppMessage.info(
                        f"✓ {src_path.name} скопирован в рабочую директорию."
                    ))
                except Exception as e:
                    return False, f"Ошибка копирования {src_path.name}: {e}", prepared_paths

            prepared_paths[file_type] = use_path
            # Сохраняем в _working_paths ТОЛЬКО если путь ведет в рабочую директорию.
            # Для create_config_files нужны только имена файлов, а они будут корректны,
            # так как use_path.name всегда вернет правильное имя.
            # Но для единообразия сохраняем все, т.к. _working_paths используется внутри FileManager.
            self._working_paths[file_type] = use_path

        if not prepared_paths:
            return False, "Не удалось подготовить ни одного файла.", prepared_paths

        return True, "Подготовка файлов завершена", prepared_paths

    def _copy_large_file(self, src: Path, dst: Path, chunk_size: int = 64 * 1024 * 1024) -> None:
        """
        Копирует большой файл с отчётом о прогрессе каждые 10%.

        Args:
            src: Исходный файл
            dst: Целевой файл
            chunk_size: Размер чанка для чтения/записи (64 МБ по умолчанию)
        """
        total = src.stat().st_size
        copied = 0

        with open(src, 'rb') as f_src, open(dst, 'wb') as f_dst:
            while True:
                chunk = f_src.read(chunk_size)
                if not chunk:
                    break
                f_dst.write(chunk)
                copied += len(chunk)

                # Отправляем прогресс каждые 10%
                progress = int((copied / total) * 100)
                if progress % 10 == 0:
                    self._send_message(AppMessage.debug(
                        f"Копирование {src.name}: {progress}%"
                    ))

    # ==================== РАБОТА С JPS ЗАГОЛОВКАМИ ====================

    def fix_jps_headers(self, jps_files: Dict[FileType, Path]) -> Tuple[bool, str, int]:
        """
        Проверяет и при необходимости добавляет заголовок JP055 в указанные JPS файлы.

        Проблема: Некоторые JPS файлы могут не иметь заголовка,
        что приводит к ошибкам при обработке.

        Решение:
            1. Проверяем первые 5 байт файла на соответствие "JP055"
            2. Если заголовка нет - добавляем его в начало

        Args:
            jps_files: Словарь {тип_файла: путь_к_файлу} для файлов, которые нужно проверить.

        Returns:
            (успех, сообщение, количество исправленных файлов)
        """
        fixed_count = 0
        file_descriptions = {
            FileType.ROVER: "ровера",
            FileType.BASE1: "базы 1",
            FileType.BASE2: "базы 2",
        }

        for file_type, description in file_descriptions.items():
            path = jps_files.get(file_type)
            if not path:
                continue

            # Проверяем заголовок
            if self._has_valid_header(path):
                self._send_message(AppMessage.debug(f"✓ {path.name}: заголовок JP055 OK"))
                continue

            # Добавляем заголовок
            if self._add_header(path):
                fixed_count += 1
                self._send_message(AppMessage.info(f"🔧 {path.name}: добавлен заголовок JP055"))
            else:
                return False, f"Не удалось исправить заголовок {path.name}", fixed_count

        return True, "JPS файлы в порядке", fixed_count

    def _has_valid_header(self, path: Path) -> bool:
        """
        Проверяет наличие корректного заголовка JP055 в файле.

        Args:
            path: Путь к JPS файлу

        Returns:
            True если первые 5 байт содержат "JP055" (в cp1251 или utf-8)
        """
        try:
            with open(path, 'rb') as f:
                header = f.read(5)

            # Проверяем в разных кодировках
            try:
                return header.decode('cp1251') == self.JPS_HEADER
            except UnicodeDecodeError:
                try:
                    return header.decode('utf-8') == self.JPS_HEADER
                except UnicodeDecodeError:
                    return False
        except Exception:
            return False

    def _add_header(self, path: Path) -> bool:
        """
        Добавляет заголовок JP055 в начало файла атомарно.

        Алгоритм с защитой от сбоев:
            1. Создаём резервную копию (.bak)
            2. Создаём временный файл с заголовком + содержимым
            3. Проверяем размер нового файла
            4. Атомарно заменяем оригинал
            5. Удаляем бэкап при успехе, восстанавливаем при ошибке

        Args:
            path: Путь к JPS файлу

        Returns:
            True при успешном добавлении заголовка
        """
        temp_path = path.with_suffix('.tmp')
        backup_path = path.with_suffix('.bak')

        try:
            # 1. Создаём резервную копию
            shutil.copy2(path, backup_path)

            # 2. Создаём новый файл с заголовком
            with open(path, 'rb') as src, open(temp_path, 'wb') as dst:
                dst.write(self.JPS_HEADER_BYTES)
                shutil.copyfileobj(src, dst)

            # 3. Проверяем размер
            original_size = backup_path.stat().st_size
            new_size = temp_path.stat().st_size

            if new_size == original_size + len(self.JPS_HEADER_BYTES):
                # 4. Атомарно заменяем оригинал
                os.replace(temp_path, path)
                backup_path.unlink(missing_ok=True)
                return True
            else:
                # Восстанавливаем из бэкапа
                os.replace(backup_path, path)
                if temp_path.exists():
                    temp_path.unlink()
                return False

        except Exception as e:
            self._send_message(AppMessage.error(f"Ошибка добавления заголовка: {e}"))
            # Пытаемся восстановить
            if backup_path.exists():
                os.replace(backup_path, path)
            return False
        finally:
            # Очищаем временные файлы, если они остались
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

    # ==================== УПРАВЛЕНИЕ КОНФИГУРАЦИОННЫМИ ФАЙЛАМИ ====================

    def reset_manual_mode(self) -> None:
        """
        Сбрасывает флаг ручного режима, позволяя автоматическому интервалу
        обновлять значения при следующем запуске Interval.exe.
        """
        if self._time_interval.manual:
            self._send_message(AppMessage.debug(
                "🔄 Сброс ручного режима интервала",
                source="FileManager"
            ))
            self._time_interval.manual = False

    def update_time_interval(self, start: str, end: str, manual: bool = False) -> None:
        """
        Обновляет временной интервал и синхронизирует с SR2Nav.cfg.

        Особенности:
            - При ручном режиме (manual=True) интервал не перезаписывается автоматически
            - Если интервал уже ручной, автоматические обновления игнорируются с предупреждением

        Args:
            start: Начало интервала "HH:MM:SS"
            end: Конец интервала "HH:MM:SS"
            manual: True если установлено пользователем, False из Interval.exe
        """
        if manual:
            self._time_interval.set_manual(start, end)
            self._send_message(AppMessage.info(
                f"📝 Установлен интервал вручную: {start} - {end}",
                source="FileManager"
            ))
        else:
            # Если интервал уже ручной - предупреждаем, но не перезаписываем
            if self._time_interval.manual:
                self._send_message(AppMessage.warning(
                    f"⚠️ Интервал установлен вручную ({self._time_interval.start} - {self._time_interval.end})\n"
                    f"   Результат Interval.exe ({start} - {end}) игнорируется.\n"
                    f"   Для использования авто-интервала снимите ручной режим.",
                    source="FileManager"
                ))
                return

            self._time_interval.set_auto(start, end)

        # Обновляем конфиг
        self._update_config_interval()

    def _update_config_interval(self) -> None:
        """
        Обновляет строку интервала в SR2Nav.cfg (4-я строка).

        Формат строки: "*HH:MM:SS HH:MM:SS" или "*1111111" если интервал не задан.
        """
        cfg_path = self._ctx.sr2nav_cfg

        if not cfg_path.exists():
            return

        try:
            lines = cfg_path.read_text(encoding='cp1251', errors='ignore').splitlines()

            # Убеждаемся, что файл содержит минимум 4 строки
            while len(lines) < 4:
                lines.append("")

            # Формируем строку интервала
            if self._time_interval.start and self._time_interval.end:
                interval_line = f"*{self._time_interval.start} {self._time_interval.end}"
            else:
                interval_line = "*1111111"

            lines[3] = interval_line

            # Сохраняем в CP1251 для совместимости
            cfg_path.write_text("\n".join(lines) + "\n", encoding='cp1251')

            self._send_message(AppMessage.debug(
                f"📝 Конфиг обновлён: интервал {self._time_interval.start} - {self._time_interval.end}",
                source="FileManager"
            ))

        except Exception as e:
            self._send_message(AppMessage.error(
                f"Ошибка обновления SR2Nav.cfg: {e}",
                source="FileManager"
            ))

    def create_config_files(self, working_paths: Dict[FileType, Path]) -> Tuple[bool, str]:
        """
        Создаёт конфигурационные файлы для Interval.exe и SR2Nav в рабочей директории.

        Создаваемые файлы:
            - Mask.Ang: содержит угол отсечения
            - SR2Nav.cfg: содержит все параметры запуска (файлы, интервал)

        Args:
            working_paths: Словарь путей к файлам в рабочей директории, которые будут
                           использованы для создания конфига. Должен содержать ключи
                           AIR, ROVER, BASE1, BASE2 (если они были скопированы).

        Returns:
            (успех, сообщение_об_ошибке_или_успехе)
        """
        # 1. Mask.Ang
        mask_path = self._ctx.mask_ang
        try:
            mask_path.write_text(f"{self._cutoff_angle:.1f}\n")
            self._send_message(AppMessage.info(f"📝 Создан Mask.Ang: {self._cutoff_angle}°"))
        except Exception as e:
            return False, f"Ошибка создания Mask.Ang: {e}"

        # 2. SR2Nav.cfg
        cfg_path = self._ctx.sr2nav_cfg
        try:
            content = self._generate_cfg_content(working_paths)
            cfg_path.write_text(content, encoding='cp1251')
            self._send_message(AppMessage.info(f"📝 Создан SR2Nav.cfg"))
        except Exception as e:
            return False, f"Ошибка создания SR2Nav.cfg: {e}"

        return True, "Конфигурационные файлы созданы"

    def _generate_cfg_content(self, working_paths: Dict[FileType, Path]) -> str:
        """
        Генерирует содержимое SR2Nav.cfg на основе путей к файлам в рабочей директории.

        Формат файла (7 строк):
            1: AIR файл
            2: *18 (фиксировано)
            3: * (пустая)
            4: Временной интервал
            5: Файл ровера
            6: Файл базы 1
            7: Файл базы 2

        Args:
            working_paths: Словарь путей к файлам в рабочей директории.

        Returns:
            Строка с содержимым конфига в кодировке CP1251
        """
        lines = []

        # Строка 1: AIR файл
        air_path = working_paths.get(FileType.AIR)
        lines.append(f"*{air_path.name if air_path else ''}")

        # Строка 2: *18
        lines.append("*18")

        # Строка 3: *
        lines.append("*")

        # Строка 4: временной интервал
        if self._time_interval.start and self._time_interval.end:
            lines.append(f"*{self._time_interval.start} {self._time_interval.end}")
        else:
            lines.append("*1111111")

        # Строки 5-7: файлы ровера и баз
        rover_path = working_paths.get(FileType.ROVER)
        base1_path = working_paths.get(FileType.BASE1)
        base2_path = working_paths.get(FileType.BASE2)

        lines.append(f"*{rover_path.name if rover_path else ''}")
        lines.append(f"*{base1_path.name if base1_path else ''}")
        lines.append(f"*{base2_path.name if base2_path else ''}")

        return "\n".join(lines) + "\n"

    # ==================== ИНТЕГРАЦИЯ С INTERVAL.EXE ====================

    async def run_interval(self) -> Tuple[bool, str, Optional[Dict[FileType, Path]]]:
        """
        Подготавливает файлы для запуска Interval.exe.

        Шаги:
            1. Подготовка необходимых файлов (ROVER, BASE1, BASE2, AIR) в рабочей директории.
            2. Исправление JPS заголовков у подготовленных JPS файлов.
            3. Создание конфигурационных файлов.

        Returns:
            (успех, сообщение, словарь подготовленных_путей_для_Interval)
        """
        # 1. Подготовка файлов, необходимых для Interval
        files_needed = [FileType.ROVER, FileType.BASE1, FileType.BASE2, FileType.AIR]
        success, msg, prepared_paths = self.prepare_files(files_needed)
        if not success:
            return False, msg, None

        # 2. Исправление JPS заголовков в подготовленных JPS файлах
        jps_files = {ft: p for ft, p in prepared_paths.items() if ft in (FileType.ROVER, FileType.BASE1, FileType.BASE2)}
        jps_success, jps_msg, fixed_count = self.fix_jps_headers(jps_files)
        if not jps_success:
            return False, jps_msg, prepared_paths

        # 3. Создание конфигов на основе подготовленных файлов
        cfg_success, cfg_msg = self.create_config_files(prepared_paths)
        if not cfg_success:
            return False, cfg_msg, prepared_paths

        return True, "Готов к запуску Interval.exe", prepared_paths

    async def parse_interval_result(self) -> Tuple[bool, str]:
        """
        Парсит результат работы Interval.exe из interval.txt.

        Алгоритм:
            1. Читает interval.txt
            2. Ищет строку с '[Common]' и извлекает временные метки
            3. Обновляет интервал (если не в ручном режиме)

        Returns:
            (успех, сообщение_с_интервалом_или_ошибкой)
        """
        interval_file = self._ctx.interval_txt

        if not interval_file.exists():
            return False, "interval.txt не найден"

        try:
            content = interval_file.read_text(encoding='utf-8')

            for line in content.splitlines():
                if '[Common]' in line:
                    parts = line.split('-> [Common]')[0].strip().split()
                    if len(parts) >= 2:
                        start, end = parts[0], parts[1]

                        # Если интервал уже установлен вручную - предупреждаем
                        if self._time_interval.manual:
                            # Возвращаем успех, но с предупреждением
                            return True, (
                                f"⚠️ Интервал сохранён вручную: {self._time_interval.start} - {self._time_interval.end}\n"
                                f"   Результат Interval.exe игнорируется. Снимите ручной режим для авто-интервала."
                            )

                        # Иначе - обновляем из Interval.exe с manual=False
                        self.update_time_interval(start, end, manual=False)
                        return True, f"Интервал из Interval.exe: {start} - {end}"

            return False, "Временные метки не найдены"

        except Exception as e:
            return False, f"Ошибка парсинга: {e}"

    # ==================== ИНТЕГРАЦИЯ С SR2NAV ====================

    async def run_sr2nav(self) -> Tuple[bool, str, Optional[Dict[FileType, Path]]]:
        """
        Подготавливает файлы для запуска SR2Nav.exe.

        Особенности:
            - Подготавливает SR2Nav.exe, Rover, Base1, Base2, Air.
            - Исправляет JPS заголовки, если необходимо.

        Returns:
            (успех, сообщение, словарь подготовленных_путей_для_SR2Nav)
        """
        # Подготавливаем все необходимые файлы для SR2Nav
        files_needed = [FileType.SR2NAV_EXE, FileType.ROVER, FileType.BASE1, FileType.BASE2, FileType.AIR]
        success, msg, prepared_paths = self.prepare_files(files_needed)
        if not success:
            return False, msg, None

        # JPS файлы уже должны быть скопированы и, возможно, исправлены на предыдущем шаге.
        # Если мы запускаем SR2Nav отдельно, без Interval, то нужно проверить их здесь.
        jps_files = {ft: p for ft, p in prepared_paths.items() if ft in (FileType.ROVER, FileType.BASE1, FileType.BASE2)}
        jps_success, jps_msg, fixed_count = self.fix_jps_headers(jps_files)
        if not jps_success:
            return False, jps_msg, prepared_paths

        # <-- ИЗМЕНЕНО: Конфиги для SR2Nav создаются на основе подготовленных путей
        cfg_success, cfg_msg = self.create_config_files(prepared_paths)
        if not cfg_success:
            return False, cfg_msg, prepared_paths

        return True, "Готов к запуску SR2Nav.exe", prepared_paths

    # ==================== УПРАВЛЕНИЕ РЕЗУЛЬТАТАМИ ====================

    def move_results_to_results_dir(self) -> int:
        """
        Перемещает результаты работы SR2Nav в именованную папку результатов.

        Ищет файлы по паттернам RESULT_FILE_PATTERNS в рабочей директории
        и перемещает их в self._ctx.results_dir.

        Returns:
            Количество перемещённых файлов
        """
        patterns = self.RESULT_FILE_PATTERNS
        results_dir = self._ctx.results_dir

        # Создаём папку, если её нет
        results_dir.mkdir(parents=True, exist_ok=True)

        moved = 0

        for pattern in patterns:
            for file_path in self._ctx.working_dir.glob(pattern):
                if file_path.is_file():
                    dest = results_dir / file_path.name
                    try:
                        # Если файл уже существует - перезаписываем
                        if dest.exists():
                            dest.unlink()
                        shutil.move(str(file_path), str(dest))
                        moved += 1
                        self._send_message(AppMessage.debug(
                            f"📦 {file_path.name} → {results_dir.name}/",
                            source="FileManager"
                        ))
                    except Exception as e:
                        self._send_message(AppMessage.warning(
                            f"Не удалось переместить {file_path.name}: {e}",
                            source="FileManager"
                        ))

        return moved

    # ==================== ОПЕРАЦИИ С JPS ФАЙЛАМИ ====================

    def stitch_jps_files(self, input_files: List[str], output_path: str) -> Tuple[bool, str]:
        """
        Сшивает несколько JPS файлов в один.

        Алгоритм:
            1. Проверяет расширения файлов
            2. Конкатенирует содержимое всех файлов
            3. Проверяет наличие заголовка JP055 в результате
            4. Добавляет заголовок, если его нет

        Args:
            input_files: Список путей к исходным JPS файлам
            output_path: Путь для сохранения результата

        Returns:
            (успех, сообщение)
        """
        try:
            # Валидация расширений (но не существования - это делает контроллер)
            paths = [Path(f) for f in input_files]
            output = Path(output_path)

            for p in paths:
                if p.suffix.lower() != '.jps':
                    return False, f"Файл должен быть .jps: {p.name}"

            if output.suffix.lower() != '.jps':
                return False, "Выходной файл должен иметь расширение .jps"

            # Создаём директорию
            output.parent.mkdir(exist_ok=True)

            # Конкатенация
            total_size = sum(p.stat().st_size for p in paths)
            self._send_message(AppMessage.info(
                f"🔗 Сшивание {len(paths)} файлов ({total_size / 1024 / 1024:.1f} МБ)"
            ))

            with open(output, 'wb') as dst:
                for src in paths:
                    with open(src, 'rb') as f:
                        shutil.copyfileobj(f, dst)

            # Проверяем заголовок и добавляем ТОЛЬКО ЕСЛИ ЕГО НЕТ
            if not self._has_valid_header(output):
                self._send_message(AppMessage.info(f"  Добавлен заголовок JP055"))
                if not self._add_header(output):
                    return False, "Не удалось добавить заголовок JP055"
            else:
                self._send_message(AppMessage.debug(f"  Заголовок JP055 уже присутствует"))

            return True, f"Файл сохранён: {output.name}"

        except Exception as e:
            return False, f"Ошибка сшивания: {e}"

    # ==================== ОЧИСТКА И СИНХРОНИЗАЦИЯ ====================

    def cleanup_working_directory(self, exclude_patterns: List[str] = None) -> Tuple[int, List[str]]:
        """
        Очищает рабочую директорию от временных файлов.

        Удаляет все файлы, не соответствующие паттернам исключения.
        После удаления синхронизирует внутренний словарь _working_paths,
        удаляя ссылки на несуществующие файлы.

        Args:
            exclude_patterns: Список паттернов файлов для исключения
                             (по умолчанию: .exe, .py, .pyw)

        Returns:
            (количество удалённых файлов, список ошибок)
        """
        if exclude_patterns is None:
            exclude_patterns = ['*.exe', '*.py', '*.pyw']

        deleted_count = 0
        errors = []

        self._send_message(AppMessage.info(
            "🧹 Очистка рабочей директории...",
            source="FileManager"
        ))

        try:
            for item in self._ctx.working_dir.iterdir():
                # Пропускаем папки
                if item.is_dir():
                    continue

                # Проверяем, попадает ли файл под исключение
                should_exclude = False
                for pattern in exclude_patterns:
                    if item.match(pattern):
                        should_exclude = True
                        break

                if should_exclude:
                    self._send_message(AppMessage.debug(
                        f"  Сохранён: {item.name} (исключён по паттерну)",
                        source="FileManager"
                    ))
                    continue

                # Удаляем файл
                try:
                    item.unlink()
                    deleted_count += 1
                    self._send_message(AppMessage.debug(
                        f"  Удалён: {item.name}",
                        source="FileManager"
                    ))
                except Exception as e:
                    error_msg = f"Не удалось удалить {item.name}: {e}"
                    errors.append(error_msg)
                    self._send_message(AppMessage.warning(
                        error_msg,
                        source="FileManager"
                    ))

            # Синхронизируем _working_paths - удаляем ссылки на несуществующие файлы
            removed_from_working = 0
            for file_type, path in list(self._working_paths.items()):
                if not path.exists():
                    self._working_paths.pop(file_type, None)
                    removed_from_working += 1
                    self._send_message(AppMessage.debug(
                        f"  🧹 Удалена ссылка на несуществующий файл: {path.name}",
                        source="FileManager"
                    ))

            if removed_from_working > 0:
                self._send_message(AppMessage.info(
                    f"  Синхронизировано состояние: удалено {removed_from_working} несуществующих файлов из списка",
                    source="FileManager"
                ))

            if deleted_count > 0:
                self._send_message(AppMessage.info(
                    f"✅ Очистка завершена. Удалено файлов: {deleted_count}",
                    source="FileManager"
                ))
            else:
                self._send_message(AppMessage.info(
                    "✨ В рабочей директории нет файлов для удаления",
                    source="FileManager"
                ))

        except Exception as e:
            error_msg = f"Ошибка при очистке рабочей директории: {e}"
            errors.append(error_msg)
            self._send_message(AppMessage.error(
                error_msg,
                source="FileManager"
            ))

        return deleted_count, errors

    # ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================

    def _send_message(self, message: AppMessage) -> None:
        """Отправляет сообщение через callback в систему логирования."""
        if self._message_callback:
            self._message_callback(message)