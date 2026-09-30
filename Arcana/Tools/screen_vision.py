import base64
import io
from PIL import ImageGrab

class ScreenVision:
    def __init__(self, output_callback=None, vision_client=None, vision_model=None,
                 vision_local=False):
        self.output_callback = output_callback
        self.vision_client = vision_client
        # Sem modelo definido nao ha como chamar a API: assume-se o mesmo
        # modelo de texto, que e' o que o run.py configura por omissao.
        self.vision_model = vision_model or "qwen/qwen3.8-27b"
        # Modelo local = CPU: captura menor e resposta curta, senao um
        # simples "descreve o ecra" demora mais de um minuto e meio.
        self.vision_local = vision_local
    
    def log(self, message):
        if self.output_callback:
            self.output_callback(message)
        else:
            print(message)
    
    def capture_screen_b64(self):
        """Capture screen and return as base64 string"""
        try:
            img = ImageGrab.grab()
            img.thumbnail((512, 512) if self.vision_local else (1024, 1024))
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=70)
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
        except Exception as e:
            self.log(f"❌ Erro ao capturar tela: {e}")
            return None
    
    def analyze_screen(self, user_query=None):
        """Analyze screen content using vision model"""
        if not self.vision_client:
            self.log("⚠️ Cliente de visão não disponível")
            return None
        
        b64_img = self.capture_screen_b64()
        if not b64_img:
            return None
        
        prompt_vision = "Descreva a imagem. Identifique contexto, textos, ações e detalhes."
        if user_query:
            prompt_vision += f"\nO usuário perguntou: '{user_query}'. Foque nisso."
        
        prompt_vision += "\nSeja conciso e direto."
        if self.vision_local:
            prompt_vision += "\nResponde SEMPRE em português, no máximo 2 frases curtas."
        
        try:
            res = self.vision_client.chat.completions.create(
                model=self.vision_model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_vision},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                    ]
                }],
                max_tokens=150 if self.vision_local else 1024,
                temperature=0.1
            )
            
            descricao = res.choices[0].message.content
            self.log("👁️ Análise de tela concluída")
            return descricao
        except Exception as e:
            self.log(f"❌ Erro na análise de tela: {e}")
            return None
    
    def detect_elements(self, target_description):
        """Detect specific elements on screen (buttons, menus, etc.)"""
        analysis = self.analyze_screen()
        if not analysis:
            return None
        
        # Simple keyword matching for element detection
        target_lower = target_description.lower()
        found_elements = []
        
        # Look for common UI elements
        element_keywords = {
            "botão": ["botão", "button"],
            "menu": ["menu", "arquivo", "editar"],
            "caixa de texto": ["caixa", "texto", "input", "field"],
            "icone": ["icone", "icon"],
            "salvar": ["salvar", "save"],
            "copiar": ["copiar", "copy"],
            "colar": ["colar", "paste"],
        }
        
        for element, keywords in element_keywords.items():
            for kw in keywords:
                if kw.lower() in analysis.lower() and kw.lower() in target_lower:
                    found_elements.append(element)
                    break
        
        return found_elements if found_elements else None