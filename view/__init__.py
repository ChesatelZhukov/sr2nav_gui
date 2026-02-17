"""
Пакет графического интерфейса пользователя (View в паттерне MVC).

Содержит все компоненты пользовательского интерфейса, включая главное окно,
диалоги, виджеты, окна анализа и модуль сохранения состояния UI. 
Не содержит бизнес-логики - вся логика делегируется контроллеру.

Архитектура пакета:
    view/
    ├── themes.py           # Цветовые темы и стили оформления
    ├── widgets.py          # Переиспользуемые UI-компоненты
    ├── dialogs.py          # Модальные диалоговые окна
    ├── main_window.py      # Главное окно приложения
    ├── persistence.py      # Сохранение состояния UI между сессиями
    └── analysis_windows/   # Окна для отображения результатов анализа
        ├── velocity_window.py  # Окно анализа скоростей
        └── gps_window.py       # Окно анализа GPS созвездия

Все классы в этом пакете отвечают только за отображение и взаимодействие с пользователем.
Обработка данных и бизнес-логика выполняются в контроллере и модели.
"""
from view.themes import Theme
from view.widgets import ModernButton, FileEntryWidget, CollapsibleFrame, InteractiveZoom
from view.dialogs import GPSExclusionDialog, TransformFileDialog
from view.main_window import MainWindow
from view.persistence import UIPersistence  # Сохранение состояния UI между запусками
from view.analysis_windows.velocity_window import VelocityAnalysisWindow
from view.analysis_windows.gps_window import GPSAnalysisWindow

__all__ = [
    # Компоненты оформления
    'Theme',
    
    # Базовые UI-компоненты
    'ModernButton',
    'FileEntryWidget',
    'CollapsibleFrame',
    'InteractiveZoom',
    
    # Диалоговые окна
    'GPSExclusionDialog',
    'TransformFileDialog',
    
    # Основные окна
    'MainWindow',
    'UIPersistence',      # Сохранение состояния UI (последние пути, настройки)
    'VelocityAnalysisWindow',
    'GPSAnalysisWindow',
]