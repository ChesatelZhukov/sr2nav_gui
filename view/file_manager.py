#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЧИСТАЯ МОДЕЛЬ - Менеджер файлов.
ТОЛЬКО ОПЕРАЦИИ С ФАЙЛАМИ, НИКАКИХ ПРОВЕРОК СУЩЕСТВОВАНИЯ!
Контроллер гарантирует, что файлы существуют.
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
    """Типы файлов, используемые в приложении."""
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
        """Ожидаемое расширение файла."""
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
        """Человекочитаемое описание."""
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
        """Обязателен ли файл для работы."""
        return self in (FileType.ROVER, FileType.SR2NAV_EXE)


@dataclass
class TimeInterval:
    """Временной интервал для обработки."""
    start: str = ""
    end: str = ""
    manual: bool = False  # True = установлен пользователем, False = из Interval.exe
    
    @property
    def is_valid(self) -> bool:
        """Проверяет, задан ли интервал."""
        return bool(self.start and self.end)
    
    def set_manual(self, start: str, end: str) -> None:
        """Устанавливает интервал вручную."""
        self.start = start
        self.end = end
        self.manual = True
    
    def set_auto(self, start: str, end: str) -> None:
        """Устанавливает интервал из Interval.exe."""
        self.start = start
        self.end = end
        self.manual = False


