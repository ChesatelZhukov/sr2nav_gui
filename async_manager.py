#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Управление единым циклом событий asyncio в отдельном потоке.

Обеспечивает потокобезопасный запуск асинхронных корутин из синхронного
кода Tkinter. Все длительные операции (анализ, обработка файлов) выполняются
в фоновом потоке, не блокируя пользовательский интерфейс.

Архитектурные принципы:
    - Единый event loop в фоновом потоке (daemon thread)
    - Потокобезопасный запуск через asyncio.run_coroutine_threadsafe
    - Автоматическая очистка завершённых задач
    - Поддержка периодических задач с защитой от остановки
    - Централизованное управление жизненным циклом всех асинхронных операций

Потокобезопасность:
    - Все операции с внутренними структурами защищены RLock
    - Callback'и выполняются в потоке event loop
    - Future'ы потокобезопасны по своей природе

Пример использования:
    >>> manager = AsyncManager()
    >>> manager.start()
    >>> 
    >>> # Запуск одноразовой задачи
    >>> future = manager.run_coroutine(my_coroutine(), name="my_task")
    >>> result = future.result(timeout=5.0)
    >>> 
    >>> # Запуск периодической задачи
    >>> manager.run_periodic(check_status, 60.0, "status_checker")
    >>> 
    >>> # Остановка при завершении приложения
    >>> manager.stop(timeout=2.0)
