#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Асинхронный менеджер внешних процессов.

Обеспечивает запуск, мониторинг и безопасное завершение внешних программ
(Interval.exe, SR2Nav.exe) с фильтрацией вывода и отправкой сообщений
в систему логирования.

Ключевые возможности:
    - Асинхронный запуск процессов без блокировки основного потока
    - Чтение и фильтрация stdout/stderr в реальном времени
    - Поддержка таймаутов с корректной обработкой (Interval.exe может завершаться по таймауту)
    - Безопасное завершение (terminate → kill при зависании)
    - Декодирование вывода в нескольких кодировках (utf-8, cp1251, cp866)
    - Интеллектуальная фильтрация: только значимые строки попадают в лог

Архитектура фильтрации:
    Вся логика фильтрации централизована в методе _process_output_line().
    Для каждого типа процесса определены свои правила разрешённых/запрещённых строк.
"""
import asyncio
import re
from typing import Optional, List, Callable, Dict, Set, Tuple
from enum import Enum, auto
from dataclasses import dataclass, field
from datetime import datetime

from core.message_system import AppMessage, MessageLevel


class ProcessType(Enum):
    """
    Типы поддерживаемых внешних процессов.
    
    Каждый тип имеет человекочитаемое имя для отображения в логах.
    """
    INTERVAL = auto()
    SR2NAV = auto()
    
    @property
    def display_name(self) -> str:
        """Возвращает имя процесса для отображения в UI."""
        return {
            ProcessType.INTERVAL: "Interval.exe",
            ProcessType.SR2NAV: "SR2Nav.exe",
        }[self]


@dataclass
class ProcessStatus:
    """
    Текущее состояние внешнего процесса.
    
    Содержит всю информацию о запущенном процессе: PID, тип, статус,
    код возврата, время начала и окончания.
    
    Attributes:
        pid: Идентификатор процесса
        process_type: Тип процесса (Interval/SR2Nav)
        is_running: Флаг активности
        exit_code: Код возврата (None если ещё не завершён)
        error: Сообщение об ошибке запуска
        start_time: Время запуска
        end_time: Время завершения
    """
    pid: Optional[int] = None
    process_type: Optional[ProcessType] = None
    is_running: bool = False
    exit_code: Optional[int] = None
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def duration(self) -> Optional[float]:
        """Длительность выполнения в секундах (если процесс завершён)."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None


