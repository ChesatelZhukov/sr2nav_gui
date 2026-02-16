# model/process_runner.py - ПОЛНОСТЬЮ ИСПРАВЛЕННЫЙ ФАЙЛ

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Асинхронный менеджер внешних процессов.
Запуск, мониторинг и безопасное завершение программ.
"""

import asyncio
import re
import signal
from typing import Optional, List, Callable, Dict, Set, Tuple
from enum import Enum, auto
from dataclasses import dataclass, field
from datetime import datetime

from core.message_system import AppMessage, MessageLevel


class ProcessType(Enum):
    """Типы поддерживаемых внешних процессов."""
    INTERVAL = auto()
    SR2NAV = auto()
    
    @property
    def display_name(self) -> str:
        """Человекочитаемое имя процесса."""
        return {
            ProcessType.INTERVAL: "Interval.exe",
            ProcessType.SR2NAV: "SR2Nav.exe",
        }[self]


@dataclass
class ProcessStatus:
    """Текущее состояние процесса."""
    pid: Optional[int] = None
    process_type: Optional[ProcessType] = None
    is_running: bool = False
    exit_code: Optional[int] = None
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def duration(self) -> Optional[float]:
        """Длительность выполнения в секундах."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None


class ProcessRunner:
    """
    Управление внешними процессами с асинхронным вводом-выводом.
    
    Особенности:
        - Фильтрация потока вывода (только значимые строки)
        - Декодирование в разных кодировках
        - Безопасное завершение (terminate → kill)
    """
    
    # ============ ИСПРАВЛЕНИЕ: АКТИВНОЕ ИСПОЛЬЗОВАНИЕ СЛОВАРЯ ФИЛЬТРОВ ============
    # Определяем правила фильтрации для каждого типа процесса
    SR2NAV_FILTER_RULES: Dict[str, Set[str]] = {
        # Категория: набор подстрок, которые разрешены
        "header": {
            "Moscow State Lomonosov",
            "Control and Navigation",
            "SR2Nav Ver.",
            "E-mail:",
            "www.navlab.ru",
        },
        "diagnostics": {
            "Not Valid Control Sum in Message [JP]",
            "Message Length Hex [055] = 85",
        },
        "time": {
            "Time span:",
        },
        "conversion": {
            "Conversion JPS to Ashtech Format",
            "Rover (E-File):",
            "Rover (B-File):",
            "Base #1 (B-File):",
            ".JPS",
        },
        "checking": {
            "GPS Raw Data Files Checking",
        },
        "modes": {
            "Standard Mode: Station Name -> [Rover]",
            "Standard Phase Velocity Mode: Station Name -> [Rover]",
            "Standard Phase Coordinate Mode: Station Name -> [Rover]",
            "Standard Mode: Station Name -> [Base]",
            "Code & Doppler Differential Mode:",
            "Carrier Phase Differential Mode:",
            "Phase Coordinates Differential Mode:",
        },
    }
    
    # Объединяем все разрешенные подстроки для SR2Nav
    SR2NAV_ALLOWED_SUBSTRINGS: Set[str] = set()
    for category_rules in SR2NAV_FILTER_RULES.values():
        SR2NAV_ALLOWED_SUBSTRINGS.update(category_rules)
    
    # Строгие запреты для SR2Nav (даже если есть разрешенная подстрока)
    SR2NAV_STRICT_BLOCKED: Set[str] = {
        "SV =",
        "Toe =",
        "178925",
        "208800",
        "PRN",
    }
    
    # Правила фильтрации для Interval.exe
    INTERVAL_BLOCK_PATTERNS: List[str] = [
        r'^\*.*\*$',      # Строки с рамкой
        r'^I:',           # Данные с I:
        r'^[\d\s\.]+$',  # Только цифры, пробелы, точки
    ]
    
    # Общие правила фильтрации для всех процессов
    GENERAL_BLOCK_RULES = {
        "binary_data": lambda line: len(line) > 200 and any(c.isdigit() for c in line[:10]),
        "starts_with_digit": lambda line: bool(line) and line[0].isdigit() and not line.startswith("Time span:"),
        "contains_sv": lambda line: "SV =" in line,
        "contains_toe": lambda line: "Toe =" in line,
    }
    
    def __init__(
        self,
        message_callback: Callable[[AppMessage], None],
    ):
        """
        Args:
            message_callback: Функция для отправки сообщений (принимает AppMessage)
        """
        self._message_callback = message_callback
        self._process: Optional[asyncio.subprocess.Process] = None
        self._process_type: Optional[ProcessType] = None
        self._status = ProcessStatus()
        self._read_tasks: List[asyncio.Task] = []
        self._message_accumulator = {}  # Для накопления многострочных сообщений
    
    # ==================== СВОЙСТВА ====================
    
    @property
    def is_running(self) -> bool:
        """Активен ли процесс в данный момент."""
        return self._process is not None and self._process.returncode is None
    
    @property
    def status(self) -> ProcessStatus:
        """Текущее состояние процесса (копия)."""
        status = ProcessStatus(
            pid=self._status.pid,
            process_type=self._process_type,
            is_running=self.is_running,
            exit_code=self._status.exit_code,
            error=self._status.error,
            start_time=self._status.start_time,
            end_time=self._status.end_time,
        )
        return status
    
    # ==================== ЗАПУСК ====================
    
    async def run(
        self,
        command: List[str],
        working_dir: str,
        process_type: ProcessType,
        timeout: Optional[float] = None,
    ) -> int:
        """
        Запускает внешний процесс и ожидает его завершения.
        
        Args:
            command: Команда и аргументы
            working_dir: Рабочая директория
            process_type: Тип процесса
            timeout: Максимальное время выполнения (None — бесконечно)
            
        Returns:
            Код возврата процесса, -1 при ошибке запуска
        """
        # Завершаем предыдущий процесс, если он ещё выполняется
        if self.is_running:
            await self.terminate()
        
        self._process_type = process_type
        self._status = ProcessStatus(
            start_time=datetime.now(),
            process_type=process_type,
        )
        
        self._send_message(
            AppMessage.info(
                f"🚀 Запуск {process_type.display_name}...",
                source="ProcessRunner"
            )
        )
        
        try:
            self._process = await asyncio.create_subprocess_exec(
                *command,
                cwd=working_dir,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
        except FileNotFoundError:
            self._status.error = f"Исполняемый файл не найден: {command[0]}"
            self._send_message(
                AppMessage.error(self._status.error, source="ProcessRunner")
            )
            self._status.end_time = datetime.now()
            return -1
            
        except PermissionError:
            self._status.error = f"Нет прав на запуск: {command[0]}"
            self._send_message(
                AppMessage.error(self._status.error, source="ProcessRunner")
            )
            self._status.end_time = datetime.now()
            return -1
            
        except Exception as error:
            self._status.error = f"Ошибка запуска: {error}"
            self._send_message(
                AppMessage.error(self._status.error, source="ProcessRunner")
            )
            self._status.end_time = datetime.now()
            return -1
        
        self._status.pid = self._process.pid
        self._send_message(
            AppMessage.debug(f"  PID: {self._status.pid}", source="ProcessRunner")
        )
        
        # Запускаем асинхронное чтение потоков
        self._read_tasks = [
            asyncio.create_task(self._read_stream(self._process.stdout, "stdout")),
            asyncio.create_task(self._read_stream(self._process.stderr, "stderr")),
        ]
        
        # Ожидаем завершения процесса
        try:
            return_code = await asyncio.wait_for(
                self._process.wait(),
                timeout=timeout
            )
            
        except asyncio.TimeoutError:
            if process_type == ProcessType.INTERVAL:
                self._send_message(
                    AppMessage.debug(
                        "ℹ️ Interval.exe: превышен таймаут (штатное поведение)",
                        source="ProcessRunner"
                    )
                )
                # Явно завершаем процесс, так как мы его больше не ждем
                if self._process:
                    try:
                        self._process.terminate()
                        await asyncio.sleep(0.1) # Даем время на завершение
                        if self._process.returncode is None:
                            self._process.kill()
                    except ProcessLookupError:
                        pass # Процесс уже завершился
                return_code = 0
            else:
                self._send_message(
                    AppMessage.warning(
                        f"⚠️ Превышено время выполнения ({timeout} с)",
                        source="ProcessRunner"
                    )
                )
                await self.terminate()
                return_code = -1
                
        finally:
            # Отменяем задачи чтения
            for task in self._read_tasks:
                task.cancel()
            
            if self._read_tasks:
                await asyncio.gather(*self._read_tasks, return_exceptions=True)
                self._read_tasks.clear()
            
            self._status.end_time = datetime.now()
            self._status.exit_code = return_code
        
        # Итоговое сообщение
        if return_code == 0:
            self._send_message(
                AppMessage.info(
                    f"✅ {process_type.display_name} успешно завершён",
                    source="ProcessRunner"
                )
            )
        else:
            self._send_message(
                AppMessage.warning(
                    f"⚠️ {process_type.display_name} завершён с кодом: {return_code}",
                    source="ProcessRunner"
                )
            )
        
        return return_code
    
    # ==================== ЧТЕНИЕ ВЫВОДА ====================
    async def _read_stream(self, stream: Optional[asyncio.StreamReader], name: str) -> None:
        """
        Читает поток вывода, фильтрует и отправляет в систему сообщений.
        
        Args:
            stream: Поток для чтения
            name: Имя потока (stdout/stderr)
        """
        if not stream:
            return
        
        buffer = bytearray()
        
        while True:
            try:
                chunk = await asyncio.wait_for(stream.read(8192), timeout=0.1)
                
                if not chunk:
                    # Остаток данных в буфере
                    if buffer:
                        line = self._decode_bytes(buffer)
                        self._process_output_line(line)
                    break
                
                buffer.extend(chunk)
                
                # Обрабатываем все полные строки
                while b'\n' in buffer:
                    line_bytes, buffer = buffer.split(b'\n', 1)
                    line = self._decode_bytes(line_bytes)
                    
                    # ОЧИСТКА: только базовое объединение пробелов
                    cleaned = ' '.join(line.split())
                    
                    if cleaned:
                        self._process_output_line(cleaned)
                
                # Защита от слишком длинных строк без \n
                if len(buffer) > 65536:
                    line = self._decode_bytes(buffer)
                    cleaned = ' '.join(line.split())
                    if cleaned:
                        self._process_output_line(cleaned)
                    buffer.clear()
                        
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as error:
                self._send_message(
                    AppMessage.debug(
                        f"⚠️ Ошибка чтения {name}: {error}",
                        source="ProcessRunner"
                    )
                )
                break

    # ============ ИСПРАВЛЕНИЕ: ЕДИНАЯ ТОЧКА ФИЛЬТРАЦИИ ============
    def _process_output_line(self, line: str) -> None:
        """
        Единый метод фильтрации вывода.
        ВСЯ логика фильтрации собрана ЗДЕСЬ.
        """
        if not line:
            return
        
        # === ОБЩИЕ ПРАВИЛА ДЛЯ ВСЕХ ПРОЦЕССОВ ===
        
        # 1. Проверка на бинарные данные
        if self.GENERAL_BLOCK_RULES["binary_data"](line):
            return
        
        # 2. Проверка на начало с цифры (кроме специальных случаев)
        if self.GENERAL_BLOCK_RULES["starts_with_digit"](line):
            return
        
        # 3. Проверка на SV = и Toe =
        if self.GENERAL_BLOCK_RULES["contains_sv"](line):
            return
        if self.GENERAL_BLOCK_RULES["contains_toe"](line):
            return
        
        # === СПЕЦИФИЧЕСКИЕ ПРАВИЛА ПО ТИПУ ПРОЦЕССА ===
        
        if self._process_type == ProcessType.SR2NAV:
            if not self._is_allowed_sr2nav_line(line):
                return
        elif self._process_type == ProcessType.INTERVAL:
            if not self._is_allowed_interval_line(line):
                return
        else:
            # Если тип неизвестен, показываем всё
            pass
        
        # Отправляем сообщение
        self._send_message(
            AppMessage.info(
                line, 
                source=self._process_type.display_name if self._process_type else "Process"
            )
        )
    
    def _is_allowed_sr2nav_line(self, line: str) -> bool:
        """
        Проверяет разрешена ли строка для SR2Nav.
        ИСПРАВЛЕНИЕ: использует словарь SR2NAV_ALLOWED_SUBSTRINGS.
        """
        if not line:
            return False
        
        # === СТРОГИЕ ЗАПРЕТЫ (даже если есть разрешенные подстроки) ===
        for blocked in self.SR2NAV_STRICT_BLOCKED:
            if blocked in line:
                return False
        
        # === РАЗРЕШЁННЫЕ ПОДСТРОКИ ===
        # Проверяем, содержит ли строка хотя бы одну разрешенную подстроку
        for allowed in self.SR2NAV_ALLOWED_SUBSTRINGS:
            if allowed in line:
                return True
        
        return False
    
    def _is_allowed_interval_line(self, line: str) -> bool:
        """Проверяет разрешена ли строка для Interval.exe."""
        if not line:
            return False
        
        # Проверяем по паттернам блокировки
        for pattern in self.INTERVAL_BLOCK_PATTERNS:
            if re.match(pattern, line):
                return False
        
        return True
    
    def _decode_bytes(self, data: bytes) -> str:
        """
        Пытается декодировать байты в строку, перебирая кодировки.
        """
        for encoding in ['utf-8', 'cp1251', 'cp866', 'latin-1']:
            try:
                return data.decode(encoding).rstrip()
            except UnicodeDecodeError:
                continue
        
        return data.decode('utf-8', errors='ignore').rstrip()
    
    # ==================== ОСТАНОВКА ====================
    
    async def terminate(self) -> bool:
        """
        Безопасно завершает текущий процесс.
        
        Returns:
            True если процесс был остановлен
        """
        if not self._process:
            self._send_message(
                AppMessage.info("ℹ️ Нет активного процесса", source="ProcessRunner")
            )
            return False
        
        if self._process.returncode is not None:
            self._process = None
            self._process_type = None
            self._status.is_running = False
            return True
        
        process_name = self._process_type.display_name if self._process_type else "процесс"
        self._send_message(
            AppMessage.warning(f"🛑 Остановка {process_name}...", source="ProcessRunner")
        )
        
        try:
            # Мягкое завершение
            self._process.terminate()
            
            try:
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
                self._send_message(
                    AppMessage.info(f"✓ {process_name} завершён", source="ProcessRunner")
                )
                return True
                
            except asyncio.TimeoutError:
                # Принудительное завершение
                self._send_message(
                    AppMessage.warning(f"⚠️ Принудительное завершение...", source="ProcessRunner")
                )
                self._process.kill()
                await self._process.wait()
                self._send_message(
                    AppMessage.info(f"✓ {process_name} остановлен", source="ProcessRunner")
                )
                return True
                
        except ProcessLookupError:
            self._send_message(
                AppMessage.info(f"✓ {process_name} уже завершён", source="ProcessRunner")
            )
            return True
            
        except Exception as error:
            self._send_message(
                AppMessage.error(f"❌ Ошибка остановки: {error}", source="ProcessRunner")
            )
            return False
            
        finally:
            self._process = None
            self._process_type = None
            self._status.is_running = False
            self._status.end_time = datetime.now()
    
    # ==================== ВСПОМОГАТЕЛЬНЫЕ ====================
    
    def _send_message(self, message: AppMessage) -> None:
        """Отправляет сообщение через колбэк."""
        if self._message_callback:
            try:
                self._message_callback(message)
            except Exception as e:
                print(f"[ProcessRunner] Ошибка отправки сообщения: {e}")