from dataclasses import dataclass
@dataclass(frozen=True)
class Theme:
    BG_PRIMARY: str = "#FFB6C1"                                                   
    BG_SECONDARY: str = "#FFC0CB"                                     
    BG_TERTIARY: str = "#FFA6C9"                                   
    FG_PRIMARY: str = "#000000"                                   
    FG_SECONDARY: str = "#000000"                                  
    FG_DISABLED: str = "#000000"                                   
    BORDER: str = "#FF1493"                                          
    ACCENT_BLUE: str = "#FF69B4"                                            
    ACCENT_GREEN: str = "#FF85B3"                                    
    ACCENT_RED: str = "#FF4D6D"                                           
    ACCENT_ORANGE: str = "#FFA07A"                                       
    ACCENT_PURPLE: str = "#DA70D6"                                  
    ACCENT_CYAN: str = "#FFB3C6"                                       
    SUCCESS: str = "#FFC0CB"                                               
    WARNING: str = "#FFB347"                                        
    ERROR: str = "#FF6B8B"                                             
    INFO: str = "#FFB6C1"                                           
    DEBUG: str = "#FFA6C9"                                       
    HOVER: str = "#FF1493"                                           
    SELECTED: str = "#FF69B4"                                      
    DISABLED: str = "#FFB6C1"                                       
def apply_theme(widget) -> None:
    bg = widget.cget('bg')
    if bg in ('SystemButtonFace', 'SystemWindow', '#f0f0f0'):
        try:
            widget.configure(bg=Theme.BG_PRIMARY)
        except:
            pass
    try:
        for child in widget.winfo_children():
            apply_theme(child)
    except:
        pass