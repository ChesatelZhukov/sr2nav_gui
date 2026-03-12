from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, Optional
import tkinter as tk
class ThemeType(Enum):
    DARK = auto()                                   
    LIGHT = auto()                    
    BARBIE = auto()                           
@dataclass(frozen=True)
class ThemeColors:
    BG_PRIMARY: str                         
    BG_SECONDARY: str                                                
    BG_TERTIARY: str                                  
    FG_PRIMARY: str                      
    FG_SECONDARY: str                                             
    FG_DISABLED: str                                    
    BORDER: str                                             
    ACCENT_BLUE: str                                 
    ACCENT_GREEN: str                       
    ACCENT_RED: str                                
    ACCENT_ORANGE: str                             
    ACCENT_PURPLE: str                            
    ACCENT_CYAN: str                              
    SUCCESS: str                              
    WARNING: str                         
    ERROR: str                   
    INFO: str                        
    DEBUG: str                                  
    HOVER: str                               
    SELECTED: str                           
    DISABLED: str                             
DARK_THEME = ThemeColors(    BG_PRIMARY="#1a1b1e",    BG_SECONDARY="#2c2e33",    BG_TERTIARY="#3a3c44",    FG_PRIMARY="#e8e9ed",    FG_SECONDARY="#9a9ca5",    FG_DISABLED="#5f616a",    BORDER="#40434a",    ACCENT_BLUE="#5f8ec9",    ACCENT_GREEN="#6f9e6f",    ACCENT_RED="#c96b6b",    ACCENT_ORANGE="#c99a6b",    ACCENT_PURPLE="#9f8cc9",    ACCENT_CYAN="#6b9ec9",    SUCCESS="#8fbc8f",    WARNING="#e0b080",    ERROR="#d98c8c",    INFO="#80b0e0",    DEBUG="#b0a0d0",    HOVER="#3e4048",    SELECTED="#2a4f6e",    DISABLED="#2a2c30",)
LIGHT_THEME = ThemeColors(    BG_PRIMARY="#f5f5f5",    BG_SECONDARY="#ffffff",    BG_TERTIARY="#e8e8e8",    FG_PRIMARY="#333333",    FG_SECONDARY="#666666",    FG_DISABLED="#999999",    BORDER="#cccccc",    ACCENT_BLUE="#0066cc",    ACCENT_GREEN="#2e7d32",    ACCENT_RED="#c62828",    ACCENT_ORANGE="#ed6c02",    ACCENT_PURPLE="#7b1fa2",    ACCENT_CYAN="#0097a7",    SUCCESS="#2e7d32",    WARNING="#ed6c02",    ERROR="#c62828",    INFO="#0288d1",    DEBUG="#7b1fa2",    HOVER="#e0e0e0",    SELECTED="#bbdefb",    DISABLED="#f0f0f0",)
BARBIE_THEME = ThemeColors(    BG_PRIMARY="#FFB6C1",    BG_SECONDARY="#FFC0CB",    BG_TERTIARY="#FFA6C9",    FG_PRIMARY="#000000",    FG_SECONDARY="#000000",    FG_DISABLED="#000000",    BORDER="#FF1493",    ACCENT_BLUE="#FF69B4",    ACCENT_GREEN="#FF85B3",    ACCENT_RED="#FF4D6D",    ACCENT_ORANGE="#FFA07A",    ACCENT_PURPLE="#DA70D6",    ACCENT_CYAN="#FFB3C6",    SUCCESS="#FFC0CB",    WARNING="#FFB347",    ERROR="#FF6B8B",    INFO="#FFB6C1",    DEBUG="#FFA6C9",    HOVER="#FF1493",    SELECTED="#FF69B4",    DISABLED="#FFB6C1",)
_THEMES: Dict[ThemeType, ThemeColors] = {    ThemeType.DARK: DARK_THEME,    ThemeType.LIGHT: LIGHT_THEME,    ThemeType.BARBIE: BARBIE_THEME,}
_ACTIVE_THEME: ThemeType = ThemeType.DARK
_BG_PRIMARY_VALUES = {theme.BG_PRIMARY for theme in _THEMES.values()}
_BG_SECONDARY_VALUES = {theme.BG_SECONDARY for theme in _THEMES.values()}
_BG_TERTIARY_VALUES = {theme.BG_TERTIARY for theme in _THEMES.values()}
_FG_PRIMARY_VALUES = {theme.FG_PRIMARY for theme in _THEMES.values()}
_FG_SECONDARY_VALUES = {theme.FG_SECONDARY for theme in _THEMES.values()}
_FG_DISABLED_VALUES = {theme.FG_DISABLED for theme in _THEMES.values()}
_BORDER_VALUES = {theme.BORDER for theme in _THEMES.values()}
_ACCENT_BLUE_VALUES = {theme.ACCENT_BLUE for theme in _THEMES.values()}
_ACCENT_GREEN_VALUES = {theme.ACCENT_GREEN for theme in _THEMES.values()}
_ACCENT_RED_VALUES = {theme.ACCENT_RED for theme in _THEMES.values()}
_ACCENT_ORANGE_VALUES = {theme.ACCENT_ORANGE for theme in _THEMES.values()}
_ACCENT_PURPLE_VALUES = {theme.ACCENT_PURPLE for theme in _THEMES.values()}
_ACCENT_CYAN_VALUES = {theme.ACCENT_CYAN for theme in _THEMES.values()}
def set_active_theme(theme_type: ThemeType) -> None:
    global _ACTIVE_THEME
    if theme_type in _THEMES:
        _ACTIVE_THEME = theme_type
