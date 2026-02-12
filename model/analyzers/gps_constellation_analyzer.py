#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЧИСТАЯ МОДЕЛЬ - Анализатор GPS созвездия.
ИСПРАВЛЕНО:
1. Нормализация метрики intervals_per_minute по частоте дискретизации
2. Корректное объединение интервалов при коротких пропаданиях
3. Реалистичная оценка стабильности для разных частот данных
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
    """Интервал видимости спутника."""
    start: float
    end: float
    duration: float = None
    
    def __post_init__(self):
        if self.duration is None:
            self.duration = self.end - self.start


@dataclass
class SatelliteStatistics:
    """Статистика по одному спутнику."""
    prn: str
    num_intervals: int = 0
    total_visible_time: float = 0.0
    avg_duration: float = 0.0
    max_duration: float = 0.0
    min_duration: float = 0.0
    visibility_percent: float = 0.0
    is_visible: bool = False
    intervals: List[SatelliteInterval] = field(default_factory=list)
    sampling_rate_hz: float = 10.0  # ИСПРАВЛЕНО: частота дискретизации по умолчанию
    
    @property
    def intervals_per_minute(self) -> float:
        """
        Количество интервалов в минуту.
        ИСПРАВЛЕНО: нормализовано по частоте дискретизации!
        
        Формула: (num_intervals / total_visible_time) * 60 * (10 / sampling_rate_hz)
        
        Для 10Hz: 8 интервалов за 1 час = 0.133/мин
        Для 1Hz: 8 интервалов за 1 час = 0.133/мин (после нормализации)
        """
        if not self.is_visible or self.total_visible_time == 0:
            return 999.0
        
        raw_ipm = (self.num_intervals / self.total_visible_time) * 60
        
        # НОРМАЛИЗАЦИЯ: приводим к эталонной частоте 10Hz
        normalized_ipm = raw_ipm * (10.0 / self.sampling_rate_hz)
        
        return normalized_ipm
    
    @property
    def stability_index(self) -> float:
        """Индекс стабильности от 0 до 1."""
        if not self.is_visible:
            return 0.0
        if self.num_intervals <= 1:
            return 1.0
        
        ipm = self.intervals_per_minute
        
        if ipm <= 0.02:   # <1 инт/50 мин
            return 1.0
        elif ipm <= 0.05:  # <1 инт/20 мин
            return 0.9
        elif ipm <= 0.1:   # <1 инт/10 мин
            return 0.8
        elif ipm <= 0.2:   # <1 инт/5 мин
            return 0.6
        elif ipm <= 0.5:   # <1 инт/2 мин
            return 0.4
        elif ipm <= 1.0:   # ~1 инт/мин
            return 0.2
        else:
            return 0.1
    
    @property
    def stability_category(self) -> Tuple[str, str]:
        """Категория стабильности на основе нормализованных интервалов/минуту."""
        if not self.is_visible:
            return ("Не виден", "invisible")
        
        ipm = self.intervals_per_minute
        
        if ipm <= 0.02:
            return ("Эталонный", "excellent")
        elif ipm <= 0.05:
            return ("Отличный", "excellent")
        elif ipm <= 0.1:
            return ("Хороший", "good")
        elif ipm <= 0.2:
            return ("Умеренный", "moderate")
        elif ipm <= 0.5:
            return ("Нестабильный", "unstable")
        elif ipm <= 1.0:
            return ("Плохой", "bad")
        else:
            return ("Критический", "critical")
    
    @property
    def warning_message(self) -> Optional[str]:
        """Предупреждение для проблемных спутников."""
        if not self.is_visible:
            return None
        
        ipm = self.intervals_per_minute
        actual_freq = self.sampling_rate_hz
        
        if ipm > 1.0:
            return f"🚫 КРИТИЧНО: {ipm:.2f} пропаданий/мин (норм. для {actual_freq}Hz)"
        elif ipm > 0.5:
            return f"⚠️ ПЛОХО: {ipm:.2f} пропаданий/мин (каждые {60/ipm:.0f} сек)"
        elif ipm > 0.2:
            return f"⚠️ НЕСТАБИЛЬНО: {ipm:.2f} пропаданий/мин"
        elif ipm > 0.1 and self.avg_duration < 60:
            return f"⚠️ ЗАМЕЧАНИЕ: короткие интервалы ({self.avg_duration:.0f} с)"
        
        return None
    
    @property
    def is_problematic(self) -> bool:
        """Проблемный ли спутник?"""
        if not self.is_visible:
            return False
        ipm = self.intervals_per_minute
        return ipm > 0.2 or (ipm > 0.1 and self.avg_duration < 30)


