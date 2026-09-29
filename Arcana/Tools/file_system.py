import os
import shutil
from pathlib import Path

from Arcana import platform_shim

class FileSystem:
    def __init__(self, output_callback=None):
        self.output_callback = output_callback
    
    def log(self, message):
        if self.output_callback:
            self.output_callback(message)
        else:
            print(message)
    
    # File search
    def search_files(self, pattern, extension=None, directory=None):
        """Search for files matching pattern, optionally by extension and directory"""
        try:
            if directory is None:
                directory = os.getcwd()
            
            results = []
            pattern_lower = pattern.lower()
            
            for root, dirs, files in os.walk(directory):
                for file in files:
                    file_path = os.path.join(root, file)
                    
                    # Check extension if specified
                    if extension:
                        if not file.lower().endswith(extension.lower()):
                            continue
                    
                    # Check pattern in filename
                    if pattern_lower in file.lower():
                        results.append(file_path)
                    
                    # Also check pattern in path
                    if pattern_lower in root.lower():
                        results.append(file_path)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_results = []
            for r in results:
                if r not in seen:
                    seen.add(r)
                    unique_results.append(r)
            
            self.log(f"📁 Encontrados {len(unique_results)} arquivos com padrão '{pattern}'")
            return unique_results
        except Exception as e:
            self.log(f"❌ Erro ao buscar arquivos: {e}")
            return []
    
    def search_by_name(self, name, directory=None):
        """Search for file by exact name"""
        return self.search_files(name, directory=directory)
    
    # Folder operations
    def create_folder(self, folder_path):
        """Create a new folder"""
        try:
            os.makedirs(folder_path, exist_ok=True)
            self.log(f"📂 Pasta criada: '{folder_path}'")
            return True
        except Exception as e:
            self.log(f"❌ Erro ao criar pasta '{folder_path}': {e}")
            return False
    
    def rename_file(self, old_path, new_path):
        """Rename a file"""
        try:
            os.rename(old_path, new_path)
            self.log(f"📝 Arquivo renomeado: '{old_path}' -> '{new_path}'")
            return True
        except Exception as e:
            self.log(f"❌ Erro ao renomear arquivo: {e}")
            return False
    
    def move_file(self, source, destination):
        """Move a file to a destination"""
        try:
            # Ensure destination directory exists
            dest_dir = os.path.dirname(destination)
            os.makedirs(dest_dir, exist_ok=True)
            
            shutil.move(source, destination)
            self.log(f"📤 Arquivo movido: '{source}' -> '{destination}'")
            return True
        except Exception as e:
            self.log(f"❌ Erro ao mover arquivo: {e}")
            return False
    
    def copy_file(self, source, destination):
        """Copy a file to a destination"""
        try:
            dest_dir = os.path.dirname(destination)
            os.makedirs(dest_dir, exist_ok=True)
            
            shutil.copy2(source, destination)
            self.log(f"📋 Arquivo copiado: '{source}' -> '{destination}'")
            return True
        except Exception as e:
            self.log(f"❌ Erro ao copiar arquivo: {e}")
            return False
    
    # File operations
    def open_file(self, file_path):
        """Open a file with default application"""
        try:
            if os.path.exists(file_path):
                if not platform_shim.abrir_caminho(file_path):
                    self.log(f"⚠️ Sem forma de abrir ficheiros: instala 'xdg-utils'.")
                    return False
                self.log(f"📄 Arquivo aberto: '{file_path}'")
                return True
            self.log(f"⚠️ Arquivo não encontrado: '{file_path}'")
            return False
        except Exception as e:
            self.log(f"❌ Erro ao abrir arquivo: {e}")
            return False
    
    # Directory operations
    def list_directory(self, path=None):
        """List files in a directory"""
        try:
            if path is None:
                path = os.getcwd()
            
            items = os.listdir(path)
            self.log(f"📂 Conteúdo da pasta '{path}':")
            for item in items:
                item_path = os.path.join(path, item)
                if os.path.isdir(item_path):
                    self.log(f"  📁 {item}/")
                else:
                    self.log(f"  📄 {item}")
            return items
        except Exception as e:
            self.log(f"❌ Erro ao listar diretório: {e}")
            return []