def get_active_theme() -> ThemeColors:
    return _THEMES[_ACTIVE_THEME]
def get_theme_colors(theme_type: Optional[ThemeType] = None) -> ThemeColors:
    if theme_type is None:
        return get_active_theme()
    return _THEMES.get(theme_type, get_active_theme())
def get_theme_name(theme_type: ThemeType) -> str:
    names = {        ThemeType.DARK: "🌙 Тёмная",        ThemeType.LIGHT: "☀️ Светлая",        ThemeType.BARBIE: "💖 Бимбо",    }
    return names.get(theme_type, "Неизвестная")
def get_all_themes() -> Dict[ThemeType, str]:
    return {theme_type: get_theme_name(theme_type) for theme_type in ThemeType}
def apply_theme(widget: tk.Widget, theme_colors: Optional[ThemeColors] = None) -> None:
    if theme_colors is None:
        theme_colors = get_active_theme()
    try:
        bg = widget.cget('bg')
    except Exception:
        bg = None
    try:
        fg = widget.cget('fg')
    except Exception:
        fg = None
    # Перекраска фона
    try:
        if bg in ('SystemButtonFace', 'SystemWindow', '#f0f0f0'):
            widget.configure(bg=theme_colors.BG_PRIMARY)
        elif bg in _BG_PRIMARY_VALUES:
            widget.configure(bg=theme_colors.BG_PRIMARY)
        elif bg in _BG_SECONDARY_VALUES:
            widget.configure(bg=theme_colors.BG_SECONDARY)
        elif bg in _BG_TERTIARY_VALUES:
            widget.configure(bg=theme_colors.BG_TERTIARY)
        elif bg in _BORDER_VALUES:
            widget.configure(bg=theme_colors.BORDER)
        elif bg in _ACCENT_BLUE_VALUES:
            widget.configure(bg=theme_colors.ACCENT_BLUE)
        elif bg in _ACCENT_GREEN_VALUES:
            widget.configure(bg=theme_colors.ACCENT_GREEN)
        elif bg in _ACCENT_RED_VALUES:
            widget.configure(bg=theme_colors.ACCENT_RED)
        elif bg in _ACCENT_ORANGE_VALUES:
            widget.configure(bg=theme_colors.ACCENT_ORANGE)
        elif bg in _ACCENT_PURPLE_VALUES:
            widget.configure(bg=theme_colors.ACCENT_PURPLE)
        elif bg in _ACCENT_CYAN_VALUES:
            widget.configure(bg=theme_colors.ACCENT_CYAN)
    except Exception:
        pass
    # Перекраска текста
    try:
        if fg in _FG_PRIMARY_VALUES:
            widget.configure(fg=theme_colors.FG_PRIMARY)
        elif fg in _FG_SECONDARY_VALUES:
            widget.configure(fg=theme_colors.FG_SECONDARY)
        elif fg in _FG_DISABLED_VALUES:
            widget.configure(fg=theme_colors.FG_DISABLED)
    except Exception:
        pass
    # Рекурсивно обойти детей
    try:
        for child in widget.winfo_children():
            apply_theme(child, theme_colors)
    except Exception:
        pass
@property
def Theme_BG_PRIMARY(self):
    return get_active_theme().BG_PRIMARY
class Theme:
    @property
    def BG_PRIMARY(self): return get_active_theme().BG_PRIMARY
    @property
    def BG_SECONDARY(self): return get_active_theme().BG_SECONDARY
    @property
    def BG_TERTIARY(self): return get_active_theme().BG_TERTIARY
    @property
    def FG_PRIMARY(self): return get_active_theme().FG_PRIMARY
    @property
    def FG_SECONDARY(self): return get_active_theme().FG_SECONDARY
    @property
    def FG_DISABLED(self): return get_active_theme().FG_DISABLED
    @property
    def BORDER(self): return get_active_theme().BORDER
    @property
    def ACCENT_BLUE(self): return get_active_theme().ACCENT_BLUE
    @property
    def ACCENT_GREEN(self): return get_active_theme().ACCENT_GREEN
    @property
    def ACCENT_RED(self): return get_active_theme().ACCENT_RED
    @property
    def ACCENT_ORANGE(self): return get_active_theme().ACCENT_ORANGE
    @property
    def ACCENT_PURPLE(self): return get_active_theme().ACCENT_PURPLE
    @property
    def ACCENT_CYAN(self): return get_active_theme().ACCENT_CYAN
    @property
    def SUCCESS(self): return get_active_theme().SUCCESS
    @property
    def WARNING(self): return get_active_theme().WARNING
    @property
    def ERROR(self): return get_active_theme().ERROR
    @property
    def INFO(self): return get_active_theme().INFO
    @property
    def DEBUG(self): return get_active_theme().DEBUG
    @property
    def HOVER(self): return get_active_theme().HOVER
    @property
    def SELECTED(self): return get_active_theme().SELECTED
    @property
    def DISABLED(self): return get_active_theme().DISABLED
Theme = Theme()