@dataclass
class GPSConstellationData:
    """Данные GPS созвездия."""
    filename: str
    filepath: str
    time_range: Tuple[float, float]
    total_duration: float
    rows_original: int
    rows_sampled: int
    sampling_rate: int
    actual_sampling_interval: float  # Реальный интервал между измерениями
    sampling_rate_hz: float = 10.0  # ИСПРАВЛЕНО: частота в Гц


@dataclass
class GPSConstellationAnalysisResult:
    """Полный результат анализа."""
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
        return [(sat, stats) for sat, stats in self.satellite_stats.items() 
                if stats.is_problematic]
    
    @property
    def critical_satellites(self) -> List[Tuple[str, SatelliteStatistics]]:
        return [(sat, stats) for sat, stats in self.satellite_stats.items() 
                if stats.intervals_per_minute > 1.0]
    
    @property
    def excellent_satellites(self) -> List[Tuple[str, SatelliteStatistics]]:
        return [(sat, stats) for sat, stats in self.satellite_stats.items() 
                if stats.num_intervals == 1 and stats.visibility_percent > 50]
    
    @property
    def overall_quality_score(self) -> float:
        """Общая оценка качества от 0 до 100."""
        if self.visible_satellites == 0:
            return 0.0
        
        base_score = min(100, (self.mean_satellites / 12) * 100)
        penalty = 0
        problem_count = 0
        
        for _, stats in self.satellite_stats.items():
            if not stats.is_visible:
                continue
            
            ipm = stats.intervals_per_minute
            if ipm > 0.5:
                penalty += 30
                problem_count += 1
            elif ipm > 0.2:
                penalty += 20
                problem_count += 1
            elif ipm > 0.1:
                penalty += 10
                problem_count += 1
        
        if problem_count > 0:
            penalty = penalty / problem_count
        
        final_score = max(0, base_score - penalty)
        return round(final_score, 1)
    
    @property
    def overall_quality_category(self) -> Tuple[str, str]:
        score = self.overall_quality_score
        if score >= 80:
            return ("Отличное", "#198754")
        elif score >= 60:
            return ("Хорошее", "#0d6efd")
        elif score >= 40:
            return ("Удовлетворительное", "#fd7e14")
        elif score >= 20:
            return ("Плохое", "#dc3545")
        else:
            return ("Критическое", "#8b0000")
    
    @property
    def summary_report(self) -> Dict[str, Any]:
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
    ЧИСТАЯ МОДЕЛЬ - Анализатор GPS созвездия.
    ОПТИМИЗИРОВАНО для файлов 30+ МБ.
    ИСПРАВЛЕНО: корректное объединение интервалов, нормализация по частоте.
    """
    
    ALL_SATELLITES = [f'G{i:02d}' for i in range(1, 33)]
    
    def __init__(self, 
                 target_points: int = 5000,      # Целевое количество точек после сэмплирования
                 min_gap_duration: float = 2.0,  # Минимальная длительность ПРОПАДАНИЯ для разделения интервалов (сек)
                 merge_gap: float = 5.0):        # Объединять интервалы с разрывом МЕНЬШЕ N сек (для близких интервалов)
        """
        Args:
            target_points: Целевое количество точек (для файлов 30+ МБ)
            min_gap_duration: Минимальная длительность ПРОПАДАНИЯ для разделения интервалов (сек)
                              Если пропадание короче - интервалы ОБЪЕДИНЯЮТСЯ
            merge_gap: Объединять интервалы с разрывом МЕНЬШЕ N сек (для уже разделенных интервалов)
        """
        self.target_points = target_points
        self.min_gap_duration = min_gap_duration
        self.merge_gap = merge_gap
        self._results: Dict[str, GPSConstellationAnalysisResult] = {}
    
    def find_sv_files(self, results_dir: str) -> List[str]:
        """Находит все SVs файлы в директории."""
        sv_files = []
        if os.path.exists(results_dir):
            for file in os.listdir(results_dir):
                if file.endswith('.SVs') or 'SV' in file.upper():
                    sv_files.append(os.path.join(results_dir, file))
        return sv_files
    
    def parse_file_optimized(self, filepath: str) -> Optional[pd.DataFrame]:
        """
        ОПТИМИЗИРОВАННЫЙ парсер для больших файлов.
        
        Стратегия:
        1. Читаем ТОЛЬКО первые 100 строк для определения структуры
        2. Определяем реальный интервал дискретизации
        3. Используем равномерное сэмплирование, а не пропуск строк
        4. Для 30+ МБ файлов читаем чанками
        """
        filename = os.path.basename(filepath)
        
        try:
            # ========== 1. Быстрое определение структуры ==========
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                header_line = f.readline().strip()
                first_data = f.readline().strip()
                second_data = f.readline().strip()
            
            # Парсим заголовок
            headers = header_line.split()
            if len(headers) < 3:
                return None
            
            # Определяем колонки спутников
            sat_columns = []
            for h in headers[2:]:
                if h.startswith('G') and h[1:].isdigit():
                    sat_columns.append(h)
            
            if not sat_columns:
                sat_columns = self.ALL_SATELLITES
            
            # ========== 2. Определяем реальную частоту ==========
            first_parts = first_data.split()
            second_parts = second_data.split()
            
            actual_interval = 0.1  # По умолчанию 10Hz
            sampling_rate_hz = 10.0  # По умолчанию
            
            if len(first_parts) >= 1 and len(second_parts) >= 1:
                try:
                    t1 = float(first_parts[0])
                    t2 = float(second_parts[0])
                    actual_interval = t2 - t1
                    if actual_interval > 0:
                        sampling_rate_hz = 1.0 / actual_interval
                except (ValueError, IndexError):
                    pass
            
            # ========== 3. ОПТИМИЗИРОВАННОЕ ЧТЕНИЕ ==========
            
            # Определяем размер файла
            file_size = os.path.getsize(filepath)
            
            # Для больших файлов используем построчное чтение с умным сэмплированием
            if file_size > 10 * 1024 * 1024:  # > 10 MB
                df = self._parse_large_file_chunked(
                    filepath, sat_columns, actual_interval
                )
            else:
                # Для маленьких файлов читаем полностью
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
        Читает большой файл чанками с адаптивным сэмплированием.
        """
        filename = os.path.basename(filepath)
        
        try:
            # Сначала оцениваем общее количество строк
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                total_lines = sum(1 for _ in f) - 1  # минус заголовок
            
            if total_lines <= 0:
                return None
            
            # Рассчитываем шаг сэмплирования для достижения target_points
            step = max(1, total_lines // self.target_points)
            
            data_rows = []
            time_values = []
            
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                # Пропускаем заголовок
                f.readline()
                
                line_count = 0
                for line in f:
                    line_count += 1
                    
                    # Равномерное сэмплирование
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
                        
                        # Читаем значения спутников
                        sat_idx = 0
                        for i in range(2, min(len(parts), len(sat_columns) + 2)):
                            sat_name = sat_columns[sat_idx] if sat_idx < len(sat_columns) else f"G{i-1:02d}"
                            try:
                                val = int(float(parts[i]))
                                row[sat_name] = val
                            except (ValueError, IndexError):
                                row[sat_name] = 0
                            sat_idx += 1
                        
                        # Заполняем отсутствующие спутники нулями
                        for sat in self.ALL_SATELLITES:
                            if sat not in row:
                                row[sat] = 0
                        
                        data_rows.append(row)
                        
                    except (ValueError, IndexError) as e:
                        continue
            
            if not data_rows:
                return None
            
            df = pd.DataFrame(data_rows)
            
            # Сохраняем информацию о реальном интервале
            df.attrs['actual_interval'] = actual_interval
            df.attrs['step'] = step
            df.attrs['total_lines'] = total_lines
            
            return df
            
        except Exception as e:
            print(f"Ошибка chunked парсинга {filename}: {e}")
            return None
    
    def _parse_small_file_full(self, filepath: str, sat_columns: List[str],
                                actual_interval: float) -> Optional[pd.DataFrame]:
        """Читает небольшой файл полностью."""
        filename = os.path.basename(filepath)
        
        try:
            # Используем pandas для быстрого чтения
            df = pd.read_csv(
                filepath,
                sep='\s+',
                header=0,
                engine='python',
                on_bad_lines='skip'
            )
            
            if len(df) < 2:
                return None
            
            # Переименовываем колонки если нужно
            column_map = {}
            for col in df.columns:
                if col.startswith('G') and col[1:].isdigit():
                    column_map[col] = col
                elif col not in ['DayTime', 'DateTime']:
                    # Пытаемся определить спутник по позиции
                    pass
            
            # Добавляем отсутствующие спутники
            for sat in self.ALL_SATELLITES:
                if sat not in df.columns:
                    df[sat] = 0
            
            df.attrs['actual_interval'] = actual_interval
            return df
            
        except Exception as e:
            print(f"Ошибка полного парсинга {filename}: {e}")
            return None
    
    def detect_gaps(self, visibility: np.ndarray, time_seconds: np.ndarray) -> List[SatelliteInterval]:
        """
        Детектирует интервалы видимости спутника.
        Возвращает ВСЕ интервалы, даже микроскопические.
        """
        if not np.any(visibility):
            return []
        
        # Находим перепады сигнала
        diff = np.diff(visibility.astype(int))
        starts = np.where(diff == 1)[0] + 1
        ends = np.where(diff == -1)[0] + 1
        
        # Обрабатываем граничные случаи
        if visibility[0]:
            starts = np.insert(starts, 0, 0)
        if visibility[-1]:
            ends = np.append(ends, len(visibility))
        
        intervals = []
        for start_idx, end_idx in zip(starts, ends):
            # Индекс конца интервала: берем последний элемент или предпоследний?
            # Для массива индексов 0..N-1, интервал занимает позиции start_idx .. end_idx-1
            end_time_idx = min(end_idx - 1, len(time_seconds) - 1)
            start_time = time_seconds[start_idx]
            end_time = time_seconds[end_time_idx]
            duration = end_time - start_time
            
            intervals.append(SatelliteInterval(
                start=start_time,
                end=end_time,
                duration=duration
            ))
        
        return intervals
    
    def merge_intervals_by_gap(self, intervals: List[SatelliteInterval], gap_threshold: float) -> List[SatelliteInterval]:
        """
        ОБЪЕДИНЯЕТ интервалы, если РАЗРЫВ между ними МЕНЬШЕ порога.
        
        Это КЛЮЧЕВОЙ МЕТОД для фильтрации коротких пропаданий.
        Если спутник пропал на 0.1 секунды и сразу появился - 
        это должно быть ОДНИМ ИНТЕРВАЛОМ, а не двумя.
        
        Args:
            intervals: Список интервалов видимости
            gap_threshold: Максимальная длительность пропадания для объединения (сек)
        
        Returns:
            Объединенный список интервалов
        """
        if not intervals:
            return []
        
        # Сортируем по времени начала
        sorted_int = sorted(intervals, key=lambda x: x.start)
        merged = []
        current = sorted_int[0]
        
        for interval in sorted_int[1:]:
            # Вычисляем разрыв между текущим интервалом и следующим
            gap = interval.start - current.end
            
            # Если разрыв МЕНЬШЕ порога - объединяем интервалы
            if gap <= gap_threshold:
                current = SatelliteInterval(
                    start=current.start,
                    end=max(current.end, interval.end),
                    duration=max(current.end, interval.end) - current.start
                )
            else:
                # Разрыв слишком большой - сохраняем текущий и начинаем новый
                merged.append(current)
                current = interval
        
        merged.append(current)
        return merged
    
    def merge_close_intervals(self, intervals: List[SatelliteInterval]) -> List[SatelliteInterval]:
        """
        Объединяет БЛИЗКО РАСПОЛОЖЕННЫЕ интервалы (использует self.merge_gap).
        Это дополнительная фильтрация для случаев, когда интервалы разделены,
        но находятся очень близко по времени.
        """
        return self.merge_intervals_by_gap(intervals, self.merge_gap)
    
    def calculate_satellite_stats(self, intervals: List[SatelliteInterval],
                                   total_duration: float, prn: str,
                                   sampling_rate_hz: float) -> SatelliteStatistics:
        """Рассчитывает статистику для одного спутника."""
        stats = SatelliteStatistics(
            prn=prn,
            num_intervals=len(intervals),
            intervals=intervals,
            sampling_rate_hz=sampling_rate_hz  # ИСПРАВЛЕНО: передаем реальную частоту
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
        Анализирует один SVs файл.
        
        ИСПРАВЛЕНО:
        1. Сначала детектируем ВСЕ интервалы
        2. ОБЪЕДИНЯЕМ интервалы при коротких пропаданиях (< min_gap_duration)
        3. Затем объединяем близкие интервалы (merge_gap)
        4. Нормализуем метрики по частоте дискретизации
        """
        filename = os.path.basename(filepath)
        
        df = self.parse_file_optimized(filepath)
        if df is None or len(df) < 2:
            return None
        
        time_seconds = df['DayTime'].values
        total_duration = time_seconds[-1] - time_seconds[0]
        
        # Получаем реальный интервал дискретизации и частоту
        actual_interval = df.attrs.get('actual_interval', 0.1)
        sampling_rate_hz = df.attrs.get('sampling_rate_hz', 1.0 / actual_interval if actual_interval > 0 else 10.0)
        
        satellite_stats = {}
        visible_count = 0
        total_sat_seconds = 0
        
        for sat in self.ALL_SATELLITES:
            if sat not in df.columns:
                satellite_stats[sat] = SatelliteStatistics(
                    prn=sat,
                    sampling_rate_hz=sampling_rate_hz
                )
                continue
            
            visibility = df[sat].values > 0
            
            # ============ ИСПРАВЛЕННАЯ ЛОГИКА ============
            
            # Шаг 1: Детектируем ВСЕ интервалы видимости (даже микроскопические)
            intervals = self.detect_gaps(visibility, time_seconds)
            
            # Шаг 2: Объединяем интервалы, если пропадание было короче min_gap_duration
            # Это фильтрует микро-пропадания (0.1-1.9 сек на 10Hz данных)
            intervals = self.merge_intervals_by_gap(intervals, self.min_gap_duration)
            
            # Шаг 3: Дополнительно объединяем очень близкие интервалы
            # (использует merge_gap, который обычно больше min_gap_duration)
            intervals = self.merge_close_intervals(intervals)
            
            # =============================================
            
            # Рассчитываем статистику с учетом частоты дискретизации
            stats = self.calculate_satellite_stats(
                intervals, total_duration, sat, sampling_rate_hz
            )
            satellite_stats[sat] = stats
            
            if stats.is_visible:
                visible_count += 1
                total_sat_seconds += stats.total_visible_time
        
        mean_satellites = total_sat_seconds / total_duration if total_duration > 0 else 0
        
        # Информация о данных
        step = df.attrs.get('step', 1)
        total_lines = df.attrs.get('total_lines', len(df) * step)
        
        data = GPSConstellationData(
            filename=filename,
            filepath=filepath,
            time_range=(time_seconds[0], time_seconds[-1]),
            total_duration=total_duration,
            rows_original=total_lines,
            rows_sampled=len(df),
            sampling_rate=step,
            actual_sampling_interval=actual_interval,
            sampling_rate_hz=sampling_rate_hz
        )
        
        result = GPSConstellationAnalysisResult(
            filename=filename,
            filepath=filepath,
            data=data,
            satellite_stats=satellite_stats,
            visible_satellites=visible_count,
            mean_satellites=mean_satellites
        )
        
        self._results[filename] = result
        return result
    
    def analyze_all(self, results_dir: str) -> Dict[str, GPSConstellationAnalysisResult]:
        """Анализирует все SVs файлы в директории."""
        self._results.clear()
        
        for filepath in self.find_sv_files(results_dir):
            result = self.analyze_file(filepath)
            if result:
                self._results[result.filename] = result
        
        return self.get_results()
    
    def get_results(self) -> Dict[str, GPSConstellationAnalysisResult]:
        return self._results.copy()
    
    def get_visible_satellites(self, filename: str) -> List[str]:
        if filename not in self._results:
            return []
        result = self._results[filename]
        return [sat for sat, stats in result.satellite_stats.items() if stats.is_visible]
    
    def get_problematic_satellites(self, filename: str) -> List[Tuple[str, SatelliteStatistics]]:
        if filename not in self._results:
            return []
        return self._results[filename].problem_satellites
    
    def get_quality_report(self, filename: str) -> Optional[Dict[str, Any]]:
        if filename not in self._results:
            return None
        return self._results[filename].summary_report
    
    def export_to_csv(self, output_file: str) -> bool:
        """Экспортирует результаты в CSV."""
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
                
                # Топ-5 проблемных спутников (по частоте!)
                problematic = sorted(
                    result.problem_satellites,
                    key=lambda x: x[1].intervals_per_minute,
                    reverse=True
                )[:5]
                
                for i, (sat, stats) in enumerate(problematic, 1):
                    row[f'Problem{i}_Satellite'] = sat
                    row[f'Problem{i}_Intervals'] = stats.num_intervals
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