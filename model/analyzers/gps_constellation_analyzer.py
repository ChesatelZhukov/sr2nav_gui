#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Анализатор GPS созвездия для обработки SVs файлов.

Выполняет детальный анализ видимости и стабильности спутников GPS,
рассчитывает метрики качества для оценки пригодности данных для RTK.

Основные возможности:
    - Парсинг SVs файлов с адаптивным сэмплированием для больших объёмов
    - Детекция интервалов видимости каждого спутника
    - Расчёт статистик: длительность, частота пропаданий, стабильность
    - Оценка качества сигнала для RTK с цветовым кодированием
    - Экспорт результатов в CSV

Алгоритм работы:
    1. Парсинг файла (оптимизированный для больших файлов >10 MB)
    2. Для каждого спутника из 32:
       - Построение маски видимости (сигнал > 0)
       - Детекция сырых интервалов видимости (raw_intervals)
       - Объединение микро-пропаданий для визуализации (merged_intervals)
       - Расчёт пиковой частоты по сырым интервалам
       - Классификация стабильности для RTK
    3. Формирование сводного отчёта с оценкой качества
"""
import os
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from bisect import bisect_right


@dataclass
class SatelliteInterval:
    """
    Интервал непрерывной видимости спутника.
    
    Attributes:
        start: Начало интервала (секунды от начала суток)
        end: Конец интервала (секунды от начала суток)
        duration: Длительность интервала (вычисляется, если не указана)
    
    Note:
        Используется как для сырых (raw_intervals), так и для
        объединённых (merged_intervals) интервалов.
    """
    start: float
    end: float
    duration: float = None
    
    def __post_init__(self):
        if self.duration is None:
            self.duration = self.end - self.start


@dataclass
class SatelliteStatistics:
    """
    Комплексная статистика по одному спутнику.
    
    Содержит как базовые метрики (длительность, количество интервалов),
    так и специализированные показатели для оценки RTK качества.
    
    Attributes:
        prn: Идентификатор спутника (G01...G32)
        num_intervals: Количество объединённых интервалов (для графика)
        total_visible_time: Суммарное время видимости (сек)
        avg_duration: Средняя длительность интервала (сек)
        max_duration: Максимальная длительность интервала (сек)
        min_duration: Минимальная длительность интервала (сек)
        visibility_percent: Процент времени видимости от общего
        is_visible: Флаг наличия хотя бы одного интервала
        intervals: Объединённые интервалы (для отображения)
        raw_intervals: Сырые интервалы (для расчёта частоты)
        sampling_rate_hz: Реальная частота дискретизации
        
        peak_intervals_per_minute: Максимальная частота в окне 10 мин
        peak_intervals_per_minute_norm: Нормализованная к 10 Гц частота
        peak_window_center: Центр окна с максимальной частотой (сек)
        peak_window_count: Количество интервалов в пиковом окне
    """
    prn: str
    num_intervals: int = 0
    total_visible_time: float = 0.0
    avg_duration: float = 0.0
    max_duration: float = 0.0
    min_duration: float = 0.0
    visibility_percent: float = 0.0
    is_visible: bool = False
    intervals: List[SatelliteInterval] = field(default_factory=list)
    raw_intervals: List[SatelliteInterval] = field(default_factory=list)
    sampling_rate_hz: float = 10.0
    
    # Пиковые метрики (рассчитываются отдельно)
    peak_intervals_per_minute: float = 0.0
    peak_intervals_per_minute_norm: float = 0.0
    peak_window_center: float = 0.0
    peak_window_count: int = 0
    
    @property
    def intervals_per_minute(self) -> float:
        """
        Пиковая нормализованная частота появления интервалов.
        
        Для невидимых спутников возвращает float('inf') как маркер отсутствия.
        Если спутник виден одним непрерывным интервалом, частота = 0.0.
        
        Returns:
            float: Количество интервалов в минуту (нормализованное к 10 Гц)
        """
        if not self.is_visible:
            return float('inf')
        
        # Если спутник виден одним непрерывным интервалом - частота 0
        if len(self.raw_intervals) <= 1:
            return 0.0
        
        if self.peak_intervals_per_minute_norm > 0:
            return self.peak_intervals_per_minute_norm
        
        # Fallback-расчёт (используется при отсутствии пиковых метрик)
        raw_ipm = (len(self.raw_intervals) / self.total_visible_time) * 60
        return raw_ipm * (10.0 / self.sampling_rate_hz)
    
    @property
    def peak_description(self) -> str:
        """
        Человекочитаемое описание пиковой нагрузки.
        
        Формирует строку вида:
        "пик 15 инт за 10 мин (1.50/мин) в районе 2.5 ч"
        """
        if self.peak_window_count <= 1:
            return "нет пиковых нагрузок"
        
        minutes = self.peak_window_center / 60
        hours = minutes / 60
        
        if hours >= 1:
            time_str = f"{hours:.1f} ч"
        else:
            time_str = f"{minutes:.0f} мин"
        
        return (f"пик {self.peak_window_count} инт за 10 мин "
                f"({self.peak_intervals_per_minute:.2f}/мин) "
                f"в районе {time_str}")
    
    @property
    def stability_index(self) -> float:
        """
        Индекс стабильности спутника для RTK (0.0 - 1.0).
        
        Критерии для RTK (очень строгие):
            - 1.0: непрерывный трек
            - 0.8: 1 пропадание за 100 мин (0.01/мин)
            - 0.6: 1 пропадание за 50 мин (0.02/мин)
            - 0.3: 1 пропадание за 20 мин (0.05/мин)
            - 0.1: хуже
        """
        if not self.is_visible:
            return 0.0
        if len(self.raw_intervals) <= 1:
            return 1.0  # Только непрерывный трек
        
        ipm = self.intervals_per_minute
        
        # Жёсткие критерии для RTK
        if ipm == 0.0:
            return 1.0
        elif ipm <= 0.01:   # 1 пропадание за 100 мин
            return 0.8
        elif ipm <= 0.02:   # 1 пропадание за 50 мин
            return 0.6
        elif ipm <= 0.05:   # 1 пропадание за 20 мин
            return 0.3
        else:
            return 0.1
    
    @property
    def stability_category(self) -> Tuple[str, str]:
        """
        Категория стабильности с цветовым тегом для UI.
        
        Returns:
            Tuple[описание, css_класс]: ("Отличный", "excellent")
        """
        if not self.is_visible:
            return ("Не виден", "invisible")
        
        ipm = self.intervals_per_minute
        raw_count = len(self.raw_intervals)
        
        # Эталон - только один непрерывный интервал
        if raw_count <= 1:
            return ("Эталонный", "excellent")
        
        # Жёсткая градация для RTK
        if ipm <= 0.01:
            return ("Отличный", "excellent")
        elif ipm <= 0.02:
            return ("Хороший", "good")
        elif ipm <= 0.05:
            return ("Удовлетворительный", "moderate")
        elif ipm <= 0.1:
            return ("Плохой", "bad")
        else:
            return ("Непригодный", "critical")
    
    @property
    def warning_message(self) -> Optional[str]:
        """
        Предупреждение для RTK с конкретными цифрами.
        
        Возвращает сообщение только для спутников с частотой > 0.01/мин.
        """
        if not self.is_visible:
            return None
        
        ipm = self.intervals_per_minute
        raw_count = len(self.raw_intervals)
        
        if raw_count <= 1:
            return None
        
        if ipm > 0.1:
            return f"🚫 НЕПРИГОДНО: {ipm:.2f}/мин (>{ipm*10:.0f} пропаданий за 10 мин)"
        elif ipm > 0.05:
            return f"⚠️ КРИТИЧНО: {ipm:.2f}/мин (1 пропадание за {60/ipm:.0f} мин)"
        elif ipm > 0.02:
            return f"⚠️ ПЛОХО: {ipm:.2f}/мин (требуется постобработка)"
        elif ipm > 0.01:
            return f"ℹ️ УМЕРЕННО: {ipm:.2f}/мин (возможны сбои)"
        
        return None
    
    @property
    def is_problematic(self) -> bool:
        """
        Флаг проблемности для RTK.
        
        Спутник считается проблемным, если частота пропаданий > 0.02/мин.
        """
        if not self.is_visible:
            return False
        
        if len(self.raw_intervals) <= 1:
            return False
        
        return self.intervals_per_minute > 0.02


@dataclass
class GPSConstellationData:
    """
    Метаданные о проанализированном файле.
    
    Содержит информацию о временных рамках, дискретизации и объёме данных.
    """
    filename: str
    filepath: str
    time_range: Tuple[float, float]
    total_duration: float
    rows_original: int
    rows_sampled: int
    sampling_rate: int
    actual_sampling_interval: float
    sampling_rate_hz: float = 10.0


@dataclass
class GPSConstellationAnalysisResult:
    """
    Полный результат анализа одного SVs файла.
    
    Объединяет все данные, статистики и вычисленные метрики.
    Предоставляет свойства для быстрого доступа к проблемным
    и эталонным спутникам, а также общую оценку качества.
    """
    filename: str
    filepath: str
    data: GPSConstellationData
    satellite_stats: Dict[str, SatelliteStatistics]
    visible_satellites: int = 0
    mean_satellites: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = True
    error: Optional[str] = None
    
    @property
    def problem_satellites(self) -> List[Tuple[str, SatelliteStatistics]]:
        """Список проблемных спутников (is_problematic = True)."""
        return [(sat, stats) for sat, stats in self.satellite_stats.items() 
                if stats.is_problematic]
    
    @property
    def critical_satellites(self) -> List[Tuple[str, SatelliteStatistics]]:
        """Критически нестабильные спутники (>1 интервала в минуту)."""
        return [(sat, stats) for sat, stats in self.satellite_stats.items() 
                if stats.intervals_per_minute > 1.0]
    
    @property
    def excellent_satellites(self) -> List[Tuple[str, SatelliteStatistics]]:
        """Эталонные спутники (один интервал, видимость >50%)."""
        return [(sat, stats) for sat, stats in self.satellite_stats.items() 
                if stats.num_intervals == 1 and stats.visibility_percent > 50]
    
    @property
    def overall_quality_score(self) -> float:
        """
        Общая оценка качества данных для RTK (0-100).
        
        Алгоритм:
            1. Базовый балл от среднего количества спутников
            2. Штраф за нестабильность (взвешенный по проблемным)
        """
        if self.visible_satellites == 0:
            return 0.0
        
        # Базовый балл от количества спутников (макс при 10+)
        base_score = min(100, (self.mean_satellites / 10) * 100)
        
        # Расчёт штрафов за нестабильность
        penalty = 0
        problem_count = 0
        
        for _, stats in self.satellite_stats.items():
            if not stats.is_visible:
                continue
            
            ipm = stats.intervals_per_minute
            
            if ipm > 0.1:
                penalty += 50
                problem_count += 1
            elif ipm > 0.05:
                penalty += 30
                problem_count += 1
            elif ipm > 0.02:
                penalty += 20
                problem_count += 1
            elif ipm > 0.01:
                penalty += 10
                problem_count += 1
        
        if problem_count > 0:
            penalty = penalty / problem_count
        
        final_score = max(0, base_score - penalty)
        return round(final_score, 1)

    @property
    def overall_quality_category(self) -> Tuple[str, str]:
        """
        Категория качества с цветовым кодом для UI.
        
        Returns:
            Tuple[описание, hex_цвет]: ("Идеально для RTK", "#198754")
        """
        score = self.overall_quality_score
        if score >= 90:
            return ("Идеально для RTK", "#198754")
        elif score >= 75:
            return ("Хорошо для RTK", "#0d6efd")
        elif score >= 50:
            return ("Удовлетворительно", "#fd7e14")
        elif score >= 25:
            return ("Плохо для RTK", "#dc3545")
        else:
            return ("Непригодно для RTK", "#8b0000")
    
    @property
    def summary_report(self) -> Dict[str, Any]:
        """
        Краткий отчёт в формате словаря для экспорта.
        
        Содержит ключевые метрики, удобные для отображения в UI
        или сохранения в CSV.
        """
        return {
            'filename': self.filename,
            'quality_score': self.overall_quality_score,
            'quality_category': self.overall_quality_category[0],
            'total_visible': self.visible_satellites,
            'problematic_count': len(self.problem_satellites),
            'critical_count': len(self.critical_satellites),
            'excellent_count': len(self.excellent_satellites),
            'mean_satellites': round(self.mean_satellites, 1),
            'duration_minutes': round(self.data.total_duration / 60, 1),
            'duration_hours': round(self.data.total_duration / 3600, 2),
            'sampling_rate_hz': round(1.0 / self.data.actual_sampling_interval, 1),
            'needs_attention': len(self.problem_satellites) > self.visible_satellites * 0.3
        }


class GPSConstellationAnalyzer:
    """
    Анализатор GPS созвездия для SVs файлов.
    
    Реализует полный цикл анализа:
        - Поиск SVs файлов в директории
        - Оптимизированный парсинг (адаптивное сэмплирование)
        - Детекция интервалов видимости для всех 32 спутников
        - Расчёт пиковых частот с использованием скользящего окна
        - Оценка качества для RTK
    
    Ключевые особенности реализации:
        - Два типа интервалов: raw (для расчётов) и merged (для графиков)
        - Пиковая частота рассчитывается по сырым интервалам
        - Безопасная обработка граничных индексов в detect_gaps
        - Для невидимых спутников intervals_per_minute = inf
    """
    
    ALL_SATELLITES = [f'G{i:02d}' for i in range(1, 33)]
    
    def __init__(self, 
                 target_points: int = 5000,
                 min_gap_duration: float = 10,
                 merge_gap: float = 10.0):
        """
        Инициализация анализатора с параметрами обработки.
        
        Args:
            target_points: Целевое количество точек после сэмплирования
                          (для больших файлов >10 MB)
            min_gap_duration: Минимальная длительность пропадания сигнала (сек)
                             для разделения интервалов
            merge_gap: Интервал для объединения близких пропаданий (сек)
                      Разрывы меньше этого значения объединяются
        """
        self.target_points = target_points
        self.min_gap_duration = min_gap_duration
        self.merge_gap = merge_gap
        self._results: Dict[str, GPSConstellationAnalysisResult] = {}
    
    def find_sv_files(self, results_dir: str) -> List[str]:
        """
        Находит все SVs файлы в указанной директории.
        
        Args:
            results_dir: Путь к директории с результатами
            
        Returns:
            Список полных путей к файлам, соответствующим шаблону:
            - расширение .SVs
            - или содержащим 'SV' в имени (регистронезависимо)
        """
        sv_files = []
        if os.path.exists(results_dir):
            for file in os.listdir(results_dir):
                if file.endswith('.SVs') or 'SV' in file.upper():
                    sv_files.append(os.path.join(results_dir, file))
        return sv_files
    
    def parse_file_optimized(self, filepath: str) -> Optional[pd.DataFrame]:
        """
        Оптимизированный парсер SVs файлов с адаптивным сэмплированием.
        
        Для файлов >10 MB использует чанковое чтение с прореживанием,
        для маленьких файлов — полную загрузку в память.
        
        Args:
            filepath: Путь к SVs файлу
            
        Returns:
            DataFrame с колонками: DayTime, DateTime, G01...G32
            или None при ошибке парсинга
        """
        filename = os.path.basename(filepath)
        
        try:
            # Чтение заголовка для определения структуры
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                header_line = f.readline().strip()
                first_data = f.readline().strip()
                second_data = f.readline().strip()
            
            headers = header_line.split()
            if len(headers) < 3:
                return None
            
            # Определение колонок спутников
            sat_columns = []
            for h in headers:
                if h.startswith('G') and h[1:].isdigit():
                    sat_columns.append(h)
            
            if not sat_columns:
                sat_columns = self.ALL_SATELLITES.copy()
            
            # Определение реального интервала дискретизации
            first_parts = first_data.split()
            second_parts = second_data.split()
            
            actual_interval = 0.1
            sampling_rate_hz = 10.0
            
            if len(first_parts) >= 1 and len(second_parts) >= 1:
                try:
                    t1 = float(first_parts[0])
                    t2 = float(second_parts[0])
                    actual_interval = t2 - t1
                    if actual_interval > 0:
                        sampling_rate_hz = 1.0 / actual_interval
                except (ValueError, IndexError):
                    pass
            
            # Выбор стратегии парсинга в зависимости от размера
            file_size = os.path.getsize(filepath)
            
            if file_size > 10 * 1024 * 1024:  # > 10 MB
                df = self._parse_large_file_chunked(
                    filepath, sat_columns, actual_interval
                )
            else:
                df = self._parse_small_file_full(
                    filepath, sat_columns, actual_interval
                )
            
            if df is not None:
                df.attrs['sampling_rate_hz'] = sampling_rate_hz
            
            return df
                
        except Exception as e:
            print(f"Ошибка парсинга {filename}: {e}")
            return None
    
    def _parse_large_file_chunked(self, filepath: str, sat_columns: List[str], 
                                actual_interval: float) -> Optional[pd.DataFrame]:
        """
        Парсинг больших файлов (>10 MB) с адаптивным прореживанием.
        
        Читает файл построчно, пропуская строки с шагом,
        рассчитанным для достижения target_points.
        
        Returns:
            DataFrame с сэмплированными данными
        """
        filename = os.path.basename(filepath)
        
        try:
            # Определение общего количества строк
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                header_line = f.readline().strip()
                headers = header_line.split()
                
                sat_positions = {}
                for idx, col_name in enumerate(headers):
                    if col_name.startswith('G') and col_name[1:].isdigit():
                        sat_positions[idx] = col_name
                
                total_lines = sum(1 for _ in f)
            
            if total_lines <= 0:
                return None
            
            # Расчёт шага прореживания
            step = max(1, total_lines // self.target_points)
            
            data_rows = []
            time_values = []
            
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                f.readline()  # пропускаем заголовок
                
                line_count = 0
                for line in f:
                    line_count += 1
                    
                    # Пропускаем строки согласно шагу
                    if line_count % step != 0:
                        continue
                    
                    line = line.strip()
                    if not line:
                        continue
                    
                    parts = line.split()
                    if len(parts) < 2:
                        continue
                    
                    try:
                        time_val = float(parts[0])
                        time_values.append(time_val)
                        
                        row = {'DayTime': time_val, 'DateTime': parts[1]}
                        
                        # Инициализация всех спутников нулями
                        for sat in self.ALL_SATELLITES:
                            row[sat] = 0
                        
                        # Заполнение реальных значений
                        for pos, sat_name in sat_positions.items():
                            if pos < len(parts):
                                try:
                                    val = int(float(parts[pos]))
                                    row[sat_name] = val
                                except (ValueError, IndexError):
                                    row[sat_name] = 0
                        
                        data_rows.append(row)
                        
                    except (ValueError, IndexError):
                        continue
            
            if not data_rows:
                return None
            
            df = pd.DataFrame(data_rows)
            
            # Сохранение метаданных
            df.attrs['actual_interval'] = actual_interval
            df.attrs['step'] = step
            df.attrs['total_lines'] = total_lines
            
            return df
            
        except Exception as e:
            print(f"Ошибка chunked парсинга {filename}: {e}")
            return None
    
    def _parse_small_file_full(self, filepath: str, sat_columns: List[str],
                                actual_interval: float) -> Optional[pd.DataFrame]:
        """
        Парсинг небольших файлов полной загрузкой в pandas.
        
        Args:
            filepath: Путь к файлу
            sat_columns: Список колонок спутников
            actual_interval: Реальный интервал дискретизации
            
        Returns:
            DataFrame с полными данными
        """
        filename = os.path.basename(filepath)
        
        try:
            # Чтение заголовка для проверки
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                header_line = f.readline().strip()
                headers = header_line.split()
            
            # Загрузка всего файла
            df = pd.read_csv(
                filepath,
                sep=r'\s+',
                header=0,
                engine='python',
                on_bad_lines='skip'
            )
            
            if len(df) < 2:
                return None
            
            # Гарантированное наличие всех спутниковых колонок
            for sat in self.ALL_SATELLITES:
                if sat not in df.columns:
                    df[sat] = 0
            
            # Упорядочивание колонок
            columns_order = ['DayTime', 'DateTime'] + self.ALL_SATELLITES
            existing_columns = [col for col in columns_order if col in df.columns]
            df = df[existing_columns]
            
            df.attrs['actual_interval'] = actual_interval
            return df
            
        except Exception as e:
            print(f"Ошибка полного парсинга {filename}: {e}")
            return None
    
    def detect_gaps(self, visibility: np.ndarray, time_seconds: np.ndarray) -> List[SatelliteInterval]:
        """
        Детектирует интервалы видимости спутника по бинарной маске.
        
        Алгоритм:
            1. Вычисляет разность маски для поиска переходов
            2. Находит начала (0→1) и концы (1→0) интервалов
            3. Корректирует границы с учётом первого/последнего элемента
            4. Формирует интервалы с безопасной проверкой индексов
        
        Args:
            visibility: Булева маска видимости (True где сигнал >0)
            time_seconds: Массив временных меток
            
        Returns:
            Список интервалов видимости (сырых, без объединения)
            
        Note:
            Метод гарантирует, что индексы start_idx и end_idx
            всегда находятся в допустимых пределах массива.
        """
        if not np.any(visibility):
            return []
        
        # Поиск переходов
        diff = np.diff(visibility.astype(int))
        starts = np.where(diff == 1)[0] + 1
        ends = np.where(diff == -1)[0] + 1
        
        # Корректировка границ с учётом начала/конца
        if visibility[0]:
            starts = np.insert(starts, 0, 0)
        if visibility[-1]:
            ends = np.append(ends, len(visibility))
        
        intervals = []
        n_times = len(time_seconds)
        
        for i in range(min(len(starts), len(ends))):
            start_idx = starts[i]
            # Безопасное ограничение конечного индекса
            end_idx = min(ends[i] - 1, n_times - 1)
            
            # Проверка валидности индексов
            if 0 <= start_idx < n_times and 0 <= end_idx < n_times and start_idx <= end_idx:
                intervals.append(SatelliteInterval(
                    start=float(time_seconds[start_idx]),
                    end=float(time_seconds[end_idx])
                ))
        
        return intervals
    
    def merge_intervals_by_gap(self, intervals: List[SatelliteInterval], gap_threshold: float) -> List[SatelliteInterval]:
        """
        Объединяет интервалы, если разрыв между ними меньше порога.
        
        Используется для двух целей:
            1. Объединение микро-пропаданий (min_gap_duration)
            2. Финальное объединение близких интервалов (merge_gap)
        
        Args:
            intervals: Список интервалов (отсортированных или нет)
            gap_threshold: Максимальный разрыв для объединения (сек)
            
        Returns:
            Новый список объединённых интервалов
        """
        if not intervals:
            return []
        
        # Сортировка по началу
        sorted_int = sorted(intervals, key=lambda x: x.start)
        merged = []
        current = sorted_int[0]
        
        for interval in sorted_int[1:]:
            gap = interval.start - current.end
            
            if gap <= gap_threshold:
                # Объединение интервалов
                current = SatelliteInterval(
                    start=current.start,
                    end=max(current.end, interval.end),
                    duration=max(current.end, interval.end) - current.start
                )
            else:
                merged.append(current)
                current = interval
        
        merged.append(current)
        return merged
    
    def merge_close_intervals(self, intervals: List[SatelliteInterval]) -> List[SatelliteInterval]:
        """Обёртка для объединения с параметром merge_gap."""
        return self.merge_intervals_by_gap(intervals, self.merge_gap)
    
    def calculate_satellite_stats(self, intervals: List[SatelliteInterval],
                                   total_duration: float, prn: str,
                                   sampling_rate_hz: float) -> SatelliteStatistics:
        """Рассчитывает базовую статистику для спутника (без пиковой частоты)."""
        stats = SatelliteStatistics(
            prn=prn,
            num_intervals=len(intervals),
            intervals=intervals,
            raw_intervals=[],  # будет заполнено отдельно
            sampling_rate_hz=sampling_rate_hz
        )
        
        if not intervals:
            return stats
        
        durations = [i.duration for i in intervals]
        stats.total_visible_time = sum(durations)
        stats.avg_duration = np.mean(durations) if durations else 0
        stats.max_duration = max(durations) if durations else 0
        stats.min_duration = min(durations) if durations else 0
        stats.visibility_percent = (stats.total_visible_time / total_duration * 100) if total_duration > 0 else 0
        stats.is_visible = stats.total_visible_time > 0
        
        return stats
    
    def analyze_file(self, filepath: str) -> Optional[GPSConstellationAnalysisResult]:
        """
        Выполняет полный анализ одного SVs файла.
        
        Алгоритм работы:
            1. Парсинг файла с адаптивным сэмплированием
            2. Для каждого из 32 спутников:
               a. Получение сырых интервалов (raw_intervals)
               b. Объединение микро-пропаданий для визуализации
               c. Расчёт пиковой частоты по сырым интервалам
               d. Сохранение обоих типов интервалов
            3. Расчёт общей статистики по файлу
            4. Формирование результата
        
        Args:
            filepath: Путь к SVs файлу
            
        Returns:
            GPSConstellationAnalysisResult или None при ошибке
        """
        filename = os.path.basename(filepath)
        
        # Шаг 1: Парсинг файла
        df = self.parse_file_optimized(filepath)
        if df is None or len(df) < 2:
            self._results.pop(filename, None)
            return None
        
        # Шаг 2: Извлечение временных рядов
        time_seconds = df['DayTime'].values
        total_duration = time_seconds[-1] - time_seconds[0]
        
        actual_interval = df.attrs.get('actual_interval', 0.1)
        if actual_interval <= 0:
            actual_interval = 0.1
        
        sampling_rate_hz = 1.0 / actual_interval
        sampling_rate_hz = min(max(sampling_rate_hz, 0.1), 100.0)
        
        # Шаг 3: Анализ каждого спутника
        satellite_stats = {}
        visible_count = 0
        total_sat_seconds = 0.0
        
        for sat in self.ALL_SATELLITES:
            # Проверка наличия колонки
            if sat not in df.columns:
                satellite_stats[sat] = SatelliteStatistics(
                    prn=sat,
                    sampling_rate_hz=sampling_rate_hz,
                    is_visible=False
                )
                continue
            
            # Маска видимости
            visibility = df[sat].values > 0
            
            if not np.any(visibility):
                satellite_stats[sat] = SatelliteStatistics(
                    prn=sat,
                    sampling_rate_hz=sampling_rate_hz,
                    is_visible=False
                )
                continue
            
            # Два типа интервалов:
            # - raw_intervals: сырые, для расчёта частоты
            # - merged_intervals: объединённые, для отображения
            raw_intervals = self.detect_gaps(visibility, time_seconds)
            
            # Объединение микро-пропаданий
            merged_intervals = self.merge_intervals_by_gap(raw_intervals, self.min_gap_duration)
            final_intervals = self.merge_close_intervals(merged_intervals)
            
            # Базовая статистика
            stats = self._calculate_basic_stats(
                final_intervals, 
                total_duration, 
                sat, 
                sampling_rate_hz
            )
            
            # Сохраняем сырые интервалы
            stats.raw_intervals = raw_intervals
            
            # Расчёт пиковой частоты по сырым интервалам
            if raw_intervals and len(raw_intervals) > 1:
                # Извлечение начал интервалов
                start_times = []
                for interval in raw_intervals:
                    if hasattr(interval, 'get'):
                        start_times.append(interval.get('start', 0))
                    else:
                        start_times.append(interval.start)
                
                start_times = np.array(sorted(start_times))
                
                # Скользящее окно 10 минут (600 секунд)
                WINDOW_SECONDS = 600
                WINDOW_MINUTES = 10.0
                
                max_intervals_in_window = 0
                optimal_window_center = start_times[0]
                
                for center_time in start_times:
                    window_start = center_time - WINDOW_SECONDS/2
                    window_end = center_time + WINDOW_SECONDS/2
                    
                    count = np.sum(
                        (start_times >= window_start) & 
                        (start_times <= window_end)
                    )
                    
                    if count > max_intervals_in_window:
                        max_intervals_in_window = count
                        optimal_window_center = center_time
                
                # Пересчёт в интервалы/минуту
                peak_raw_ipm = max_intervals_in_window / WINDOW_MINUTES
                peak_normalized_ipm = peak_raw_ipm * (10.0 / sampling_rate_hz)
                
                stats.peak_intervals_per_minute = peak_raw_ipm
                stats.peak_intervals_per_minute_norm = peak_normalized_ipm
                stats.peak_window_center = optimal_window_center
                stats.peak_window_count = max_intervals_in_window
            else:
                # Один непрерывный интервал или нет интервалов
                stats.peak_intervals_per_minute = 0.0
                stats.peak_intervals_per_minute_norm = 0.0
                stats.peak_window_center = 0.0
                stats.peak_window_count = 1 if raw_intervals else 0
            
            satellite_stats[sat] = stats
            
            if stats.is_visible:
                visible_count += 1
                total_sat_seconds += stats.total_visible_time
        
        # Шаг 4: Общая статистика
        mean_satellites = total_sat_seconds / total_duration if total_duration > 0 else 0
        
        step = df.attrs.get('step', 1)
        total_lines = df.attrs.get('total_lines', len(df) * step)
        
        # Шаг 5: Формирование результата
        data = GPSConstellationData(
            filename=filename,
            filepath=filepath,
            time_range=(float(time_seconds[0]), float(time_seconds[-1])),
            total_duration=float(total_duration),
            rows_original=int(total_lines),
            rows_sampled=len(df),
            sampling_rate=step,
            actual_sampling_interval=float(actual_interval),
            sampling_rate_hz=float(sampling_rate_hz)
        )
        
        result = GPSConstellationAnalysisResult(
            filename=filename,
            filepath=filepath,
            data=data,
            satellite_stats=satellite_stats,
            visible_satellites=visible_count,
            mean_satellites=mean_satellites,
            timestamp=datetime.now(),
            success=True
        )
        
        self._results[filename] = result
        return result
    
    def _calculate_basic_stats(self, intervals: List[SatelliteInterval], 
                            total_duration: float, prn: str,
                            sampling_rate_hz: float) -> SatelliteStatistics:
        """
        Внутренний метод для расчёта базовой статистики спутника.
        
        Вычисляет метрики, не требующие пикового анализа:
        - Количество интервалов
        - Суммарное время видимости
        - Среднюю/макс/мин длительность
        - Процент видимости
        
        Returns:
            SatelliteStatistics с заполненными базовыми полями
        """
        stats = SatelliteStatistics(
            prn=prn,
            num_intervals=len(intervals),
            intervals=intervals,
            sampling_rate_hz=sampling_rate_hz
        )
        
        if not intervals:
            return stats
        
        durations = [i.duration for i in intervals]
        stats.total_visible_time = sum(durations)
        stats.avg_duration = float(np.mean(durations)) if durations else 0.0
        stats.max_duration = float(max(durations)) if durations else 0.0
        stats.min_duration = float(min(durations)) if durations else 0.0
        stats.visibility_percent = (stats.total_visible_time / total_duration * 100) if total_duration > 0 else 0.0
        stats.is_visible = stats.total_visible_time > 0
        
        return stats
    
    def analyze_all(self, results_dir: str) -> Dict[str, GPSConstellationAnalysisResult]:
        """
        Анализирует все SVs файлы в указанной директории.
        
        Args:
            results_dir: Путь к директории с результатами
            
        Returns:
            Словарь {имя_файла: результат} для успешно обработанных файлов
        """
        self._results.clear()
        
        for filepath in self.find_sv_files(results_dir):
            result = self.analyze_file(filepath)
            if result:
                self._results[result.filename] = result
        
        return self.get_results()
    
    def get_results(self) -> Dict[str, GPSConstellationAnalysisResult]:
        """Возвращает копию всех результатов анализа."""
        return self._results.copy()
    
    def get_visible_satellites(self, filename: str) -> List[str]:
        """Возвращает список видимых спутников для указанного файла."""
        if filename not in self._results:
            return []
        result = self._results[filename]
        return [sat for sat, stats in result.satellite_stats.items() if stats.is_visible]
    
    def get_problematic_satellites(self, filename: str) -> List[Tuple[str, SatelliteStatistics]]:
        """Возвращает список проблемных спутников."""
        if filename not in self._results:
            return []
        return self._results[filename].problem_satellites
    
    def get_quality_report(self, filename: str) -> Optional[Dict[str, Any]]:
        """Возвращает краткий отчёт о качестве для файла."""
        if filename not in self._results:
            return None
        return self._results[filename].summary_report
    
    def export_to_csv(self, output_file: str) -> bool:
        """
        Экспортирует все результаты анализа в CSV файл.
        
        Формат включает:
            - Основные метрики по каждому файлу
            - Топ-5 проблемных спутников с их характеристиками
            
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
                    'Duration_sec': result.data.total_duration,
                    'Duration_min': round(result.data.total_duration / 60, 1),
                    'Duration_hours': round(result.data.total_duration / 3600, 2),
                    'Sampling_interval_sec': result.data.actual_sampling_interval,
                    'Sampling_rate_Hz': round(result.data.sampling_rate_hz, 1),
                    'Total_Satellites': 32,
                    'Visible_Satellites': result.visible_satellites,
                    'Mean_Satellites': round(result.mean_satellites, 2),
                    'Quality_Score': result.overall_quality_score,
                    'Quality_Category': result.overall_quality_category[0],
                    'Problematic_Satellites': len(result.problem_satellites),
                    'Critical_Satellites': len(result.critical_satellites),
                    'Excellent_Satellites': len(result.excellent_satellites),
                }
                
                # Добавление топ-5 проблемных спутников
                problematic = sorted(
                    result.problem_satellites,
                    key=lambda x: x[1].intervals_per_minute,
                    reverse=True
                )[:5]
                
                for i, (sat, stats) in enumerate(problematic, 1):
                    row[f'Problem{i}_Satellite'] = sat
                    row[f'Problem{i}_Intervals'] = len(stats.raw_intervals)
                    row[f'Problem{i}_AvgDuration'] = round(stats.avg_duration, 1)
                    row[f'Problem{i}_Visibility_%'] = round(stats.visibility_percent, 1)
                    row[f'Problem{i}_IntervalsPerMinute'] = round(stats.intervals_per_minute, 3)
                    row[f'Problem{i}_Category'] = stats.stability_category[0]
                
                export_data.append(row)
            
            df = pd.DataFrame(export_data)
            df.to_csv(output_file, index=False, encoding='utf-8')
            return True
            
        except Exception as e:
            print(f"Ошибка экспорта: {e}")
            return False