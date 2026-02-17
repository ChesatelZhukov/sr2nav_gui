"""
Пакет графического интерфейса пользователя (View в паттерне MVC).

Содержит все компоненты пользовательского интерфейса, включая главное окно,
диалоги, виджеты и окна анализа. Не содержит бизнес-логики - вся логика
делегируется контроллеру.

Архитектура пакета:
    view/
    ├── themes.py           # Цветовые темы и стили оформления
    ├── widgets.py          # Переиспользуемые UI-компоненты (кнопки, поля ввода)
    ├── dialogs.py          # Модальные диалоговые окна
    ├── main_window.py      # Главное окно приложения (содержит UIPersistence)
    └── analysis_windows/   # Окна для отображения результатов анализа
        ├── velocity_window.py  # Окно анализа скоростей
        └── gps_window.py       # Окно анализа GPS созвездия

Все классы в этом пакете отвечают только за отображение и взаимодействие с пользователем.
Обработка данных и бизнес-логика выполняются в контроллере и модели.
"""
from view.themes import Theme
from view.widgets import ModernButton, FileEntryWidget, CollapsibleFrame, InteractiveZoom
from view.dialogs import GPSExclusionDialog, TransformFileDialog
from view.main_window import MainWindow, UIPersistence  # UIPersistence для сохранения состояния
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
    'UIPersistence',      # Сохранение состояния UI между сессиями
    'VelocityAnalysisWindow',
    'GPSAnalysisWindow',
]