class ProcessRunner:
    """
    Асинхронный менеджер внешних процессов.
    
    Отвечает за:
        - Запуск процессов с заданными параметрами
        - Асинхронное чтение stdout/stderr
        - Фильтрацию и форматирование вывода
        - Контроль времени выполнения (таймауты)
        - Безопасное завершение процессов
    
    Особенности реализации:
        - Для каждого типа процесса определён свой набор правил фильтрации
        - Interval.exe имеет специальную обработку таймаута (штатное поведение)
        - Все сообщения проходят через единую систему логирования
        - При завершении процесса автоматически отменяются задачи чтения
    
    Пример:
        >>> runner = ProcessRunner(message_callback=my_callback)
        >>> exit_code = await runner.run(
        ...     command=["Interval.exe"],
        ...     working_dir="/path/to/work",
        ...     process_type=ProcessType.INTERVAL,
        ...     timeout=1.5
        ... )
    """
    
    # ============ ПРАВИЛА ФИЛЬТРАЦИИ ДЛЯ SR2NAV ============
    # Категории разрешённых строк с подстроками для идентификации
    SR2NAV_FILTER_RULES: Dict[str, Set[str]] = {
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
    
    # Объединённый набор всех разрешённых подстрок для быстрой проверки
    SR2NAV_ALLOWED_SUBSTRINGS: Set[str] = set()
    for category_rules in SR2NAV_FILTER_RULES.values():
        SR2NAV_ALLOWED_SUBSTRINGS.update(category_rules)
    
    # Строгие запреты - даже если строка содержит разрешённую подстроку,
    # но также содержит запрещённую, она будет отфильтрована
    SR2NAV_STRICT_BLOCKED: Set[str] = {
        "SV =",      # Сырые данные по спутникам (слишком детально)
        "Toe =",     # Технические параметры эфемерид
        "178925",    # Конкретные значения (шум)
        "208800",    # Конкретные значения (шум)
        "PRN",       # Перечисление PRN номеров
    }
    
    # ============ ПРАВИЛА ФИЛЬТРАЦИИ ДЛЯ INTERVAL.EXE ============
    # Паттерны для блокировки (регулярные выражения)
    INTERVAL_BLOCK_PATTERNS: List[str] = [
        r'^\*.*\*$',      # Строки с рамкой (украшательства)
        r'^I:',           # Данные с префиксом I: (внутренняя диагностика)
        r'^[\d\s\.]+$',   # Только цифры, пробелы, точки (сырые данные)
    ]
    
    # ============ ОБЩИЕ ПРАВИЛА ФИЛЬТРАЦИИ ============
    # Применяются ко всем процессам независимо от типа
    GENERAL_BLOCK_RULES = {
        # Бинарные данные: длинные строки с цифрами в начале
        "binary_data": lambda line: len(line) > 200 and any(c.isdigit() for c in line[:10]),
        
        # Строки, начинающиеся с цифры (кроме специально разрешённых)
        "starts_with_digit": lambda line: bool(line) and line[0].isdigit() and not line.startswith("Time span:"),
        
        # Технические данные по спутникам
        "contains_sv": lambda line: "SV =" in line,
        "contains_toe": lambda line: "Toe =" in line,
    }
    
    def __init__(
        self,
        message_callback: Callable[[AppMessage], None],
    ):
        """
        Инициализация менеджера процессов.
        
        Args:
            message_callback: Функция для отправки сообщений в систему логирования.
                             Должна принимать AppMessage.
        """
        self._message_callback = message_callback
        self._process: Optional[asyncio.subprocess.Process] = None
        self._process_type: Optional[ProcessType] = None
        self._status = ProcessStatus()
        self._read_tasks: List[asyncio.Task] = []
        self._message_accumulator = {}  # Для накопления частичных сообщений
    
    # ==================== СВОЙСТВА ====================
    
    @property
    def is_running(self) -> bool:
        """Проверяет, выполняется ли процесс в данный момент."""
        return self._process is not None and self._process.returncode is None
    
    @property
    def status(self) -> ProcessStatus:
        """
        Возвращает копию текущего состояния процесса.
        
        Returns:
            ProcessStatus с актуальными данными (PID, время запуска и т.д.)
        """
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
    
    # ==================== ЗАПУСК ПРОЦЕССА ====================
    
    async def run(
        self,
        command: List[str],
        working_dir: str,
        process_type: ProcessType,
        timeout: Optional[float] = None,
    ) -> int:
        """
        Запускает внешний процесс и ожидает его завершения.
        
        Алгоритм:
            1. Завершает предыдущий процесс, если он ещё выполняется
            2. Создаёт подпроцесс с перенаправлением потоков
            3. Запускает асинхронное чтение stdout/stderr
            4. Ожидает завершения с учётом таймаута
            5. Обрабатывает специальные случаи (таймаут Interval.exe)
            6. Возвращает код возврата
        
        Args:
            command: Команда и аргументы (например, ["Interval.exe"])
            working_dir: Рабочая директория для запуска
            process_type: Тип процесса (определяет фильтрацию)
            timeout: Максимальное время выполнения в секундах.
                    None - бесконечно, 0 - без ожидания.
                    
        Returns:
            Код возврата процесса, или -1 при ошибке запуска
            
        Note:
            Для Interval.exe таймаут обрабатывается специально:
            превышение времени считается штатным поведением.
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
        
        # Ожидаем завершения процесса с учётом таймаута
        try:
            return_code = await asyncio.wait_for(
                self._process.wait(),
                timeout=timeout
            )
            
        except asyncio.TimeoutError:
            # Специальная обработка для Interval.exe
            if process_type == ProcessType.INTERVAL:
                self._send_message(
                    AppMessage.debug(
                        "ℹ️ Interval.exe: превышен таймаут (штатное поведение)",
                        source="ProcessRunner"
                    )
                )
                # Явно завершаем процесс, так как мы его больше не ждём
                if self._process:
                    try:
                        self._process.terminate()
                        await asyncio.sleep(0.1)  # Даём время на завершение
                        if self._process.returncode is None:
                            self._process.kill()
                    except ProcessLookupError:
                        pass  # Процесс уже завершился
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
    
    # ==================== ЧТЕНИЕ И ФИЛЬТРАЦИЯ ВЫВОДА ====================
    
    async def _read_stream(self, stream: Optional[asyncio.StreamReader], name: str) -> None:
        """
        Читает поток вывода, буферизирует и обрабатывает строки.
        
        Args:
            stream: Поток для чтения (stdout или stderr)
            name: Имя потока для диагностических сообщений
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
                    
                    # Базовая очистка: объединяем множественные пробелы
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

    def _process_output_line(self, line: str) -> None:
        """
        Централизованная фильтрация строк вывода.
        
        Алгоритм:
            1. Применяет общие правила фильтрации (бинарные данные, цифры в начале)
            2. Применяет специфические правила в зависимости от типа процесса
            3. Отправляет разрешённые строки в систему сообщений
        
        Args:
            line: Очищенная строка вывода (без лишних пробелов)
        """
        if not line:
            return
        
        # === ОБЩИЕ ПРАВИЛА ДЛЯ ВСЕХ ПРОЦЕССОВ ===
        
        # 1. Проверка на бинарные данные (очень длинные строки с цифрами)
        if self.GENERAL_BLOCK_RULES["binary_data"](line):
            return
        
        # 2. Проверка на начало с цифры (кроме специально разрешённых)
        if self.GENERAL_BLOCK_RULES["starts_with_digit"](line):
            return
        
        # 3. Проверка на технические данные по спутникам
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
            # Если тип неизвестен, показываем всё (для отладки)
            pass
        
        # Отправляем сообщение в систему логирования
        self._send_message(
            AppMessage.info(
                line, 
                source=self._process_type.display_name if self._process_type else "Process"
            )
        )
    
    def _is_allowed_sr2nav_line(self, line: str) -> bool:
        """
        Проверяет, разрешена ли строка для отображения при работе SR2Nav.
        
        Правила:
            1. Строка не должна содержать строго запрещённые подстроки
            2. Строка должна содержать хотя бы одну разрешённую подстроку
        
        Args:
            line: Строка для проверки
            
        Returns:
            True если строка должна быть показана пользователю
        """
        if not line:
            return False
        
        # Строгие запреты - даже если есть разрешённые подстроки
        for blocked in self.SR2NAV_STRICT_BLOCKED:
            if blocked in line:
                return False
        
        # Проверка на наличие хотя бы одной разрешённой подстроки
        for allowed in self.SR2NAV_ALLOWED_SUBSTRINGS:
            if allowed in line:
                return True
        
        return False
    
    def _is_allowed_interval_line(self, line: str) -> bool:
        """
        Проверяет, разрешена ли строка для отображения при работе Interval.exe.
        
        Args:
            line: Строка для проверки
            
        Returns:
            True если строка должна быть показана пользователю
        """
        if not line:
            return False
        
        # Проверяем по паттернам блокировки
        for pattern in self.INTERVAL_BLOCK_PATTERNS:
            if re.match(pattern, line):
                return False
        
        return True
    
    def _decode_bytes(self, data: bytes) -> str:
        """
        Декодирует байты в строку, перебирая возможные кодировки.
        
        Args:
            data: Байтовые данные для декодирования
            
        Returns:
            Декодированная строка, очищенная от пробельных символов в конце
        """
        for encoding in ['utf-8', 'cp1251', 'cp866', 'latin-1']:
            try:
                return data.decode(encoding).rstrip()
            except UnicodeDecodeError:
                continue
        
        # Если ничего не подошло - игнорируем ошибки
        return data.decode('utf-8', errors='ignore').rstrip()
    
    # ==================== ЗАВЕРШЕНИЕ ПРОЦЕССА ====================
    
    async def terminate(self) -> bool:
        """
        Безопасно завершает текущий процесс.
        
        Алгоритм:
            1. Проверяет наличие активного процесса
            2. Отправляет сигнал terminate (мягкое завершение)
            3. Ждёт до 2 секунд
            4. Если процесс не завершился - отправляет kill
            5. Очищает состояние
        
        Returns:
            True если процесс был остановлен (или уже не выполнялся)
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
            self._message_accumulator.clear()
    
    # ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================
    
    def _send_message(self, message: AppMessage) -> None:
        """Отправляет сообщение через колбэк в систему логирования."""
        if self._message_callback:
            try:
                self._message_callback(message)
            except Exception as e:
                print(f"[ProcessRunner] Ошибка отправки сообщения: {e}")