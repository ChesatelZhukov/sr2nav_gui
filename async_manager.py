#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Управление единым циклом событий asyncio в отдельном потоке.
Потокобезопасный запуск корутин, автоматическая очистка задач.
"""

import asyncio
import threading
import time
from typing import Optional, Dict, Any, Callable, Awaitable
import concurrent.futures
from dataclasses import dataclass
from enum import Enum, auto


class TaskPriority(Enum):
    """Приоритет выполнения задачи."""
    LOW = auto()
    NORMAL = auto()
    HIGH = auto()


@dataclass
class TaskInfo:
    """Информация о зарегистрированной задаче."""
    future: concurrent.futures.Future
    name: Optional[str] = None
    priority: TaskPriority = TaskPriority.NORMAL
    created_at: float = 0.0


class AsyncManager:
    """
    Центральный менеджер асинхронных операций.
    
    Особенности:
        - Единый event loop в фоновом потоке
        - Автоматическая очистка завершённых задач
        - Поддержка периодических задач с защитой от остановки
        - Потокобезопасный запуск из любого места
    """
    
    def __init__(self):
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
        if self._running:
            return
        
        self._stop_event.clear()
        loop_ready = threading.Event()  # <-- Добавить
        
        def _run_loop() -> None:
            try:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                self._running = True
                loop_ready.set()  # <-- Сигнал о готовности
                self._loop.run_forever()
                
            except Exception as error:
                print(f"[AsyncManager] Ошибка цикла: {error}")
                self._running = False
                
            finally:
                self._cleanup_loop()
                self._thread = None
        
        self._thread = threading.Thread(target=_run_loop, daemon=True)
        self._thread.start()
        loop_ready.wait(timeout=1.0)  # <-- Ожидание готовности
        
        # Ожидаем готовности цикла
        while self._loop is None and not self._stop_event.is_set():
            time.sleep(0.005)
    
    def stop(self, timeout: float = 2.0) -> None:
        """
        Останавливает event loop и освобождает ресурсы.
        
        Args:
            timeout: Максимальное время ожидания завершения потока
        """
        if not self._running or not self._loop:
            return
        
        self._stop_event.set()
        self._running = False
        
        try:
            self.cancel_all_tasks()
            
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)
            
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=timeout)
                
        except Exception as error:
            print(f"[AsyncManager] Ошибка при остановке: {error}")
        finally:
            self._thread = None
    
    def _cleanup_loop(self) -> None:
        """Закрывает цикл и очищает оставшиеся задачи."""
        if not self._loop:
            return
        
        try:
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            
            if pending and self._loop.is_running():
                self._loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            
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
            coro: Корутина для выполнения
            name: Имя задачи (для отладки)
            priority: Приоритет выполнения
            
        Returns:
            Future для отслеживания результата
        """
        if not self._running:
            self.start()
        
        
        if not self._loop:
            raise RuntimeError("Цикл событий не инициализирован")
        
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        
        with self._lock:
            task_id = self._task_counter
            self._task_counter += 1
            
            self._tasks[task_id] = TaskInfo(
                future=future,
                name=name or f"task-{task_id}",
                priority=priority,
                created_at=time.time()
            )
        
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
        
        Args:
            coro_func: Функция, возвращающая корутину
            interval: Интервал выполнения (секунды)
            task_name: Уникальное имя задачи
            error_handler: Обработчик ошибок выполнения
            
        Returns:
            Future периодической задачи
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
        Отменяет задачу по идентификатору.
        
        Returns:
            True если задача найдена и отменена
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
        Отменяет все активные задачи.
        
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
        """Удаляет завершённую задачу из хранилища."""
        with self._lock:
            self._tasks.pop(task_id, None)
    
    # ==================== НАСТРОЙКА ====================
    
    def set_error_handler(self, handler: Callable[[Exception, str], None]) -> None:
        """Устанавливает глобальный обработчик ошибок."""
        self._error_handler = handler
    
    # ==================== СВОЙСТВА ====================
    
    @property
    def is_running(self) -> bool:
        """Запущен ли цикл событий."""
        return self._running and self._loop is not None
    
    @property
    def active_task_count(self) -> int:
        """Количество выполняющихся задач."""
        with self._lock:
            active = sum(
                1 for task in self._tasks.values()
                if not task.future.done()
            )
        return active
    
    @property
    def active_periodic_count(self) -> int:
        """Количество активных периодических задач."""
        with self._lock:
            active = sum(
                1 for task in self._periodic_tasks.values()
                if not task.future.done()
            )
        return active
    
    def get_task_names(self) -> Dict[str, str]:
        """Возвращает словарь {имя: статус} активных задач."""
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


# ==================== ГЛОБАЛЬНЫЙ ДОСТУП ====================

_ASYNC_MANAGER_INSTANCE: Optional[AsyncManager] = None


def get_async_manager() -> AsyncManager:
    """Возвращает глобальный экземпляр менеджера (синглтон)."""
    global _ASYNC_MANAGER_INSTANCE
    if _ASYNC_MANAGER_INSTANCE is None:
        _ASYNC_MANAGER_INSTANCE = AsyncManager()
    return _ASYNC_MANAGER_INSTANCE


# Для обратной совместимости
async_manager = get_async_manager()