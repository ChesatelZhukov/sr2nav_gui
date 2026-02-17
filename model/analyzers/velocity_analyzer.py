#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Анализатор VEL файлов для обработки скоростных данных.

Предоставляет чистую бизнес-логику для парсинга и анализа файлов скоростей
в формате VEL. Не имеет зависимостей от пользовательского интерфейса и может
использоваться в любом контексте (GUI, консоль, веб-сервисы).

Основные возможности:
    - Парсинг VEL файлов с извлечением временных рядов скоростей
    - Расчёт статистических показателей (макс, среднее, std)
    - Вычисление 2D и 3D скоростей
    - **Расчет максимальной 4-й разности высоты (для оценки резких скачков)**
    - Пакетный анализ всех VEL файлов в директории
    - Экспорт результатов в CSV

Формат VEL файла:
    Строки 0-1: заголовки (игнорируются)
    Строки 2+: данные с колонками:
        0: время (сек)
        5: скорость E (м/с)
        6: скорость N (м/с)
        7: скорость UP (м/с)
        3: высота (Hei) - для расчета 4-й разности
"""
import os
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class VelocityData:
    """
    Структурированные данные скоростей из VEL файла.
    
    Содержит временные ряды и метаданные о файле.
    Все массивы numpy обеспечивают эффективные вычисления.
    
    Attributes:
        filename: Имя файла (без пути)
        filepath: Полный путь к исходному файлу
        time: Массив временных меток (сек от начала суток)
        v_e: Массив скоростей по оси E (м/с)
        v_n: Массив скоростей по оси N (м/с)
        v_up: Массив вертикальных скоростей (м/с)
        height: Массив высот (м) - добавлено для расчета 4-й разности
        rows: Количество строк данных
        time_span: Кортеж (начало, конец) временного интервала
    """
    filename: str
    filepath: str
    time: np.ndarray
    v_e: np.ndarray
    v_n: np.ndarray
    v_up: np.ndarray
    height: np.ndarray  # Добавлено поле для высоты
    rows: int
    time_span: Tuple[float, float]
    
    @property
    def duration(self) -> float:
        """Длительность записи в секундах."""
        return self.time_span[1] - self.time_span[0] if len(self.time) > 1 else 0


@dataclass
class VelocityStatistics:
    """
    Статистические показатели скоростей.
    
    Содержит как базовые статистики (макс, среднее, std) по каждой оси,
    так и интегрированные показатели (2D и 3D скорости), а также новый
    показатель: максимальная 4-я разность высоты.
    
    Attributes:
        max_v_e: Максимальная скорость по E (абсолютное значение)
        max_v_n: Максимальная скорость по N (абсолютное значение)
        max_v_up: Максимальная вертикальная скорость (абсолютное значение)
        mean_v_e: Средняя скорость по E
        mean_v_n: Средняя скорость по N
        mean_v_up: Средняя вертикальная скорость
        std_v_e: Стандартное отклонение по E
        std_v_n: Стандартное отклонение по N
        std_v_up: Стандартное отклонение по вертикали
        max_speed_2d: Максимальная горизонтальная скорость
        max_speed_3d: Максимальная полная скорость
        mean_speed_2d: Средняя горизонтальная скорость
        mean_speed_3d: Средняя полная скорость
        rows_analyzed: Количество проанализированных строк
        max_height_4th_diff: Максимальная 4-я разность высоты (м) - новый показатель
    """
    max_v_e: float = 0.0
    max_v_n: float = 0.0
    max_v_up: float = 0.0
    mean_v_e: float = 0.0
    mean_v_n: float = 0.0
    mean_v_up: float = 0.0
    std_v_e: float = 0.0
    std_v_n: float = 0.0
    std_v_up: float = 0.0
    max_speed_2d: float = 0.0
    max_speed_3d: float = 0.0
    mean_speed_2d: float = 0.0
    mean_speed_3d: float = 0.0
    rows_analyzed: int = 0
    max_height_4th_diff: float = 0.0  # Новый атрибут
    height_4th_diff_array: np.ndarray = None


@dataclass
class VelocityAnalysisResult:
    """
    Полный результат анализа одного VEL файла.
    
    Объединяет исходные данные и вычисленную статистику.
    Используется как единый контейнер для передачи между компонентами.
    
    Attributes:
        filename: Имя файла
        filepath: Путь к файлу
        data: Исходные данные (VelocityData)
        statistics: Вычисленная статистика (VelocityStatistics)
        timestamp: Время выполнения анализа
        success: Флаг успешности анализа
        error: Сообщение об ошибке (если success=False)
    """
    filename: str
    filepath: str
    data: VelocityData
    statistics: VelocityStatistics
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = True
    error: Optional[str] = None


class VelocityAnalyzer:
    """
    Анализатор VEL файлов с поддержкой пакетной обработки.
    
    Реализует полный цикл обработки:
        1. Поиск VEL файлов в директории (с приоритетом L1/IO)
        2. Парсинг каждого файла в структурированные данные
        3. Расчёт статистических показателей, включая max 4th diff по высоте
        4. Кэширование результатов
        5. Экспорт в CSV
    
    Класс не содержит UI-кода и может использоваться в любом окружении.
    """
    
    def __init__(self):
        """Инициализирует анализатор с пустым кэшем результатов."""
        self._results: Dict[str, VelocityAnalysisResult] = {}
    
    def find_vel_files(self, results_dir: str) -> List[str]:
        """
        Находит все VEL файлы в директории с приоритезацией.
        
        Алгоритм приоритета:
            1. Файлы с 'L1' или 'IO' в имени (обычно основные результаты)
            2. Остальные VEL файлы в алфавитном порядке
        
        Args:
            results_dir: Путь к директории для поиска
            
        Returns:
            Список путей к VEL файлам, отсортированный по приоритету
        """
        vel_files = []
        if os.path.exists(results_dir):
            for file in os.listdir(results_dir):
                if file.endswith('.VEL'):
                    vel_files.append(os.path.join(results_dir, file))
        
        # Приоритезация файлов
        priority = []
        others = []
        for f in vel_files:
            name = os.path.basename(f)
            if 'L1' in name or 'IO' in name:
                priority.append(f)
            else:
                others.append(f)
        
        return priority + others
    
    def parse_file(self, filepath: str) -> Optional[VelocityData]:
        """
        Парсит VEL файл и возвращает структурированные данные.
        
        Формат файла:
            - Первые 2 строки: заголовки (пропускаются)
            - Последующие строки: данные с разделителями-пробелами
            - Индексы колонок: 0(время), 3(высота Hei), 5(E), 6(N), 7(UP)
        
        Args:
            filepath: Путь к VEL файлу
            
        Returns:
            VelocityData с numpy массивами или None при ошибке парсинга
        """
        filename = os.path.basename(filepath)
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            if len(lines) < 3:
                return None
            
            time_data = []
            height_data = []  # Для высоты
            v_e_data = []
            v_n_data = []
            v_up_data = []
            
            # Пропускаем заголовки (первые 2 строки)
            for line in lines[2:]:
                line = line.strip()
                if not line:
                    continue
                
                parts = line.split()
                # Проверяем, что достаточно колонок для всех данных (минимум 8 для высоты и скоростей)
                if len(parts) >= 8:  
                    try:
                        time_data.append(float(parts[0]))
                        height_data.append(float(parts[3]))  # Высота (индекс 3)
                        v_e_data.append(float(parts[5]))
                        v_n_data.append(float(parts[6]))
                        v_up_data.append(float(parts[7]))
                    except (ValueError, IndexError) as e:
                        # Пропускаем строки с ошибками парсинга
                        # print(f"Ошибка парсинга строки в {filename}: {e}")
                        continue
            
            if not time_data:
                return None
            
            return VelocityData(
                filename=filename,
                filepath=filepath,
                time=np.array(time_data),
                height=np.array(height_data),  # Сохраняем высоту
                v_e=np.array(v_e_data),
                v_n=np.array(v_n_data),
                v_up=np.array(v_up_data),
                rows=len(time_data),
                time_span=(time_data[0], time_data[-1])
            )
            
        except Exception as e:
            print(f"Ошибка парсинга {filename}: {e}")
            return None
    
    def _calculate_4th_diff(self, data: np.ndarray) -> np.ndarray:
        """
        Вычисляет 4-ю разность для входного массива и возвращает ВСЕ значения.

        Args:
            data: Входной numpy массив (например, высота)

        Returns:
            Массив той же длины, что и входной, содержащий 4-ю разность.
            Возвращает пустой массив, если данных недостаточно.
        """
        if data is None or len(data) < 5:
            return np.array([])

        try:
            # Вычисляем 4-ю разность. prepend используется для сохранения длины.
            fourth_diff = np.diff(data, n=4, prepend=data[:4])
            return fourth_diff
        except Exception as e:
            print(f"Ошибка расчета 4-й разности: {e}")
            return np.array([])
    
    def calculate_statistics(self, data: VelocityData) -> VelocityStatistics:
        """
        Рассчитывает статистику на основе данных скоростей.
        
        Вычисляет:
            - Максимальные абсолютные скорости по осям
            - Средние значения
            - Стандартные отклонения
            - Горизонтальные (2D) и полные (3D) скорости
            - **Максимальную 4-ю разность высоты**
        
        Args:
            data: Структурированные данные из parse_file
            
        Returns:
            VelocityStatistics с заполненными полями
        """
        stats = VelocityStatistics(rows_analyzed=data.rows)
        
        if data.rows == 0:
            return stats
        
        # Скорости по осям (абсолютные значения для максимумов)
        stats.max_v_e = float(np.max(np.abs(data.v_e)))
        stats.max_v_n = float(np.max(np.abs(data.v_n)))
        stats.max_v_up = float(np.max(np.abs(data.v_up)))
        
        stats.mean_v_e = float(np.mean(data.v_e))
        stats.mean_v_n = float(np.mean(data.v_n))
        stats.mean_v_up = float(np.mean(data.v_up))
        
        stats.std_v_e = float(np.std(data.v_e))
        stats.std_v_n = float(np.std(data.v_n))
        stats.std_v_up = float(np.std(data.v_up))
        
        # 2D и 3D скорости
        speed_2d = np.sqrt(data.v_e**2 + data.v_n**2)
        speed_3d = np.sqrt(data.v_e**2 + data.v_n**2 + data.v_up**2)
        
        stats.max_speed_2d = float(np.max(speed_2d))
        stats.max_speed_3d = float(np.max(speed_3d))
        stats.mean_speed_2d = float(np.mean(speed_2d))
        stats.mean_speed_3d = float(np.mean(speed_3d))
        
        # === НОВЫЙ РАСЧЕТ: Максимальная 4-я разность высоты ===
        # Стало
        stats.height_4th_diff_array = self._calculate_4th_diff(data.height)
        # Если нужно оставить совместимость со старым кодом, можно также посчитать и максимум
        if stats.height_4th_diff_array is not None and len(stats.height_4th_diff_array) > 0:
            stats.max_height_4th_diff = float(np.max(np.abs(stats.height_4th_diff_array)))
        else:
            stats.max_height_4th_diff = 0.0
        
        return stats
    
    def analyze_file(self, filepath: str) -> Optional[VelocityAnalysisResult]:
        """
        Выполняет полный анализ одного VEL файла.
        
        Последовательность:
            1. Парсинг файла в VelocityData
            2. Расчёт статистики на основе данных
            3. Сохранение результата во внутреннем кэше
        
        Args:
            filepath: Путь к VEL файлу
            
        Returns:
            VelocityAnalysisResult или None при ошибке парсинга
        """
        data = self.parse_file(filepath)
        if not data:
            return None
        
        stats = self.calculate_statistics(data)
        
        result = VelocityAnalysisResult(
            filename=data.filename,
            filepath=filepath,
            data=data,
            statistics=stats
        )
        
        self._results[data.filename] = result
        return result
    
    def analyze_all(self, results_dir: str) -> Dict[str, VelocityAnalysisResult]:
        """
        Анализирует все VEL файлы в указанной директории.
        
        Args:
            results_dir: Путь к директории с VEL файлами
            
        Returns:
            Словарь {имя_файла: результат} для успешно обработанных файлов
        """
        self._results.clear()
        
        for filepath in self.find_vel_files(results_dir):
            result = self.analyze_file(filepath)
            if result:
                self._results[result.filename] = result
        
        return self.get_results()
    
    def get_results(self) -> Dict[str, VelocityAnalysisResult]:
        """
        Возвращает копию всех результатов анализа.
        
        Returns:
            Словарь с результатами последнего вызова analyze_all()
        """
        return self._results.copy()
    
    def get_summary_statistics(self) -> Dict[str, Any]:
        """
        Возвращает сводную статистику по всем проанализированным файлам.
        
        Содержит:
            - Общее количество файлов
            - Список имён файлов
            - Максимальные скорости по осям среди всех файлов
            - Максимальные 2D и 3D скорости
            - **Максимальную 4-ю разность высоты среди всех файлов**
            
        Returns:
            Словарь со сводной статистикой или {} если нет результатов
        """
        if not self._results:
            return {}
        
        summary = {
            'total_files': len(self._results),
            'files': [],
            'max_velocities': {
                'v_e': 0.0, 'v_n': 0.0, 'v_up': 0.0
            },
            'max_speeds': {
                '2d': 0.0, '3d': 0.0
            },
            'max_height_4th_diff': 0.0  # Новый глобальный максимум
        }
        
        for filename, result in self._results.items():
            summary['files'].append(filename)
            stats = result.statistics
            
            # Поиск глобальных максимумов
            summary['max_velocities']['v_e'] = max(
                summary['max_velocities']['v_e'], 
                stats.max_v_e
            )
            summary['max_velocities']['v_n'] = max(
                summary['max_velocities']['v_n'], 
                stats.max_v_n
            )
            summary['max_velocities']['v_up'] = max(
                summary['max_velocities']['v_up'], 
                stats.max_v_up
            )
            summary['max_speeds']['2d'] = max(
                summary['max_speeds']['2d'], 
                stats.max_speed_2d
            )
            summary['max_speeds']['3d'] = max(
                summary['max_speeds']['3d'], 
                stats.max_speed_3d
            )
            # Новый глобальный максимум
            summary['max_height_4th_diff'] = max(
                summary['max_height_4th_diff'],
                stats.max_height_4th_diff
            )
        
        return summary
    
    def export_to_csv(self, output_file: str) -> bool:
        """
        Экспортирует все результаты анализа в CSV файл.
        
        Формат CSV содержит по одной строке на каждый файл со всеми
        статистическими показателями, включая новый.
        
        Args:
            output_file: Путь для сохранения CSV файла
            
        Returns:
            True при успешном экспорте, False при ошибке или отсутствии данных
        """
        if not self._results:
            return False
        
        try:
            export_data = []
            for filename, result in self._results.items():
                row = {
                    'Filename': filename,
                    'Rows': result.data.rows,
                    'Duration_sec': result.data.duration,
                    'Max_V_E': result.statistics.max_v_e,
                    'Max_V_N': result.statistics.max_v_n,
                    'Max_V_UP': result.statistics.max_v_up,
                    'Mean_V_E': result.statistics.mean_v_e,
                    'Mean_V_N': result.statistics.mean_v_n,
                    'Mean_V_UP': result.statistics.mean_v_up,
                    'Std_V_E': result.statistics.std_v_e,
                    'Std_V_N': result.statistics.std_v_n,
                    'Std_V_UP': result.statistics.std_v_up,
                    'Max_Speed_2D': result.statistics.max_speed_2d,
                    'Max_Speed_3D': result.statistics.max_speed_3d,
                    'Max_Height_4th_Diff': result.statistics.max_height_4th_diff,  # Новая колонка
                }
                export_data.append(row)
            
            df = pd.DataFrame(export_data)
            df.to_csv(output_file, index=False, encoding='utf-8')
            return True
            
        except Exception as e:
            print(f"Ошибка экспорта: {e}")
            return False