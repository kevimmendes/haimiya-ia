import tkinter as tk
from tkinter import ttk, scrolledtext
import os
import re
import threading
import time
import logging
import keyboard
import subprocess
import psutil
import winsound

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

class AppLauncher:
    def __init__(self, output_callback=None):
        self.output_callback = output_callback
        self.gui_root = None
        self.enabled = True
      
        # ==========================================
        # 📂 DICIONÁRIO DE APPS (LÓGICA CMD INVISÍVEL)
        # ==========================================
        self.apps = {
            "Minecraft": {
                "target": "minecraft:",
                "aliases": ["jogo do bloco", "jogo quadrado", "farm", "aini", "minecraft bedrock", "mine"],
                "process_names": ["Minecraft.Windows.exe"],
                "allow_multiple": False
            },

            "Cyberpunk 2077": {
                "target": '"" "D:\\SteamLibrary\\steamapps\\common\\Cyberpunk 2077\\bin\\x64\\Cyberpunk2077.exe"',
                "aliases": ["2077", "cyberpunk", "jogo do doente", "night city", "dar uns tiros"],
                "process_names": ["Cyberpunk2077.exe"],
                "allow_multiple": False
            },

            "bloco de notas": {
                "target": "notepad",
                "aliases": ["anotações", "notas", "editor de texto", "notepad", "escrever"],
                "process_names": ["notepad.exe"],
                "allow_multiple": True
            },

            "calculadora": {
                "target": "calc",
                "aliases": ["números", "cálculo", "calculadora", "contas"],
                "process_names": ["calculator.exe", "calc.exe", "CalculatorApp.exe"],
                "allow_multiple": True
            },

            "youtube": {
                "target": "https://www.youtube.com",
                "aliases": ["vídeos", "ver vídeo", "site do youtube", "youtube", "assistir algo"],
                "process_names": [], 
                "allow_multiple": True
            },

            "navegador": {
                "target": "https://www.google.com",
                "aliases": ["google", "pesquisar", "web", "internet", "browser", "navegador", "chrome", "edge"],
                "process_names": ["chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "brave.exe"],
                "allow_multiple": True
            }
        }

    # 🔥 MÉTODO NOVO: Fica dentro da classe AppLauncher!
    def obter_nomes_dos_apps(self):
        # Retorna apenas os nomes (chaves) em formato de texto limpo
        return ", ".join(self.apps.keys())

    def log(self, message):
        if self.output_callback:
            self.output_callback(message)
        else:
            print(message)

    def find_app(self, command):
        if not command: return None, None
        command = command.lower().strip()
        
        for app_name, app_data in self.apps.items():
            if command == app_name.lower() or command in [a.lower() for a in app_data.get('aliases', [])]:
                return app_name, app_data['target']
        
        last_words = ' '.join(command.split()[-2:])
        for app_name, app_data in self.apps.items():
            if last_words in app_name.lower() or any(last_words in a.lower() for a in app_data.get('aliases', [])):
                return app_name, app_data['target']
        
        return None, None

    def is_app_running(self, app_name):
        if app_name not in self.apps: return False
        process_names = self.apps[app_name].get('process_names', [])
        if not process_names: return False 

        for proc in psutil.process_iter(['name']):
            try:
                proc_name = proc.info['name'].lower()
                for target_name in process_names:
                    if target_name.lower() in proc_name:
                        return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    def close_app(self, app_name):
        try:
            closed = False
            for proc in psutil.process_iter(['name']):
                try:
                    proc_name = proc.info['name'].lower()
                    for target_name in self.apps[app_name].get('process_names', []):
                        if target_name.lower() in proc_name:
                            proc.terminate()
                            closed = True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return closed
        except Exception as e:
            self.log(f"❌ Erro ao fechar {app_name}: {e}")
            return False

    def open_app_cmd(self, app_name, target):
        try:
            subprocess.Popen(f'start {target}', shell=True)
            return True
        except Exception as e:
            self.log(f"❌ Erro ao abrir {app_name}: {str(e)}")
            return False

    # =======================================================
    # PONTE COM A LLM (O CÉREBRO DA REM) COM FEEDBACK DE MEMÓRIA
    # =======================================================
    def process_llm_tag(self, llm_response):
        """Procura tags <APP:acao:alvo:parametro> na resposta da IA, executa todas e retorna o status compilado."""
        if not self.enabled:
            return None

        import urllib.parse 
        import webbrowser

        # Regex aprimorada e permissiva. Aceita:
        # <APP:abrir:calculadora>
        # <APP:abrir:calculadora:> (ignorando os dois pontos extras no final)
        # <APP:abrir:youtube:musica triste>
        tags_encontradas = re.findall(r'<APP:\s*(abrir|fechar)\s*:\s*([^>:]+)(?::([^>]*))?>', llm_response, re.IGNORECASE)
        
        if not tags_encontradas:
            return None

        resultados = []

        for match in tags_encontradas:
            action = match[0].lower().strip()
            app_raw = match[1].lower().strip()
            # Limpa o parâmetro e garante que não pegou "vazio" por causa do dois pontos extra
            param = match[2].strip() if match[2] and match[2].strip() else None

            self.log(f"⚙️ Tag LLM detectada -> Ação: {action.upper()} | Alvo: {app_raw} | Param: {param}")

            app_name, target = self.find_app(app_raw)
            
            if not app_name:
                erro_msg = f"❌ Erro: O aplicativo '{app_raw}' não foi encontrado no dicionário."
                self.log(f"⚠️ [Sistema] {erro_msg}")
                resultados.append(erro_msg)
                continue

            is_running = self.is_app_running(app_name)

            if action == "abrir":
                # --- MÁGICA DO YOUTUBE ---
                if app_name.lower() == "youtube":
                    if param:
                        busca_formatada = urllib.parse.quote(param)
                        target = f"https://www.youtube.com/results?search_query={busca_formatada}"
                    else:
                        target = "https://www.youtube.com"
                    
                    webbrowser.open(target)
                    msg = f"✅ Sucesso: O YouTube foi aberto pesquisando por '{param}'." if param else "✅ Sucesso: O YouTube foi aberto."
                    self.log(msg)
                    resultados.append(msg)

                # --- MÁGICA DO NAVEGADOR (GOOGLE) ---
                elif app_name.lower() == "navegador":
                    if param:
                        busca_formatada = urllib.parse.quote_plus(param)
                        target = f"https://www.google.com/search?q={busca_formatada}"
                    else:
                        target = "https://www.google.com"
                    
                    webbrowser.open(target)
                    msg = f"✅ Sucesso: O Navegador foi aberto pesquisando por '{param}'." if param else "✅ Sucesso: O Navegador foi aberto."
                    self.log(msg)
                    resultados.append(msg)

                # --- ABRIR PROGRAMAS E JOGOS NO PC ---
                else:
                    if is_running and not self.apps[app_name].get('allow_multiple', True):
                        info_msg = f"ℹ️ Info: O aplicativo '{app_name}' já está aberto."
                        self.log(f"ℹ️ [Sistema] {info_msg}")
                        resultados.append(info_msg)
                    
                    elif self.open_app_cmd(app_name, target):
                        sucesso_msg = f"✅ Sucesso: O aplicativo '{app_name}' foi aberto com sucesso no PC."
                        self.log(sucesso_msg)
                        resultados.append(sucesso_msg)
                    else:
                        resultados.append(f"❌ Erro crítico: Falha ao tentar abrir o '{app_name}'.")

            elif action == "fechar":
                if not is_running and self.apps[app_name].get('process_names'):
                    info_msg = f"ℹ️ Info: O aplicativo '{app_name}' já estava fechado."
                    self.log(f"ℹ️ [Sistema] {info_msg}")
                    resultados.append(info_msg)
                
                elif self.close_app(app_name):
                    sucesso_msg = f"✅ Sucesso: O aplicativo '{app_name}' foi encerrado com sucesso."
                    self.log(sucesso_msg)
                    resultados.append(sucesso_msg)
                else:
                    resultados.append(f"❌ Erro crítico: Falha ao tentar fechar o '{app_name}'.")

        # Retorna todas as ações realizadas em um único bloco de texto para a Rem processar
        return "\n".join(resultados) if resultados else None

class AppLauncherGUI:
    def __init__(self, root, launcher_instance):
        self.root = root
        self.launcher = launcher_instance
        self.root.title("Rem - App Launcher (Módulo LLM)")
        self.root.geometry("500x350")
        self.root.configure(bg="#1e1e2e")
        self.launcher.output_callback = self.add_to_log
        
        self.setup_styles()
        self.create_widgets()
        
        self.add_to_log("=== Módulo AppLauncher Ativo ===")
        self.add_to_log("Integrado com o Brain. Aguardando tags da LLM e avaliando intenções...")
        
    def setup_styles(self):
        self.style = ttk.Style()
        self.style.configure("TFrame", background="#1e1e2e")
        self.style.configure("TLabel", background="#1e1e2e", foreground="#cdd6f4", font=("Segoe UI", 10))
        self.style.configure("TButton", font=("Segoe UI", 9, "bold"))
        self.style.configure("Title.TLabel", font=("Segoe UI", 12, "bold"), foreground="#89b4fa")
        self.style.configure("Status.TLabel", font=("Segoe UI", 9, "italic"), foreground="#a6e3a1")
        
    def create_widgets(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        header = ttk.Frame(main_frame)
        header.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header, text="Rem - Sistema de Automação", style="Title.TLabel").pack(side=tk.LEFT)
        
        self.status_label = ttk.Label(header, text="Status: Online", style="Status.TLabel")
        self.status_label.pack(side=tk.RIGHT)
        
        self.log_area = scrolledtext.ScrolledText(
            main_frame, bg="#313244", fg="#cdd6f4", font=("Consolas", 9), height=10
        )
        self.log_area.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.log_area.config(state=tk.DISABLED)
        
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)
        self.btn_toggle = ttk.Button(btn_frame, text="Desativar Automação", command=self.toggle_system)
        self.btn_toggle.pack(side=tk.LEFT)

    def add_to_log(self, message):
        self.log_area.config(state=tk.NORMAL)
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state=tk.DISABLED)

    def toggle_system(self):
        if self.launcher.enabled:
            self.launcher.enabled = False
            self.status_label.config(text="Status: Offline", foreground="#f38ba8")
            self.btn_toggle.config(text="Ativar Automação")
            self.add_to_log("⚠️ AppLauncher desativado. A IA não abrirá mais programas.")
        else:
            self.launcher.enabled = True
            self.status_label.config(text="Status: Online", foreground="#a6e3a1")
            self.btn_toggle.config(text="Desativar Automação")
            self.add_to_log("✅ AppLauncher reativado.")

if __name__ == "__main__":
    root = tk.Tk()
    launcher = AppLauncher()
    AppLauncherGUI(root, launcher)
    root.mainloop()