"""
import asyncio
import threading
import time
from typing import Optional, Dict, Any, Callable, Awaitable
import concurrent.futures
from dataclasses import dataclass
from enum import Enum, auto


class TaskPriority(Enum):
    """
    Приоритет выполнения задачи в event loop.
    
    В текущей реализации используется только для информационных целей,
    но может быть расширен для реального приоритезирования в будущем.
    """
    LOW = auto()
    NORMAL = auto()
    HIGH = auto()


@dataclass
class TaskInfo:
    """
    Информация о зарегистрированной задаче.
    
    Хранит метаданные задачи для мониторинга и управления.
    
    Attributes:
        future: Future для отслеживания результата
        name: Имя задачи (для отладки и отображения)
        priority: Приоритет выполнения
        created_at: Время создания (timestamp)
    """
    future: concurrent.futures.Future
    name: Optional[str] = None
    priority: TaskPriority = TaskPriority.NORMAL
    created_at: float = 0.0


class AsyncManager:
    """
    Центральный менеджер асинхронных операций.
    
    Управляет единым event loop в фоновом потоке, обеспечивая
    потокобезопасный запуск корутин и автоматическую очистку ресурсов.
    
    Особенности:
        - Единый event loop в фоновом потоке (daemon thread)
        - Автоматическая очистка завершённых задач
        - Поддержка периодических задач с защитой от остановки
        - Потокобезопасный запуск из любого места (включая Tkinter)
        - Глобальный обработчик ошибок
        - Мониторинг активных задач
    
    Атрибуты:
        _loop: Главный event loop в фоновом потоке
        _thread: Фоновый поток для event loop
        _running: Флаг работы цикла
        _stop_event: Событие для сигнализации остановки
        _tasks: Словарь активных задач {id: TaskInfo}
        _periodic_tasks: Словарь периодических задач {имя: TaskInfo}
        _lock: Блокировка для потокобезопасного доступа
        _error_handler: Глобальный обработчик ошибок
    """
    
    def __init__(self):
        """Инициализация менеджера (без запуска)."""
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._stop_event = threading.Event()
        
        self._tasks: Dict[int, TaskInfo] = {}
        self._periodic_tasks: Dict[str, TaskInfo] = {}
        self._task_counter = 0
        
        self._lock = threading.RLock()
        self._error_handler: Optional[Callable[[Exception, str], None]] = None
    
    # ==================== УПРАВЛЕНИЕ ЖИЗНЕННЫМ ЦИКЛОМ ====================
    
    def start(self) -> None:
        """
        Запускает фоновый поток с event loop.
        
        Создаёт новый event loop в отдельном потоке и ожидает его готовности.
        Поток запускается как daemon, поэтому он автоматически завершится
        при выходе из основной программы.
        
        Безопасен для многократного вызова (повторные вызовы игнорируются).
        
        Raises:
            RuntimeError: Если не удаётся запустить цикл событий
        """
        if self._running:
            return
        
        self._stop_event.clear()
        loop_ready = threading.Event()
        
        def _run_loop() -> None:
            """Функция, выполняемая в фоновом потоке."""
            try:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                self._running = True
                loop_ready.set()  # Сигнал о готовности основному потоку
                self._loop.run_forever()
                
            except Exception as error:
                print(f"[AsyncManager] Ошибка цикла: {error}")
                self._running = False
                
            finally:
                self._cleanup_loop()
                self._thread = None
        
        self._thread = threading.Thread(target=_run_loop, daemon=True)
        self._thread.start()
        
        # Ожидаем готовности цикла (максимум 1 секунда)
        if not loop_ready.wait(timeout=1.0):
            raise RuntimeError("Не удалось запустить цикл событий")
        
        # Дополнительная проверка готовности
        while self._loop is None and not self._stop_event.is_set():
            time.sleep(0.005)
    
    def stop(self, timeout: float = 2.0) -> None:
        """
        Останавливает event loop и освобождает ресурсы.
        
        Последовательность действий:
            1. Устанавливает флаг остановки
            2. Отменяет все активные задачи
            3. Останавливает event loop
            4. Ожидает завершения потока
        
        Args:
            timeout: Максимальное время ожидания завершения потока (сек)
        """
        if not self._running or not self._loop:
            return
        
        self._stop_event.set()
        self._running = False
        
        try:
            # Отменяем все задачи
            self.cancel_all_tasks()
            
            # Останавливаем цикл
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)
            
            # Ожидаем завершения потока
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=timeout)
                
        except Exception as error:
            print(f"[AsyncManager] Ошибка при остановке: {error}")
        finally:
            self._thread = None
    
    def _cleanup_loop(self) -> None:
        """
        Закрывает цикл и очищает оставшиеся задачи.
        
        Вызывается автоматически при завершении потока.
        Отменяет все незавершённые задачи и закрывает цикл.
        """
        if not self._loop:
            return
        
        try:
            # Собираем все незавершённые задачи
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            
            # Ожидаем их завершения (с отменой)
            if pending and self._loop.is_running():
                self._loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            
            # Закрываем цикл
            self._loop.close()
            
        except Exception as error:
            print(f"[AsyncManager] Ошибка при очистке: {error}")
        finally:
            self._loop = None
    
    # ==================== УПРАВЛЕНИЕ ЗАДАЧАМИ ====================
    
    def run_coroutine(
        self, 
        coro: Awaitable,
        name: Optional[str] = None,
        priority: TaskPriority = TaskPriority.NORMAL
    ) -> concurrent.futures.Future:
        """
        Запускает корутину в главном цикле событий.
        
        Args:
            coro: Корутина для выполнения (awaitable объект)
            name: Имя задачи для отладки и мониторинга
            priority: Приоритет выполнения (информационно)
            
        Returns:
            Future для отслеживания результата выполнения
            
        Raises:
            RuntimeError: Если цикл событий не инициализирован
            
        Example:
            >>> future = manager.run_coroutine(
            ...     my_async_function(),
            ...     name="data_processing"
            ... )
            >>> result = future.result(timeout=10.0)
        """
        if not self._running:
            self.start()
        
        if not self._loop:
            raise RuntimeError("Цикл событий не инициализирован")
        
        # Потокобезопасный запуск корутины
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        
        # Регистрируем задачу
        with self._lock:
            task_id = self._task_counter
            self._task_counter += 1
            
            self._tasks[task_id] = TaskInfo(
                future=future,
                name=name or f"task-{task_id}",
                priority=priority,
                created_at=time.time()
            )
        
        # Автоматическое удаление при завершении
        future.add_done_callback(lambda _: self._remove_task(task_id))
        
        return future
    
    def run_periodic(
        self,
        coro_func: Callable[[], Awaitable],
        interval: float,
        task_name: str,
        error_handler: Optional[Callable[[Exception], None]] = None
    ) -> concurrent.futures.Future:
        """
        Запускает периодическую задачу.
        
        Создаёт задачу, которая выполняет переданную корутину
        с заданным интервалом, пока менеджер не будет остановлен.
        
        Args:
            coro_func: Функция, возвращающая корутину для выполнения
            interval: Интервал выполнения в секундах
            task_name: Уникальное имя задачи (для управления и отмены)
            error_handler: Специфичный обработчик ошибок для этой задачи.
                          Если не указан, используется глобальный обработчик.
            
        Returns:
            Future периодической задачи (никогда не завершается при нормальной работе)
            
        Example:
            >>> async def check_status():
            ...     status = await get_status()
            ...     print(f"Status: {status}")
            >>> 
            >>> manager.run_periodic(
            ...     check_status,
            ...     interval=60.0,
            ...     task_name="status_checker"
            ... )
        """
        async def _wrapper() -> None:
            """Внутренняя обёртка с контролем остановки."""
            while self._running and not self._stop_event.is_set():
                try:
                    await coro_func()
                except asyncio.CancelledError:
                    break
                except Exception as error:
                    if error_handler:
                        error_handler(error)
                    elif self._error_handler:
                        self._error_handler(error, task_name)
                    else:
                        print(f"[{task_name}] Ошибка: {error}")
                
                # Не выполняем sleep, если приложение уже останавливается
                if self._running and not self._stop_event.is_set():
                    await asyncio.sleep(interval)
        
        # Отменяем предыдущую задачу с таким именем
        self.cancel_periodic(task_name)
        
        future = self.run_coroutine(_wrapper(), name=task_name)
        
        with self._lock:
            self._periodic_tasks[task_name] = TaskInfo(
                future=future,
                name=task_name,
                created_at=time.time()
            )
        
        return future
    
    def cancel_task(self, task_id: int) -> bool:
        """
        Отменяет задачу по её идентификатору.
        
        Args:
            task_id: Идентификатор задачи (из регистрации)
            
        Returns:
            True если задача найдена и отменена, False если задача
            уже завершена или не существует
        """
        with self._lock:
            task_info = self._tasks.pop(task_id, None)
            if task_info and not task_info.future.done():
                task_info.future.cancel()
                return True
        return False
    
    def cancel_periodic(self, task_name: str) -> bool:
        """
        Отменяет периодическую задачу по имени.
        
        Args:
            task_name: Имя задачи (заданное при запуске)
            
        Returns:
            True если задача найдена и отменена
        """
        with self._lock:
            task_info = self._periodic_tasks.pop(task_name, None)
            if task_info and not task_info.future.done():
                task_info.future.cancel()
                return True
        return False
    
    def cancel_all_tasks(self) -> int:
        """
        Отменяет все активные задачи (обычные и периодические).
        
        Returns:
            Количество отменённых задач
        """
        cancelled = 0
        
        with self._lock:
            for task_id, task_info in list(self._tasks.items()):
                if not task_info.future.done():
                    task_info.future.cancel()
                    cancelled += 1
            self._tasks.clear()
        
        for task_name in list(self._periodic_tasks.keys()):
            if self.cancel_periodic(task_name):
                cancelled += 1
        
        return cancelled
    
    def _remove_task(self, task_id: int) -> None:
        """
        Удаляет завершённую задачу из хранилища.
        
        Вызывается автоматически через add_done_callback.
        
        Args:
            task_id: Идентификатор завершённой задачи
        """
        with self._lock:
            self._tasks.pop(task_id, None)
    
    # ==================== НАСТРОЙКА И МОНИТОРИНГ ====================
    
    def set_error_handler(self, handler: Callable[[Exception, str], None]) -> None:
        """
        Устанавливает глобальный обработчик ошибок для периодических задач.
        
        Args:
            handler: Функция, принимающая (исключение, имя_задачи)
        """
        self._error_handler = handler
    
    @property
    def is_running(self) -> bool:
        """Проверяет, запущен ли цикл событий."""
        return self._running and self._loop is not None
    
    @property
    def active_task_count(self) -> int:
        """
        Возвращает количество выполняющихся задач (без учёта периодических).
        """
        with self._lock:
            active = sum(
                1 for task in self._tasks.values()
                if not task.future.done()
            )
        return active
    
    @property
    def active_periodic_count(self) -> int:
        """Возвращает количество активных периодических задач."""
        with self._lock:
            active = sum(
                1 for task in self._periodic_tasks.values()
                if not task.future.done()
            )
        return active
    
    def get_task_names(self) -> Dict[str, str]:
        """
        Возвращает информацию об активных задачах.
        
        Returns:
            Словарь {имя_задачи: статус} для мониторинга
        """
        result = {}
        with self._lock:
            for task_id, info in self._tasks.items():
                if not info.future.done():
                    name = info.name or f"ID:{task_id}"
                    result[name] = "выполняется"
            
            for name, info in self._periodic_tasks.items():
                if not info.future.done():
                    result[name] = "периодическая"
        return result


# ==================== ГЛОБАЛЬНЫЙ ДОСТУП (СИНГЛТОН) ====================

_ASYNC_MANAGER_INSTANCE: Optional[AsyncManager] = None


def get_async_manager() -> AsyncManager:
    """
    Возвращает глобальный экземпляр менеджера (синглтон).
    
    При первом вызове создаёт экземпляр AsyncManager, при последующих —
    возвращает уже существующий. Это гарантирует, что все компоненты
    используют один и тот же event loop.
    
    Returns:
        AsyncManager: Глобальный менеджер асинхронных операций
        
    Example:
        >>> manager = get_async_manager()
        >>> manager.start()
        >>> future = manager.run_coroutine(my_coro())
    """
    global _ASYNC_MANAGER_INSTANCE
    if _ASYNC_MANAGER_INSTANCE is None:
        _ASYNC_MANAGER_INSTANCE = AsyncManager()
    return _ASYNC_MANAGER_INSTANCE


# Для обратной совместимости с существующим кодом
async_manager = get_async_manager()