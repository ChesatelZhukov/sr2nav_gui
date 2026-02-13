#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЧИСТАЯ МОДЕЛЬ - Анализатор GPS созвездия.
ИСПРАВЛЕНО v3.0:
1. Корректное разделение: raw_intervals для частоты, merged_intervals для отображения
2. Пиковая частота считается по raw_intervals (микро-интервалам)
3. Для одного непрерывного интервала частота = 0.0
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
    intervals: List[SatelliteInterval] = field(default_factory=list)        # ОБЪЕДИНЕННЫЕ интервалы (для графика)
    raw_intervals: List[SatelliteInterval] = field(default_factory=list)    # СЫРЫЕ интервалы (для расчета частоты)
    sampling_rate_hz: float = 10.0
    
    # Пиковые метрики
    peak_intervals_per_minute: float = 0.0
    """Максимальное количество интервалов в 10-минутном окне, пересчитанное в минуты"""
    
    peak_intervals_per_minute_norm: float = 0.0
    """Нормализованная пиковая частота (приведена к 10 Гц)"""
    
    peak_window_center: float = 0.0
    """Центр окна с максимальной частотой (сек)"""
    
    peak_window_start: float = 0.0
    """Начало окна с максимальной частотой (сек)"""
    
    peak_window_end: float = 0.0
    """Конец окна с максимальной частотой (сек)"""
    
    peak_window_count: int = 0
    """Количество интервалов в пиковом окне"""
    
    @property
    def intervals_per_minute(self) -> float:
        """
        Возвращает ПИКОВУЮ НОРМАЛИЗОВАННУЮ ЧАСТОТУ.
        ИСПРАВЛЕНО: если сырых интервалов <= 1, возвращаем 0.0
        """
        if not self.is_visible:
            return 999.0
        
        # Если спутник виден одним непрерывным интервалом - частота 0
        if len(self.raw_intervals) <= 1:
            return 0.0
        
        if self.peak_intervals_per_minute_norm > 0:
            return self.peak_intervals_per_minute_norm
        
        # Fallback
        raw_ipm = (len(self.raw_intervals) / self.total_visible_time) * 60
        return raw_ipm * (10.0 / self.sampling_rate_hz)
    
    @property
    def peak_description(self) -> str:
        """Человекочитаемое описание пиковой нагрузки."""
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
        """Индекс стабильности от 0 до 1 для RTK."""
        if not self.is_visible:
            return 0.0
        if len(self.raw_intervals) <= 1:
            return 1.0  # Только непрерывный трек
        
        ipm = self.intervals_per_minute
        
        # ЖЁСТКИЕ КРИТЕРИИ ДЛЯ RTK
        if ipm == 0.0:
            return 1.0      # Эталон - непрерывный
        elif ipm <= 0.01:   # 1 пропадание за 100 мин
            return 0.8      # Хорошо
        elif ipm <= 0.02:   # 1 пропадание за 50 мин
            return 0.6      # Удовлетворительно
        elif ipm <= 0.05:   # 1 пропадание за 20 мин
            return 0.3      # Плохо для RTK
        else:
            return 0.1      # Непригодно
    
    @property
    def stability_category(self) -> Tuple[str, str]:
        """Категория стабильности для RTK."""
        if not self.is_visible:
            return ("Не виден", "invisible")
        
        ipm = self.intervals_per_minute
        raw_count = len(self.raw_intervals)
        
        # ЭТАЛОН - только один непрерывный интервал
        if raw_count <= 1:
            return ("Эталонный", "excellent")
        
        # ЖЁСТКАЯ ГРАДАЦИЯ ДЛЯ RTK
        if ipm <= 0.01:      # <1 пропадания за 100 мин
            return ("Отличный", "excellent")
        elif ipm <= 0.02:    # <1 пропадания за 50 мин
            return ("Хороший", "good")
        elif ipm <= 0.05:    # <1 пропадания за 20 мин
            return ("Удовлетворительный", "moderate")
        elif ipm <= 0.1:     # <1 пропадания за 10 мин
            return ("Плохой", "bad")
        else:                # >1 пропадания за 10 мин
            return ("Непригодный", "critical")
    
    @property
    def warning_message(self) -> Optional[str]:
        """Предупреждения для RTK."""
        if not self.is_visible:
            return None
        
        ipm = self.intervals_per_minute
        raw_count = len(self.raw_intervals)
        
        if raw_count <= 1:
            return None
        
        # РАННИЕ ПРЕДУПРЕЖДЕНИЯ ДЛЯ RTK
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
        """Проблемный для RTK >0.02/мин."""
        if not self.is_visible:
            return False
        
        if len(self.raw_intervals) <= 1:
            return False
        
        # ПОРОГ ПРОБЛЕМНОСТИ ДЛЯ RTK
        if self.intervals_per_minute > 0.02:
            return True
        
        return False


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
    actual_sampling_interval: float
    sampling_rate_hz: float = 10.0


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
        """Общая оценка качества от 0 до 100 для RTK."""
        if self.visible_satellites == 0:
            return 0.0
        
        # Базовый балл от количества спутников
        base_score = min(100, (self.mean_satellites / 10) * 100)
        
        # ШТРАФЫ ЗА НЕСТАБИЛЬНОСТЬ
        penalty = 0
        problem_count = 0
        
        for _, stats in self.satellite_stats.items():
            if not stats.is_visible:
                continue
            
            ipm = stats.intervals_per_minute
            
            # ЖЁСТКИЕ ШТРАФЫ ДЛЯ RTK
            if ipm > 0.1:
                penalty += 50  # Непригодно
                problem_count += 1
            elif ipm > 0.05:
                penalty += 30  # Критично
                problem_count += 1
            elif ipm > 0.02:
                penalty += 20  # Плохо
                problem_count += 1
            elif ipm > 0.01:
                penalty += 10  # Умеренно
                problem_count += 1
        
        if problem_count > 0:
            penalty = penalty / problem_count
        
        final_score = max(0, base_score - penalty)
        return round(final_score, 1)

    @property
    def overall_quality_category(self) -> Tuple[str, str]:
        """Категории качества для RTK."""
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
    ИСПРАВЛЕНО v3.0:
    - raw_intervals для расчета частоты
    - merged_intervals для отображения
    - Один непрерывный интервал = частота 0.0
    """
    
    ALL_SATELLITES = [f'G{i:02d}' for i in range(1, 33)]
    
    def __init__(self, 
                 target_points: int = 5000,
                 min_gap_duration: float = 10,
                 merge_gap: float = 10.0):
        """
        Args:
            target_points: Целевое количество точек
            min_gap_duration: Минимальная длительность ПРОПАДАНИЯ для разделения интервалов (сек)
            merge_gap: Объединять интервалы с разрывом МЕНЬШЕ N сек
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
        """
        filename = os.path.basename(filepath)
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                header_line = f.readline().strip()
                first_data = f.readline().strip()
                second_data = f.readline().strip()
            
            headers = header_line.split()
            if len(headers) < 3:
                return None
            
            sat_columns = []
            for h in headers:
                if h.startswith('G') and h[1:].isdigit():
                    sat_columns.append(h)
            
            if not sat_columns:
                sat_columns = self.ALL_SATELLITES.copy()
            
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
        """Читает большой файл чанками с адаптивным сэмплированием."""
        filename = os.path.basename(filepath)
        
        try:
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
            
            step = max(1, total_lines // self.target_points)
            
            data_rows = []
            time_values = []
            
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                f.readline()
                
                line_count = 0
                for line in f:
                    line_count += 1
                    
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
                        
                        for sat in self.ALL_SATELLITES:
                            row[sat] = 0
                        
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
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                header_line = f.readline().strip()
                headers = header_line.split()
            
            df = pd.read_csv(
                filepath,
                sep='\s+',
                header=0,
                engine='python',
                on_bad_lines='skip'
            )
            
            if len(df) < 2:
                return None
            
            actual_sat_columns = []
            for col in df.columns:
                if col.startswith('G') and col[1:].isdigit():
                    actual_sat_columns.append(col)
            
            for sat in self.ALL_SATELLITES:
                if sat not in df.columns:
                    df[sat] = 0
            
            columns_order = ['DayTime', 'DateTime'] + self.ALL_SATELLITES
            existing_columns = [col for col in columns_order if col in df.columns]
            df = df[existing_columns]
            
            df.attrs['actual_interval'] = actual_interval
            return df
            
        except Exception as e:
            print(f"Ошибка полного парсинга {filename}: {e}")
            return None
    
    def detect_gaps(self, visibility: np.ndarray, time_seconds: np.ndarray) -> List[SatelliteInterval]:
        """Детектирует ВСЕ интервалы видимости спутника (сырые)."""
        if not np.any(visibility):
            return []
        
        diff = np.diff(visibility.astype(int))
        starts = np.where(diff == 1)[0] + 1
        ends = np.where(diff == -1)[0] + 1
        
        if visibility[0]:
            starts = np.insert(starts, 0, 0)
        if visibility[-1]:
            ends = np.append(ends, len(visibility))
        
        intervals = []
        for start_idx, end_idx in zip(starts, ends):
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
        Объединяет интервалы, если РАЗРЫВ между ними МЕНЬШЕ порога.
        Используется для объединения микро-пропаданий.
        """
        if not intervals:
            return []
        
        sorted_int = sorted(intervals, key=lambda x: x.start)
        merged = []
        current = sorted_int[0]
        
        for interval in sorted_int[1:]:
            gap = interval.start - current.end
            
            if gap <= gap_threshold:
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
        """Объединяет близко расположенные интервалы."""
        return self.merge_intervals_by_gap(intervals, self.merge_gap)
    
    def calculate_satellite_stats(self, intervals: List[SatelliteInterval],
                                   total_duration: float, prn: str,
                                   sampling_rate_hz: float) -> SatelliteStatistics:
        """Рассчитывает статистику для одного спутника."""
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
        Анализирует один SVs файл.
        
        ИСПРАВЛЕНО v3.0:
        1. Детекция ВСЕХ интервалов видимости (raw_intervals)
        2. Объединение микро-пропаданий (merged_intervals) для отображения
        3. Расчет пиковой частоты по raw_intervals
        4. Если raw_intervals <= 1 → частота = 0.0
        """
        filename = os.path.basename(filepath)
        
        # ------------------------------------------------------------
        # ШАГ 1: ПАРСИНГ ФАЙЛА
        # ------------------------------------------------------------
        df = self.parse_file_optimized(filepath)
        if df is None or len(df) < 2:
            self._results.pop(filename, None)
            return None
        
        # ------------------------------------------------------------
        # ШАГ 2: ИЗВЛЕЧЕНИЕ ВРЕМЕННЫХ РЯДОВ
        # ------------------------------------------------------------
        time_seconds = df['DayTime'].values
        total_duration = time_seconds[-1] - time_seconds[0]
        
        actual_interval = df.attrs.get('actual_interval', 0.1)
        if actual_interval <= 0:
            actual_interval = 0.1
        
        sampling_rate_hz = 1.0 / actual_interval
        sampling_rate_hz = min(max(sampling_rate_hz, 0.1), 100.0)
        
        # ------------------------------------------------------------
        # ШАГ 3: АНАЛИЗ КАЖДОГО СПУТНИКА
        # ------------------------------------------------------------
        satellite_stats = {}
        visible_count = 0
        total_sat_seconds = 0.0
        
        for sat in self.ALL_SATELLITES:
            # ---------- 3.1 Проверка наличия колонки ----------
            if sat not in df.columns:
                satellite_stats[sat] = SatelliteStatistics(
                    prn=sat,
                    sampling_rate_hz=sampling_rate_hz,
                    is_visible=False
                )
                continue
            
            # ---------- 3.2 Маска видимости ----------
            visibility = df[sat].values > 0
            
            if not np.any(visibility):
                satellite_stats[sat] = SatelliteStatistics(
                    prn=sat,
                    sampling_rate_hz=sampling_rate_hz,
                    is_visible=False
                )
                continue
            
            # ========== 3.3 ИСПРАВЛЕНИЕ: ДВА ТИПА ИНТЕРВАЛОВ ==========
            # СЫРЫЕ интервалы - для расчета частоты
            raw_intervals = self.detect_gaps(visibility, time_seconds)
            
            # ОБЪЕДИНЕННЫЕ интервалы - для отображения на графике
            merged_intervals = self.merge_intervals_by_gap(raw_intervals, self.min_gap_duration)
            final_intervals = self.merge_close_intervals(merged_intervals)
            
            # ---------- 3.4 Базовая статистика ----------
            stats = self._calculate_basic_stats(
                final_intervals, 
                total_duration, 
                sat, 
                sampling_rate_hz
            )
            
            # ---------- 3.5 Сохраняем СЫРЫЕ интервалы ----------
            stats.raw_intervals = raw_intervals
            
            # ========== 3.6 ИСПРАВЛЕННЫЙ РАСЧЕТ ПИКОВОЙ ЧАСТОТЫ ==========
            # Используем raw_intervals, а не final_intervals!
            if raw_intervals and len(raw_intervals) > 1:  # Только если есть микро-интервалы
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
                
                # Пересчет в интервалы/минуту
                peak_raw_ipm = max_intervals_in_window / WINDOW_MINUTES
                peak_normalized_ipm = peak_raw_ipm * (10.0 / sampling_rate_hz)
                
                stats.peak_intervals_per_minute = peak_raw_ipm
                stats.peak_intervals_per_minute_norm = peak_normalized_ipm
                stats.peak_window_center = optimal_window_center
                stats.peak_window_start = optimal_window_center - WINDOW_SECONDS/2
                stats.peak_window_end = optimal_window_center + WINDOW_SECONDS/2
                stats.peak_window_count = max_intervals_in_window
            else:
                # Один непрерывный интервал или нет интервалов
                stats.peak_intervals_per_minute = 0.0
                stats.peak_intervals_per_minute_norm = 0.0
                stats.peak_window_center = 0.0
                stats.peak_window_count = 1 if raw_intervals else 0
            
            # ---------- 3.7 Сохраняем статистику ----------
            satellite_stats[sat] = stats
            
            if stats.is_visible:
                visible_count += 1
                total_sat_seconds += stats.total_visible_time
        
        # ------------------------------------------------------------
        # ШАГ 4: ОБЩАЯ СТАТИСТИКА ПО ФАЙЛУ
        # ------------------------------------------------------------
        mean_satellites = total_sat_seconds / total_duration if total_duration > 0 else 0
        
        step = df.attrs.get('step', 1)
        total_lines = df.attrs.get('total_lines', len(df) * step)
        
        # ------------------------------------------------------------
        # ШАГ 5: ФОРМИРОВАНИЕ РЕЗУЛЬТАТА
        # ------------------------------------------------------------
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
        """Рассчитывает базовую статистику (без пиковой частоты)."""
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
                
                problematic = sorted(
                    result.problem_satellites,
                    key=lambda x: x[1].intervals_per_minute,
                    reverse=True
                )[:5]
                
                for i, (sat, stats) in enumerate(problematic, 1):
                    row[f'Problem{i}_Satellite'] = sat
                    row[f'Problem{i}_Intervals'] = len(stats.raw_intervals)  # сырые интервалы
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