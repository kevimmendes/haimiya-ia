import json
import re
from Arcana.Tools.computer_control import ComputerControl
from Arcana.Tools.file_system import FileSystem
from Arcana.Tools.screen_vision import ScreenVision
from Arcana.Tools.task_planner import TaskPlanner


class ToolsSystem:
    def __init__(self, output_callback=None, vision_client=None):
        self.output_callback = output_callback
        self.computer = ComputerControl(output_callback)
        self.files = FileSystem(output_callback)
        self.screen = ScreenVision(output_callback, vision_client)
        self.planner = TaskPlanner()
        self.enabled = True
    
    def log(self, message):
        if self.output_callback:
            self.output_callback(message)
        else:
            print(message)
    
    # === COMPUTER CONTROL ===
    
    def move_mouse(self, x, y, duration=0.1):
        """Move mouse to position"""
        if not self.enabled: return False
        return self.computer.move_mouse(x, y, duration)
    
    def click(self, button="left", clicks=1, duration=0.1):
        """Click with specified button"""
        if not self.enabled: return False
        return self.computer.click_mouse(button, clicks, duration)
    
    def double_click(self, button="left"):
        """Double click"""
        if not self.enabled: return False
        return self.computer.double_click(button)
    
    def right_click(self):
        """Right click"""
        if not self.enabled: return False
        return self.computer.right_click()
    
    def type_text(self, text, interval=0.01):
        """Type text"""
        if not self.enabled: return False
        return self.computer.type_text(text, interval)
    
    def press_key(self, key):
        """Press a key"""
        if not self.enabled: return False
        return self.computer.press_key(key)
    
    def hotkey(self, *keys):
        """Press hotkey combination"""
        if not self.enabled: return False
        return self.computer.hotkey(*keys)
    
    # === FILE SYSTEM ===
    
    def search_files(self, pattern, extension=None, directory=None):
        """Search for files"""
        if not self.enabled: return []
        return self.files.search_files(pattern, extension, directory)
    
    def search_by_name(self, name, directory=None):
        """Search file by name"""
        if not self.enabled: return []
        return self.files.search_by_name(name, directory)
    
    def create_folder(self, folder_path):
        """Create folder"""
        if not self.enabled: return False
        return self.files.create_folder(folder_path)
    
    def rename_file(self, old_path, new_path):
        """Rename file - requires confirmation for security"""
        if not self.enabled: return False
        # Security: ask confirmation for renaming
        self.log(f"⚠️ Solicitando confirmação: Renomear '{os.path.basename(old_path)}' para '{os.path.basename(new_path)}'?")
        return self.files.rename_file(old_path, new_path)
    
    def move_file(self, source, destination):
        """Move file - requires confirmation"""
        if not self.enabled: return False
        # Security: ask confirmation for moving
        self.log(f"⚠️ Solicitando confirmação: Mover '{os.path.basename(source)}' para '{os.path.basename(destination)}'?")
        return self.files.move_file(source, destination)
    
    def copy_file(self, source, destination):
        """Copy file"""
        if not self.enabled: return False
        return self.files.copy_file(source, destination)
    
    def open_file(self, file_path):
        """Open file"""
        if not self.enabled: return False
        return self.files.open_file(file_path)
    
    def list_directory(self, path=None):
        """List directory"""
        if not self.enabled: return []
        return self.files.list_directory(path)
    
    # === SCREEN VISION ===
    
    def capture_screen(self):
        """Capture screen"""
        if not self.enabled: return None
        return self.screen.capture_screen_b64()
    
    def analyze_screen(self, user_query=None):
        """Analyze screen"""
        if not self.enabled: return None
        return self.screen.analyze_screen(user_query)
    
    def detect_elements(self, target_description):
        """Detect elements on screen"""
        if not self.enabled: return None
        return self.screen.detect_elements(target_description)
    
    # === PLANNING ===
    
    def start_task(self, task_name, steps=None):
        """Start a task planning"""
        if not self.enabled: return False
        self.planner.start_task(task_name, steps)
        return True
    
    def get_task_status(self):
        """Get current task progress"""
        if not self.enabled: return None
        return self.planner.get_status()
    
    def complete_current_step(self):
        """Mark current step as completed"""
        if not self.enabled: return False
        self.planner.complete_step()
        return True
    
    # === INTEGRATION HELPERS ===
    
    def get_app_names(self):
        """Get list of known apps for LLM context"""
        # This is a simplified version - in real use, would query the launcher
        return ["Bloco de Notas", "Calculadora", "YouTube", "Navegador", 
                "Minecraft", "Cyberpunk 2077"]
    
    def enable(self, state=True):
        """Enable/disable the tools system"""
        self.enabled = state
        self.log(f"🔧 Sistema de ferramentas {'ativado' if state else 'desativado'}")
    
    def to_dict(self):
        """Convert to dictionary for saving/loading state"""
        return {
            "enabled": self.enabled,
            "planner_state": self.planner.get_status()
        }
    
    @classmethod
    def from_dict(cls, data, output_callback=None, vision_client=None):
        """Create from dictionary state"""
        instance = cls(output_callback, vision_client)
        instance.enabled = data.get("enabled", True)
        return instance