class FileManager:
    """
    ЧИСТАЯ МОДЕЛЬ - Менеджер файлов.
    ТОЛЬКО ОПЕРАЦИИ, НИКАКИХ ПРОВЕРОК!
    Контроллер гарантирует, что файлы существуют.
    """

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
        Args:
            context: Контекст приложения
            message_callback: Функция для отправки сообщений
        """
        self._ctx = context
        self._message_callback = message_callback
        
        # Словарь путей к файлам (оригинальные пути от пользователя)
        self._original_paths: Dict[FileType, Path] = {}
        
        # Словарь путей в рабочей директории (после копирования)
        self._working_paths: Dict[FileType, Path] = {}
        
        # Параметры
        self._cutoff_angle: float = 7.0
        self._time_interval = TimeInterval()
    
    # ==================== ПУБЛИЧНЫЙ API ====================
    
    def set_path(self, file_type: FileType, path: str | Path) -> None:
        """Устанавливает путь к файлу."""
        if not path:
            self._original_paths.pop(file_type, None)
            self._working_paths.pop(file_type, None)
            return
        
        path_obj = Path(path)
        self._original_paths[file_type] = path_obj
        
        # Если файл уже в рабочей директории - сразу обновляем working_paths
        if path_obj.parent == self._ctx.working_dir:
            self._working_paths[file_type] = path_obj
    
    # ============ НОВЫЙ СПЕЦИАЛИЗИРОВАННЫЙ МЕТОД ДЛЯ РОВЕРА ============
    
    def set_rover_path(self, path: str | Path) -> None:
        """
        Устанавливает путь к роверу и обновляет папку результатов.
        """
        if not path:
            self._original_paths.pop(FileType.ROVER, None)
            self._working_paths.pop(FileType.ROVER, None)
            return
        
        path_obj = Path(path)
        self._original_paths[FileType.ROVER] = path_obj
        
        if path_obj.parent == self._ctx.working_dir:
            self._working_paths[FileType.ROVER] = path_obj
        
        # ДОБАВЛЯЕМ ПРОВЕРКУ - path точно не None здесь
        if str(path).strip():  # <-- дополнительная проверка
            new_dir = self._ctx.set_results_dir_from_rover(str(path))
            self._send_message(AppMessage.info(
                f"📁 Папка результатов: {new_dir.name}",
                source="FileManager"
            ))
    
    def get_path(self, file_type: FileType) -> Optional[Path]:
        """Возвращает путь к файлу в рабочей директории (если есть)."""
        return self._working_paths.get(file_type)
    
    def get_original_path(self, file_type: FileType) -> Optional[Path]:
        """Возвращает оригинальный путь к файлу (от пользователя)."""
        return self._original_paths.get(file_type)
    
    def get_all_paths(self) -> Dict[str, str]:
        """
        Возвращает словарь {ключ_файла: путь} для синхронизации с UI.
        Ключи соответствуют FileType.value.
        """
        result = {}
        for file_type, path in self._working_paths.items():
            result[file_type.value] = str(path)
        return result
    
    def get_working_paths_with_originals(self) -> Dict[str, Tuple[str, str]]:
        """
        Возвращает словарь {ключ_файла: (рабочий_путь, оригинальный_путь)}
        для отображения в UI реального местоположения файла.
        """
        result = {}
        for file_type in FileType:
            working = self._working_paths.get(file_type)
            original = self._original_paths.get(file_type)
            if working or original:
                result[file_type.value] = (
                    str(working) if working else "",
                    str(original) if original else ""
                )
        return result
    
    # ==================== ПАРАМЕТРЫ ====================
    
    @property
    def cutoff_angle(self) -> float:
        """Угол отсечения в градусах."""
        return self._cutoff_angle
    
    def set_cutoff_angle(self, angle: float) -> None:
        """Устанавливает угол отсечения."""
        self._cutoff_angle = round(angle, 1)
    
    @property
    def time_interval(self) -> TimeInterval:
        """Временной интервал."""
        return self._time_interval
    
    # ==================== ПОДГОТОВКА ФАЙЛОВ ====================
    
    def cleanup_results_dir(self, force: bool = False) -> Tuple[int, bool]:
        """
        ОЧИЩАЕТ ПАПКУ РЕЗУЛЬТАТОВ перед запуском.
        
        Args:
            force: Если False, проверяет наличие файлов и отправляет предупреждение
            
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
        
        # Собираем список существующих файлов
        for pattern in patterns:
            existing_files.extend(list(results_dir.glob(pattern)))
        
        # Если есть файлы и не форсируем - запрашиваем подтверждение
        if existing_files and not force:
            self._send_message(AppMessage.warning(
                f"⚠️ В папке {results_dir.name} найдены файлы ({len(existing_files)} шт.)\n"
                f"Очистка удалит их перед запуском.",
                source="FileManager"
            ))
            return 0, True
        
        # Удаляем файлы
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

    def prepare_files(self) -> Tuple[bool, str, int]:
        """
        Копирует все файлы в рабочую директорию и проверяет JPS заголовки.
        Возвращает (успех, сообщение, количество исправленных файлов)
        """
        self._send_message(AppMessage.info("📋 Подготовка файлов..."))
        
        # 1. Копирование файлов
        copy_success, copy_msg, copied_count = self._copy_all_files()
        if not copy_success:
            return False, copy_msg, 0
        
        # 2. Проверка JPS файлов
        jps_success, jps_msg, fixed_count = self._fix_jps_headers()
        if not jps_success:
            return False, jps_msg, fixed_count
        
        return True, "Файлы готовы", fixed_count
    
    def _copy_all_files(self) -> Tuple[bool, str, int]:
        """
        Копирует все файлы из оригинальных путей в рабочую директорию.
        Возвращает (успех, сообщение, количество скопированных файлов)
        """
        copied_count = 0
        
        for file_type, src_path in self._original_paths.items():
            # Если файл уже в рабочей директории - пропускаем
            if src_path.parent == self._ctx.working_dir:
                self._working_paths[file_type] = src_path
                continue
            
            dst_path = self._ctx.working_dir / src_path.name
            
            try:
                # Для больших JPS файлов - копирование с прогрессом
                if file_type in (FileType.ROVER, FileType.BASE1, FileType.BASE2):
                    self._copy_large_file(src_path, dst_path)
                else:
                    shutil.copy2(src_path, dst_path)
                
                self._working_paths[file_type] = dst_path
                copied_count += 1
                
                # ИНФОРМИРУЕМ, ЧТО ФАЙЛ БЫЛ СКОПИРОВАН
                self._send_message(AppMessage.info(
                    f"✓ {src_path.name} → рабочая директория\n"
                    f"  (оригинал: {src_path.parent})"
                ))
                
            except Exception as e:
                return False, f"Ошибка копирования {src_path.name}: {e}", copied_count
        
        return True, "Копирование завершено", copied_count
    
    def _copy_large_file(self, src: Path, dst: Path, chunk_size: int = 64 * 1024 * 1024) -> None:
        """Копирует большой файл с выводом прогресса."""
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
    
    # ==================== JPS ЗАГОЛОВКИ ====================
    
    def _fix_jps_headers(self) -> Tuple[bool, str, int]:
        """
        Проверяет и исправляет заголовки JPS файлов.
        Возвращает (успех, сообщение, количество исправленных)
        """
        jps_files = [
            (FileType.ROVER, "ровера"),
            (FileType.BASE1, "базы 1"),
            (FileType.BASE2, "базы 2"),
        ]
        
        fixed_count = 0
        
        for file_type, description in jps_files:
            if file_type not in self._working_paths:
                continue
            
            path = self._working_paths[file_type]
            
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
        """Проверяет наличие корректного заголовка JP055."""
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
        """Добавляет заголовок JP055 в начало файла."""
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
    
    # ==================== СОЗДАНИЕ КОНФИГОВ ====================
    
    def update_time_interval(self, start: str, end: str, manual: bool = False) -> None:
        """Обновляет временной интервал."""
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
        """Обновляет SR2Nav.cfg с текущим временным интервалом."""
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

    def create_config_files(self) -> Tuple[bool, str]:
        """Создаёт конфигурационные файлы для Interval.exe и SR2Nav."""
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
            content = self._generate_cfg_content()
            cfg_path.write_text(content, encoding='cp1251')
            self._send_message(AppMessage.info(f"📝 Создан SR2Nav.cfg"))
        except Exception as e:
            return False, f"Ошибка создания SR2Nav.cfg: {e}"
        
        return True, "Конфигурационные файлы созданы"
    
    def _generate_cfg_content(self) -> str:
        """Генерирует содержимое SR2Nav.cfg."""
        lines = []
        
        # Строка 1: AIR файл
        air_path = self._working_paths.get(FileType.AIR)
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
        rover_path = self._working_paths.get(FileType.ROVER)
        base1_path = self._working_paths.get(FileType.BASE1)
        base2_path = self._working_paths.get(FileType.BASE2)
        
        lines.append(f"*{rover_path.name if rover_path else ''}")
        lines.append(f"*{base1_path.name if base1_path else ''}")
        lines.append(f"*{base2_path.name if base2_path else ''}")
        
        return "\n".join(lines) + "\n"
    
    # ==================== INTERVAL.EXE ====================
    
    async def run_interval(self) -> Tuple[bool, str]:
        """Подготавливает и запускает Interval.exe."""
        # Подготовка файлов
        success, msg, _ = self.prepare_files()
        if not success:
            return False, msg
        
        # Создание конфигов
        success, msg = self.create_config_files()
        if not success:
            return False, msg
        
        return True, "Готов к запуску Interval.exe"
    
    async def parse_interval_result(self) -> Tuple[bool, str]:
        """Парсит результат работы Interval.exe."""
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
                            return True, (
                                f"⚠️ Интервал сохранён вручную: {self._time_interval.start} - {self._time_interval.end}\n"
                                f"   Результат Interval.exe игнорируется. Снимите ручной режим для авто-интервала."
                            )
                        
                        # Иначе - обновляем из Interval.exe
                        self.update_time_interval(start, end, manual=False)
                        return True, f"Интервал из Interval.exe: {start} - {end}"
            
            return False, "Временные метки не найдены"
            
        except Exception as e:
            return False, f"Ошибка парсинга: {e}"
    
    # ==================== SR2NAV ====================
    
    async def run_sr2nav(self) -> Tuple[bool, str]:
        """Подготавливает и запускает SR2Nav.exe."""
        # Копируем SR2Nav.exe в рабочую директорию, если его там нет
        sr2nav_path = self._working_paths.get(FileType.SR2NAV_EXE)
        if not sr2nav_path:
            original = self._original_paths.get(FileType.SR2NAV_EXE)
            if original:
                dst = self._ctx.working_dir / original.name
                shutil.copy2(original, dst)
                self._working_paths[FileType.SR2NAV_EXE] = dst
        
        return True, "Готов к запуску SR2Nav.exe"
    
    # ==================== ПЕРЕМЕЩЕНИЕ РЕЗУЛЬТАТОВ ====================
    
    def move_results_to_results_dir(self) -> int:
        """Перемещает результаты работы SR2Nav в папку результатов."""
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
    
    # ==================== СШИВАНИЕ JPS ====================
    
    def stitch_jps_files(self, input_files: List[str], output_path: str) -> Tuple[bool, str]:
        """Сшивает несколько JPS файлов в один."""
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
            
            # ИСПРАВЛЕНО: Проверяем заголовок и добавляем ТОЛЬКО ЕСЛИ ЕГО НЕТ
            if not self._has_valid_header(output):
                self._send_message(AppMessage.info(f"  Добавлен заголовок JP055"))
                if not self._add_header(output):
                    return False, "Не удалось добавить заголовок JP055"
            else:
                self._send_message(AppMessage.debug(f"  Заголовок JP055 уже присутствует"))
            
            return True, f"Файл сохранён: {output.name}"
            
        except Exception as e:
            return False, f"Ошибка сшивания: {e}"
    
    # ==================== ВСПОМОГАТЕЛЬНЫЕ ====================
    
    def _send_message(self, message: AppMessage) -> None:
        """Отправляет сообщение через callback."""
        if self._message_callback:
            self._message_callback(message)