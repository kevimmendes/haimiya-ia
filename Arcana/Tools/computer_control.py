import pyautogui
import os
import time

class ComputerControl:
    def __init__(self, output_callback=None):
        self.output_callback = output_callback
        pyautogui.FAILSAFE = True
    
    def log(self, message):
        if self.output_callback:
            self.output_callback(message)
        else:
            print(message)
    
    # Mouse control
    def move_mouse(self, x, y, duration=0.1):
        """Move mouse to position (x, y) over duration seconds"""
        try:
            pyautogui.moveTo(x, y, duration=duration)
            self.log(f"🖱️ Mouse movido para ({x}, {y})")
            return True
        except Exception as e:
            self.log(f"❌ Erro ao mover mouse: {e}")
            return False
    
    def click_mouse(self, button="left", clicks=1, duration=0.1):
        """Click with specified button (left/right), clicks count, and duration"""
        try:
            if button == "right":
                pyautogui.rightClick()
            elif button == "left":
                pyautogui.click()
            
            for _ in range(clicks - 1):
                pyautogui.click(button=button, interval=duration)
            
            if clicks >= 1:
                pyautogui.click(button=button)
            
            self.log(f"🖱️ Clique {button} ({clicks}x) executado")
            return True
        except Exception as e:
            self.log(f"❌ Erro ao clicar mouse: {e}")
            return False
    
    def double_click(self, button="left"):
        """Double click with specified button"""
        try:
            pyautogui.doubleClick(button=button)
            self.log(f"🖱️ Duplo clique {button} executado")
            return True
        except Exception as e:
            self.log(f"❌ Erro ao dar duplo clique: {e}")
            return False
    
    def right_click(self):
        """Right click"""
        return self.click_mouse(button="right", clicks=1)
    
    # Keyboard control
    def type_text(self, text, interval=0.01):
        """Type text character by character"""
        try:
            pyautogui.typewrite(text, interval=interval)
            self.log(f"💰 Texto digitado: '{text[:50]}{'...' if len(text) > 50 else ''}'")
            return True
        except Exception as e:
            self.log(f"❌ Erro ao digitar texto: {e}")
            return False
    
    def press_key(self, key):
        """Press a single key"""
        try:
            pyautogui.press(key)
            self.log(f"⌨️ Tecla '{key}' pressionada")
            return True
        except Exception as e:
            self.log(f"❌ Erro ao pressionar tecla '{key}': {e}")
            return False
    
    def hotkey(self, *keys):
        """Press a hotkey combination (e.g., ctrl+c, win+r)"""
        try:
            pyautogui.hotkey(*keys)
            keys_str = '+'.join(keys)
            self.log(f"⌨️ Atalho '{keys_str}' executado")
            return True
        except Exception as e:
            self.log(f"❌ Erro ao executar atalho '{keys}': {e}")
            return False
    
    # Screen capture
    def capture_screen(self, region=None):
        """Capture screen, optionally a region (x, y, width, height)"""
        try:
            img = pyautogui.screenshot(region=region)
            self.log(f"📸 Tela capturada ({img.size[0]}x{img.size[1]})")
            return img
        except Exception as e:
            self.log(f"❌ Erro ao capturar tela: {e}")
            return None
    
    # Window management
    def get_windows(self):
        """Get list of window titles"""
        try:
            import pygetwindow as gw
            windows = gw.getAllTitles()
            return [w for w in windows if w]
        except Exception as e:
            self.log(f"❌ Erro ao obter janelas: {e}")
            return []
    
    def find_window(self, title_pattern):
        """Find a window by title pattern"""
        try:
            import pygetwindow as gw
            matches = gw.getWindowsWithTitle(title_pattern)
            return matches[0] if matches else None
        except Exception as e:
            self.log(f"❌ Erro ao encontrar janela: {e}")
            return None
    
    def activate_window(self, title_pattern):
        """Activate a window by title pattern"""
        try:
            window = self.find_window(title_pattern)
            if window:
                window.activate()
                self.log(f"🪟 Janela '{title_pattern}' ativada")
                return True
            self.log(f"⚠️ Janela '{title_pattern}' não encontrada")
            return False
        except Exception as e:
            self.log(f"❌ Erro ao ativar janela: {e}")
            return False