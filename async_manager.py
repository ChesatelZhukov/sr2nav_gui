#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Менеджер асинхронных операций с единым event loop.
Запускает asyncio цикл в отдельном потоке и управляет задачами.
"""
import asyncio
import threading
import time
from typing import Optional, Dict, Any, Callable
import concurrent.futures
from weakref import WeakValueDictionary


class AsyncManager:
    """
    Управляет одним главным циклом asyncio в отдельном потоке.
    
    Особенности:
        - Единый event loop для всего приложения
        - Потокобезопасный запуск корутин
        - Автоматическая очистка завершённых задач
        - Поддержка периодических задач
    """
    
    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._tasks: Dict[int, concurrent.futures.Future] = {}
        self._task_counter = 0
        self._periodic_tasks: Dict[str, concurrent.futures.Future] = {}
        self._lock = threading.Lock()
    
    # ==================== УПРАВЛЕНИЕ ЦИКЛОМ ====================
    
    def start(self) -> None:
        """
        Запускает главный цикл asyncio в отдельном потоке.
        Если цикл уже запущен, ничего не делает.
        """
        if self._running:
            return
        
        def _run_loop():
            """Внутренняя функция для запуска event loop в потоке."""
            try:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                self._running = True
                
                # Запускаем бесконечный цикл
                self._loop.run_forever()
                
            except Exception as e:
                print(f"❌ Ошибка event loop: {e}")
                
            finally:
                # Очистка после остановки цикла
                if self._loop:
                    # Отменяем все задачи
                    pending = asyncio.all_tasks(self._loop)
                    for task in pending:
                        task.cancel()
                    
                    # Ждём завершения задач
                    if pending:
                        self._loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True)
                        )
                    
                    self._loop.close()
                    self._running = False
        
        # Создаём и запускаем поток
        self._thread = threading.Thread(target=_run_loop, daemon=True)
        self._thread.start()
        
        # Ждём инициализации цикла
        while self._loop is None:
            time.sleep(0.01)
    
    def stop(self, timeout: float = 2.0) -> None:
        """
        Останавливает главный цикл событий.
        
        Args:
            timeout: Максимальное время ожидания остановки потока (сек)
        """
        if self._loop and self._running:
            # Отменяем все задачи
            self.cancel_all_tasks()
            
            # Останавливаем цикл
            self._loop.call_soon_threadsafe(self._loop.stop)
            
            # Ждём завершения потока
            if self._thread:
                self._thread.join(timeout=timeout)
    
    # ==================== УПРАВЛЕНИЕ ЗАДАЧАМИ ====================
    
    def run_coroutine(self, coro) -> concurrent.futures.Future:
        """
        Запускает корутину в главном цикле событий.
        
        Args:
            coro: Корутина для выполнения
            
        Returns:
            Future объект для отслеживания результата
        """
        if not self._running:
            self.start()
        
        # Запускаем корутину в потокобезопасном режиме
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        
        # Сохраняем задачу с уникальным ID
        with self._lock:
            task_id = self._task_counter
            self._task_counter += 1
            self._tasks[task_id] = future
        
        # Автоматически удаляем задачу после завершения
        future.add_done_callback(lambda _: self._remove_task(task_id))
        
        return future
    
    def run_periodic(
        self, 
        coro_func: Callable, 
        interval: float, 
        task_name: str
    ) -> concurrent.futures.Future:
        """
        Запускает периодическую задачу.
        
        Args:
            coro_func: Функция, возвращающая корутину
            interval: Интервал выполнения в секундах
            task_name: Уникальное имя задачи
            
        Returns:
            Future объект периодической задачи
        """
        async def _wrapper():
            while True:
                try:
                    await coro_func()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    print(f"⚠️ Ошибка в периодической задаче {task_name}: {e}")
                
                await asyncio.sleep(interval)
        
        # Отменяем существующую задачу с таким же именем
        self.cancel_periodic(task_name)
        
        # Создаём новую
        future = asyncio.run_coroutine_threadsafe(_wrapper(), self._loop)
        
        with self._lock:
            self._periodic_tasks[task_name] = future
        
        return future
    
    def cancel_task(self, task_id: int) -> bool:
        """
        Отменяет задачу по ID.
        
        Returns:
            True если задача была отменена
        """
        with self._lock:
            if task_id in self._tasks:
                future = self._tasks[task_id]
                if not future.done():
                    future.cancel()
                del self._tasks[task_id]
                return True
        return False
    
    def cancel_periodic(self, task_name: str) -> bool:
        """
        Отменяет периодическую задачу по имени.
        
        Returns:
            True если задача была отменена
        """
        with self._lock:
            if task_name in self._periodic_tasks:
                future = self._periodic_tasks[task_name]
                if not future.done():
                    future.cancel()
                del self._periodic_tasks[task_name]
                return True
        return False
    
    def cancel_all_tasks(self) -> None:
        """Отменяет все запущенные задачи."""
        with self._lock:
            # Отменяем обычные задачи
            for task_id, future in list(self._tasks.items()):
                if not future.done():
                    future.cancel()
            self._tasks.clear()
        
        # Отменяем периодические задачи
        for task_name in list(self._periodic_tasks.keys()):
            self.cancel_periodic(task_name)
    
    def _remove_task(self, task_id: int) -> None:
        """Внутренний метод для удаления завершённой задачи."""
        with self._lock:
            self._tasks.pop(task_id, None)
    
    # ==================== СВОЙСТВА ====================
    
    @property
    def is_running(self) -> bool:
        """Запущен ли event loop."""
        return self._running
    
    @property
    def task_count(self) -> int:
        """Количество активных задач."""
        with self._lock:
            return len(self._tasks)
    
    @property
    def periodic_task_count(self) -> int:
        """Количество активных периодических задач."""
        with self._lock:
            return len(self._periodic_tasks)


# Глобальный экземпляр менеджера (синглтон)
_async_manager = None


def get_async_manager() -> AsyncManager:
    """
    Возвращает глобальный экземпляр AsyncManager.
    Создаёт его при первом вызове.
    """
    global _async_manager
    if _async_manager is None:
        _async_manager = AsyncManager()
    return _async_manager


# Для обратной совместимости
async_manager = get_async_manager()