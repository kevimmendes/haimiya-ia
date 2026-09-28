import json
from datetime import datetime

class TaskPlanner:
    def __init__(self):
        self.current_task = None
        self.task_progress = 0
        self.current_step_index = 0
        self.steps = []
        self.task_history = []
    
    def start_task(self, task_name, steps=None):
        """Start a new task with optional steps"""
        self.current_task = task_name
        self.task_progress = 0
        self.current_step_index = 0
        
        if steps is None:
            # Default generic steps based on task type
            steps = self._get_default_steps(task_name)
        
        self.steps = steps
        self.task_history.append({
            "task": task_name,
            "started": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "steps": steps.copy()
        })
        
        self.log(f"📋 Tarefa iniciada: '{task_name}'")
        self.log(f"   Passos: {len(steps)} etapas definidas")
    
    def _get_default_steps(self, task_name):
        """Get default steps based on task type"""
        task_lower = task_name.lower()
        
        if "capacapa" in task_lower or "álbum" in task_lower or "capa" in task_lower:
            return [
                "Entender o conceito da capa",
                "Pesquisar referências e inspirações",
                "Abrir Photoshop ou editor de imagens",
                "Criar documento com dimensões adequadas",
                "Criar elementos visuais (textos, imagens, shapes)",
                "Organizar layers e grupos",
                "Aplicar efeitos e ajustes",
                "Salvar projeto",
                "Exportar imagem final"
            ]
        elif "programar" in task_lower or "code" in task_lower:
            return [
                "Entender o requisito da funcionalidade",
                "Pesquisar soluções ou bibliotecas necessárias",
                "Escrever o código",
                "Testar o código",
                "Depurar erros",
                "Documentar o código"
            ]
        elif "organizar" in task_lower:
            return [
                "Identificar o que organizar",
                "Categorizar itens",
                "Criar estrutura de pastas",
                "Mover/renomear arquivos",
                "Verificar organização"
            ]
        else:
            return [
                "Entender o objetivo",
                "Planeiar as etapas necessárias",
                "Executar primeira etapa",
                "Verificar progresso",
                "Continuar ou ajustar plano"
            ]
    
    def log(self, message):
        print(f"[Planner] {message}")
    
    def add_step(self, step_description, completed=False):
        """Add a step to the current task"""
        if self.current_step_index < len(self.steps):
            self.steps[self.current_step_index] = f"{step_description} {'✓' if completed else ''}"
    
    def next_step(self):
        """Move to next step"""
        if self.current_step_index < len(self.steps) - 1:
            self.current_step_index += 1
            self.task_progress = int((self.current_step_index + 1) / len(self.steps) * 100)
            return True
        return False
    
    def previous_step(self):
        """Move to previous step"""
        if self.current_step_index > 0:
            self.current_step_index -= 1
            self.task_progress = int(self.current_step_index / len(self.steps) * 100)
            return True
        return False
    
    def complete_step(self):
        """Mark current step as completed"""
        if self.current_step_index < len(self.steps):
            self.steps[self.current_step_index] = self.steps[self.current_step_index].replace(
                self.steps[self.current_step_index].split()[-1], '✓'
            )
            self.task_progress = int((self.current_step_index + 1) / len(self.steps) * 100)
    
    def get_status(self):
        """Get current task status"""
        if not self.current_task:
            return None
        
        completed_steps = sum(1 for step in self.steps if '✓' in step)
        total_steps = len(self.steps)
        progress = int(completed_steps / total_steps * 100) if total_steps > 0 else 0
        
        current_step = self.steps[self.current_step_index] if self.steps else "Nenhum passo"
        
        return {
            "task": self.current_task,
            "progress": f"{progress}%",
            "current_step": current_step,
            "completed": completed_steps,
            "total": total_steps,
            "steps": self.steps
        }
    
    def finish_task(self):
        """Finish the current task"""
        status = self.get_status()
        if status:
            status["completed"] = status["total"]
            status["progress"] = "100%"
            status["current_step"] = "Tarefa concluída"
        
        self.task_history[-1]["completed"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.task_history[-1]["progress"] = status
        
        self.log(f"✅ Tarefa concluída: '{self.current_task}'")
        self.current_task = None
        self.steps = []
        self.current_step_index = 0
        
        return status