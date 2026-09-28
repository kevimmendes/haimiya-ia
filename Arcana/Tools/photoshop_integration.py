class PhotoshopIntegration:
    """Integração com o Adobe Photoshop no Windows.

    Estratégia em 2 camadas:
      1. Bridge oficial via COM (win32com.client) + ExtendScript (DoJavaScript)
         - método fiável, dá acesso a toda a API do Photoshop
      2. Fallback por automação de UI (pyautogui) quando o COM não responde

    Todos os imports são preguiçosos para que a app arranque mesmo sem Photoshop.
    """

    def __init__(self, output_callback=None, computer=None):
        self.output_callback = output_callback
        self.computer = computer
        self._app = None
        self.PROGRAM_ID = "Photoshop.Application"

    def log(self, message):
        if self.output_callback:
            self.output_callback(message)
        else:
            print(message)

    # ======================================================
    # LIGACAO
    # ======================================================
    def ligar(self, visivel=True):
        try:
            import win32com.client
            if self._app is None:
                self._app = win32com.client.Dispatch(self.PROGRAM_ID)
            try:
                self._app.Visible = visivel
            except Exception:
                pass
            self.log("[PS] Photoshop ligado via COM.")
            return True
        except Exception as e:
            self.log(f"[PS] COM indisponivel ({e}). A usar automacao de interface.")
            return False

    def esta_aberto(self):
        if self._app is not None:
            return True
        try:
            import psutil
            for p in psutil.process_iter(["name"]):
                if "photoshop" in (p.info["name"] or "").lower():
                    return True
        except Exception:
            pass
        return False

    def abrir(self):
        try:
            import subprocess
            alvos = [
                r"C:\Program Files\Adobe\Adobe Photoshop 2025\Photoshop.exe",
                r"C:\Program Files\Adobe\Adobe Photoshop 2024\Photoshop.exe",
                r"C:\Program Files\Adobe\Adobe Photoshop 2023\Photoshop.exe",
                r"C:\Program Files\Adobe\Adobe Photoshop 2026\Photoshop.exe",
            ]
            for a in alvos:
                try:
                    subprocess.Popen([a])
                    self.log(f"[PS] Photoshop iniciado a partir de {a}")
                    return True
                except Exception:
                    continue
            import os
            for raiz in [r"C:\Program Files\Adobe", r"C:\Program Files (x86)\Adobe"]:
                if not os.path.isdir(raiz):
                    continue
                for pasta in os.listdir(raiz):
                    if "photoshop" in pasta.lower():
                        exe = os.path.join(raiz, pasta, "Photoshop.exe")
                        if os.path.exists(exe):
                            subprocess.Popen([exe])
                            self.log(f"[PS] Photoshop iniciado a partir de {exe}")
                            return True
            self.ligar()
            return self._app is not None
        except Exception as e:
            self.log(f"[PS] Erro ao abrir Photoshop: {e}")
            return self.ligar()

    def fechar(self, guardar=False):
        if self._app is not None:
            try:
                self._app.Quit(2 if guardar else 1)
                self.log("[PS] Photoshop fechado.")
                self._app = None
                return True
            except Exception as e:
                self.log(f"[PS] Erro ao fechar: {e}")
                return False
        try:
            import psutil
            for p in psutil.process_iter(["name"]):
                if "photoshop" in (p.info["name"] or "").lower():
                    p.terminate()
            self.log("[PS] Photoshop terminado.")
            return True
        except Exception as e:
            self.log(f"[PS] Erro: {e}")
            return False

    # ======================================================
    # PONTE ExtendScript
    # ======================================================
    def js(self, codigo, fallback_ui=None):
        """Corre ExtendScript dentro do Photoshop. Cai para UI se o COM falhar."""
        if self.ligar():
            try:
                res = self._app.DoJavaScript(codigo)
                return res
            except Exception as e:
                self.log(f"[PS] ExtendScript falhou: {e}")
        if fallback_ui and self.computer:
            try:
                return fallback_ui()
            except Exception as e:
                self.log(f"[PS] Fallback de interface tambem falhou: {e}")
        return None

    # ======================================================
    # DOCUMENTO
    # ======================================================
    def criar_documento(self, largura=1920, altura=1080, resolucao=72, nome="Documento", cor="FFFFFF"):
        def _js():
            return (
                'var d = app.documents.add('
                f'{int(largura)}, {int(altura)}, {int(resolucao)}, "{nome}", NewDocumentMode.RGB, DocumentFill.WHITE);'
                f'app.foregroundColor.rgb.red = {self._hex(cor, 0)};'
                f'app.foregroundColor.rgb.green = {self._hex(cor, 1)};'
                f'app.foregroundColor.rgb.blue = {self._hex(cor, 2)};'
                'd.name = "' + nome + '";'
                '"ok"'
            )
        res = self.js(_js())
        if res:
            self.log(f"[PS] Documento criado: {largura}x{altura} @ {resolucao}ppi, nome '{nome}'")
            return True
        self.log("[PS] Nao foi possivel criar o documento (Photoshop fechado ou COM bloqueado).")
        return False

    def fechar_documento(self, guardar=False):
        return self.js(
            'if (app.documents.length > 0) { app.activeDocument.close('
            + ('SaveOptions.SAVECHANGES' if guardar else 'SaveOptions.DONOTSAVECHANGES') + '); "ok" } else { "vazio" }'
        ) is not None

    def estado(self):
        """Lê o estado real do Photoshop: documento, layers, dimensões."""
        script = (
            'if (app.documents.length === 0) { "sem documento" } else {'
            'var d = app.activeDocument;'
            'var nomes = []; for (var i=0; i<d.artLayers.length; i++) { nomes.push(d.artLayers[i].name); }'
            '"doc=" + d.name + " | " + d.width.as("px") + "x" + d.height.as("px") + '
            '| layers=" + nomes.length + " | " + nomes.join(" >> ") }'
        )
        res = self.js(script)
        if res:
            self.log(f"[PS] Estado: {res}")
            return res
        return "Photoshop nao esta ligado"

    # ======================================================
    # LAYERS
    # ======================================================
    def criar_layer(self, nome="Layer"):
        res = self.js(
            'if (app.documents.length === 0) { "sem doc" } else {'
            f'var l = app.activeDocument.artLayers.add(); l.name = "{nome}"; "ok" }}'
        )
        if res == "ok":
            self.log(f"[PS] Layer criada: '{nome}'")
            return True
        self.log(f"[PS] Nao foi possivel criar a layer '{nome}'.")
        return False

    def renomear_layer(self, antigo, novo):
        res = self.js(
            'if (app.documents.length === 0) { "sem doc" } else {'
            'var d = app.activeDocument, achou = false;'
            'for (var i=0; i<d.artLayers.length; i++) {'
            f'  if (d.artLayers[i].name == "{antigo}") {{ d.artLayers[i].name = "{novo}"; achou = true; }} }}'
            'achou ? "ok" : "nao encontrada" }'
        )
        ok = res == "ok"
        self.log(f"[PS] Layer '{antigo}' -> '{novo}': {'renomeada' if ok else 'nao encontrada'}")
        return ok

    def duplicar_layer(self, nome="Layer", vezes=1):
        res = self.js(
            'if (app.documents.length === 0) { "sem doc" } else {'
            f'var d = app.activeDocument; var base = d.artLayers[d.artLayers.length-1];'
            f'for (var i=1; i<={int(vezes)}; i++) {{ var c = base.duplicate(); c.name = "{nome} " + i; }} "ok" }}'
        )
        if res == "ok":
            self.log(f"[PS] Layer '{nome}' duplicada x{vezes}")
            return True
        return False

    def ordernar_layers(self, criterio="topo"):
        """Organiza layers: 'topo' (ordem de leitura) ou 'nome' (alfabetica)."""
        if criterio == "nome":
            script = (
                'var d = app.activeDocument; var nomes = [];'
                'for (var i=0; i<d.artLayers.length; i++) { nomes.push(d.artLayers[i].name); }'
                'nomes.sort(); var y = 0;'
                'for (var i=0; i<d.artLayers.length; i++) { d.artLayers[i].name = nomes[i]; }'
                'while (d.artLayers.length > 1) { d.artLayers[0].move(d.artLayers[0], ElementPlacement.PLACEAFTER); }'
                '"ok"'
            )
        else:
            script = (
                'var d = app.activeDocument;'
                'for (var i = d.artLayers.length - 1; i > 0; i--) {'
                '  d.artLayers[i].move(d.artLayers[i], ElementPlacement.PLACEAFTER); } "ok"'
            )
        res = self.js(script)
        if res == "ok":
            self.log(f"[PS] Layers organizadas por '{criterio}'.")
            return True
        return False

    def ocultar_layer(self, nome, esconder=True):
        res = self.js(
            'if (app.documents.length === 0) { "sem doc" } else {'
            'var d = app.activeDocument; for (var i=0; i<d.artLayers.length; i++) {'
            f'  if (d.artLayers[i].name == "{nome}") {{ d.artLayers[i].visible = {str(not esconder).lower()}; "ok" }} }} "nao encontrada"'
        )
        return res == "ok"

    def apagar_layer(self, nome, confirmar=False):
        """DESTRUTIVO - remover layer. So executa se confirmar=True."""
        if not confirmar:
            self.log(f"Atencao: confirmar apagar a layer '{nome}'? Responde 'sim' para executar.")
            return "AGUARDA_CONFIRMACAO"
        res = self.js(
            'if (app.documents.length === 0) { "sem doc" } else {'
            'var d = app.activeDocument; for (var i=0; i<d.artLayers.length; i++) {'
            f'  if (d.artLayers[i].name == "{nome}") {{ d.artLayers[i].remove(); "ok" }} }} "nao encontrada"'
        )
        if res == "ok":
            self.log(f"[PS] Layer '{nome}' apagada.")
            return True
        return False

    def agrupar_layers(self, nome="Grupo"):
        res = self.js(
            'if (app.documents.length < 1) { "sem doc" } else {'
            'var s = app.activeDocument.selection; s.selectAll(); s.deselect();'
            f'var g = app.activeDocument.layerSets.add(); g.name = "{nome}"; "ok" }}'
        )
        if res == "ok":
            self.log(f"[PS] Grupo '{nome}' criado.")
            return True
        return False

    # ======================================================
    # DESENHO
    # ======================================================
    def forma(self, tipo="retangulo", x=0, y=0, largura=400, altura=300, cor=None, cantos=0):
        """Desenha uma forma solida na layer ativa via ExtendScript."""
        if cor:
            setcor = (
                f'app.foregroundColor.rgb.red = {self._hex(cor, 0)};'
                f'app.foregroundColor.rgb.green = {self._hex(cor, 1)};'
                f'app.foregroundColor.rgb.blue = {self._hex(cor, 2)};'
            )
        else:
            setcor = ""

        x = int(x); y = int(y); largura = int(largura); altura = int(altura)

        if tipo in ("circulo", "elipse", "ovalo", "ellipse"):
            metodo = (
                f'var s = new ShapeSubType(); s.type = ShapeSubType.ELLIPSE;'
                f'var ref = new ActionReference();'
                f'function f(ref) {{ var d = ref.putEnumerated(sTID, sID, pTID); return executeAction(sTID, d, DialogModes.NO); }}'
                f'function tID(type) {{ var tid = app.charIDToTypeID(type); return tid; }}'
                f'function sTID() {{ return tID("null"); }}'
                f'function pTID() {{ return tID("Lyr "); }}'
                f'function sID() {{ return tID("null"); }}'
                f'var desc = new ActionDescriptor();'
                f'desc.putPath(charIDToTypeID("null"), new FolderPathOptions);'
                f'f(ref);'
            )
            # fallback mais simples e fiável via pathItems
            script = (
                'if (app.documents.length === 0) { "sem doc" } else {' + setcor +
                f'var d = app.activeDocument; var d2 = d.width.as("px"); var d3 = d.height.as("px");'
                f'var w = Math.min({largura}, d2 - {x}); var h = Math.min({altura}, d3 - {y});'
                f'var p = d.pathItems.ellipse([{x},{y}], [{x+w},{y+h}]);'
                f'p.filled = true; p.fillColor = app.foregroundColor; p.remove(); "ok" }}'
            )
        elif tipo in ("linha", "line"):
            script = (
                'if (app.documents.length === 0) { "sem doc" } else {' + setcor +
                f'var p = app.activeDocument.pathItems.add([{x},{y}]);'
                f'p.lineTo([{x+largura},{y+altura}]); p.stroked = false; p.remove(); "ok" }}'
            )
        else:
            raio = int(cantos) if tipo in ("retangulo_arredondado", "arredondado") else 0
            script = (
                'if (app.documents.length === 0) { "sem doc" } else {' + setcor +
                f'var d = app.activeDocument; var d2 = d.width.as("px"); var d3 = d.height.as("px");'
                f'var w = Math.min({largura}, d2 - {x}); var h = Math.min({altura}, d3 - {y});'
                f'var p = d.pathItems.rectangle([{x},{y}], [{x+w},{y+h}], {raio});'
                f'p.filled = true; p.fillColor = app.foregroundColor; p.remove(); "ok" }}'
            )

        res = self.js(script)
        if res == "ok":
            self.log(f"[PS] Forma '{tipo}' desenhada em ({x},{y}) {largura}x{altura}.")
            return True
        self.log(f"[PS] Nao foi possivel desenhar a forma '{tipo}'.")
        return False

    def texto(self, conteudo, x=100, y=100, tamanho=60, cor="000000", nome_layer="Texto"):
        res = self.js(
            'if (app.documents.length === 0) { "sem doc" } else {'
            f'app.foregroundColor.rgb.red = {self._hex(cor, 0)};'
            f'app.foregroundColor.rgb.green = {self._hex(cor, 1)};'
            f'app.foregroundColor.rgb.blue = {self._hex(cor, 2)};'
            f'var l = app.activeDocument.artLayers.add(); l.name = "{nome_layer}";'
            'l.kind = LayerKind.TEXT;'
            f'l.textItem.contents = "{conteudo}";'
            f'l.textItem.size = {float(tamanho)};'
            f'l.textItem.position = [{int(x)}, {int(y)}];'
            'app.activeDocument.activeLayer = l; "ok" }'
        )
        if res == "ok":
            self.log(f"[PS] Texto criado: '{conteudo}'")
            return True
        return False

    def escolher_cor(self, cor="FF0000"):
        res = self.js(
            f'app.foregroundColor.rgb.red = {self._hex(cor, 0)};'
            f'app.foregroundColor.rgb.green = {self._hex(cor, 1)};'
            f'app.foregroundColor.rgb.blue = {self._hex(cor, 2)}; "ok"'
        )
        return res == "ok"

    def definir_cor(self, cor, fundo=False):
        res = self.js(
            f'var c = app.{"backgroundColor" if fundo else "foregroundColor"};'
            f'c.rgb.red = {self._hex(cor, 0)}; c.rgb.green = {self._hex(cor, 1)}; c.rgb.blue = {self._hex(cor, 2)}; "ok"'
        )
        if res == "ok":
            self.log(f"[PS] Cor {'de fundo' if fundo else 'de frente'} definida: #{cor}")
            return True
        return False

    # ======================================================
    # SELECAO / FERRAMENTAS / EFEITOS
    # ======================================================
    def selecionar(self, tipo="tudo", x=0, y=0, largura=400, altura=300):
        tipos = {
            "tudo": "d.selection.selectAll();",
            "nada": "d.selection.deselect();",
            "retangulo": f"d.selection.select([[{int(x)},{int(y)}],[{int(x+largura)},{int(y+altura)}]]);",
            "elipse": (
                f"d.selection.select([[{int(x)},{int(y)}],[{int(x+largura/2)},{int(y+altura/2)}],"
                f"[{int(x+largura)},{int(y+altura)}]]);"
            ),
        }
        acao = tipos.get(tipo)
        if not acao:
            self.log(f"[PS] Selecao '{tipo}' desconhecida.")
            return False
        res = self.js('if (app.documents.length === 0) { "sem doc" } else { var d = app.activeDocument; ' + acao + ' "ok" }')
        if res == "ok":
            self.log(f"[PS] Selecao '{tipo}' aplicada.")
            return True
        return False

    def preencher(self, cor=None):
        if cor:
            self.definir_cor(cor)
        res = self.js(
            'if (app.documents.length === 0) { "sem doc" } else {'
            'if (app.activeDocument.selection.bounds[0] < 0) { d = app.activeDocument; d.selection.selectAll(); }'
            'app.activeDocument.fill(app.foregroundColor); "ok" }'
        )
        if res == "ok":
            self.log("[PS] Preenchimento aplicado.")
            return True
        return False

    def ferramenta(self, nome="move"):
        """Seleciona ferramenta pelo atalho de teclado do Photoshop (fallback UI)."""
        atalhos = {
            "move": "v", "mover": "v", "marquee": "m", "lasso": "l",
            "magic_wand": "w", "crop": "c", "eyedropper": "i", "pincel": "b",
            "brush": "b", "pencil": "b", "eraser": "e", "borracha": "e",
            "gradient": "g", "blur": "r", "sharpen": "s", "dodge": "o",
            "type": "t", "texto": "t", "shape": "u", "hand": "h", "zoom": "z",
        }
        tecla = atalhos.get(nome.lower())
        if not tecla:
            self.log(f"[PS] Ferramenta '{nome}' desconhecida.")
            return False
        if not self.computer:
            return False
        try:
            self.computer.activate_window("Adobe Photoshop")
            self.computer.press_key(tecla)
            self.log(f"[PS] Ferramenta '{nome}' selecionada.")
            return True
        except Exception as e:
            self.log(f"[PS] Erro ao trocar de ferramenta: {e}")
            return False

    def desfazer(self, vezes=1):
        if not self.computer:
            return False
        self.computer.activate_window("Adobe Photoshop")
        for _ in range(max(1, vezes)):
            self.computer.hotkey("ctrl", "z")
        self.log(f"[PS] Desfeito x{vezes}.")
        return True

    def efeito(self, nome, intensidade=50):
        """Aplica um filtro por nome via ExtendScript (blur, sharpen, gaussian, etc)."""
        filtros = {
            "blur": "d.applyGaussianBlur({radius: %d});" % intensidade,
            "desfoque": "d.applyGaussianBlur({radius: %d});" % intensidade,
            "gaussian_blur": "d.applyGaussianBlur({radius: %d});" % intensidade,
            "nitidez": "d.applyUnSharpMask({amount: %d, radius: 1.5, threshold: 0});" % intensidade,
            "sharpen": "d.applyUnSharpMask({amount: %d, radius: 1.5, threshold: 0});" % intensidade,
            "mosaico": "d.applyMosaic({horizontal: %d, vertical: %d});" % (max(2, intensidade // 5), max(2, intensidade // 5)),
            "pixelate": "d.applyMosaic({horizontal: %d, vertical: %d});" % (max(2, intensidade // 5), max(2, intensidade // 5)),
        }
        acao = filtros.get(nome.lower())
        if not acao:
            self.log(f"[PS] Efeito '{nome}' nao suportado via script. Use Photoshop para filtros avancados.")
            return False
        res = self.js(
            'if (app.documents.length === 0) { "sem doc" } else { var d = app.activeDocument; '
            + acao + ' "ok" }'
        )
        if res == "ok":
            self.log(f"[PS] Efeito '{nome}' aplicado.")
            return True
        return False

    def ajustar_niveis(self, entrada=0, saida=255):
        res = self.js(
            'if (app.documents.length === 0) { "sem doc" } else {'
            f'app.activeDocument.adjustLevels(LevelsAdjustment({{inputBlack: 0, inputWhite: 255, gamma: 1.0, outputBlack: {int(entrada)}, outputWhite: {int(saida)}}})); "ok" }}'
        )
        return res == "ok"

    def inverter_cores(self):
        res = self.js(
            'if (app.documents.length === 0) { "sem doc" } else {'
            'app.activeDocument.selection.selectAll();'
            'app.activeDocument.selection.invert(); app.activeDocument.selection.deselect(); "ok" }'
        )
        if res == "ok":
            self.log("[PS] Cores invertidas.")
            return True
        return False

    # ======================================================
    # GUARDAR
    # ======================================================
    def guardar(self, caminho=None, formato="psd"):
        if not caminho:
            res = self.js(
                'if (app.documents.length === 0) { "sem doc" } else {'
                'var f = app.activeDocument.fullName.fsName; "salvo:" + f }'
            )
            if res:
                self.log(f"[PS] Documento ja guardado: {res}")
                return True
            if self.computer:
                self.computer.activate_window("Adobe Photoshop")
                self.computer.hotkey("ctrl", "s")
                self.log("[PS] Ctrl+S enviado.")
                return True
            return False

        caminho = caminho.replace("\\", "/")
        if formato.lower() == "psd":
            script = 'd.saveAs(new File("' + caminho + '"), PhotoshopSaveOptions.PROJECT, true, Extension.LOWERCASE);'
        else:
            fmt = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP", "gif": "GIF", "tif": "TIFF", "tiff": "TIFF"}
            tipo = fmt.get(formato.lower(), "PNG")
            extras = {
                "JPEG": "d.saveAs(new File(\"" + caminho + "\"), PhotoshopSaveOptions.JPEG, true, Extension.LOWERCASE);",
                "PNG": "d.saveAs(new File(\"" + caminho + "\"), PhotoshopSaveOptions.PNG, true, Extension.LOWERCASE, true);",
            }
            script = extras.get(tipo, 'd.saveAs(new File("' + caminho + '"), PhotoshopSaveOptions.' + tipo + ', true, Extension.LOWERCASE);')

        res = self.js(
            'if (app.documents.length === 0) { "sem doc" } else { var d = app.activeDocument; ' + script + ' "ok" }'
        )
        if res == "ok":
            self.log(f"[PS] Guardado em {caminho}")
            return True
        self.log(f"[PS] Falha ao guardar em {caminho}")
        return False

    def exportar(self, caminho, formato="jpg", qualidade=90):
        caminho = caminho.replace("\\", "/")
        tipo = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP", "gif": "GIF"}.get(formato.lower(), "PNG")
        script = (
            'if (app.documents.length === 0) { "sem doc" } else { var d = app.activeDocument; var o = new PNGSaveOptions(); '
            f'd.saveAs(new File("{caminho}"), PhotoshopSaveOptions.{tipo}, true, Extension.LOWERCASE, true); "ok" }}'
        )
        res = self.js(script)
        if res == "ok":
            self.log(f"[PS] Exportado para {caminho} ({tipo})")
            return True
        return False

    def ajuda(self):
        return (
            "Photoshop: abrir | documento:LxA | layer:NOME | renomear:VELHO>NOVO | "
            "forma:tipo,x,y,l,a | texto:conteudo | cor:RRGGBB | selecionar:TIPO | "
            "preencher | efeito:blur | guardar:CAMINHO | exportar:CAMINHO.jpg | estado"
        )

    @staticmethod
    def _hex(cor, indice):
        try:
            c = cor.lstrip("#")
            if len(c) == 3:
                c = "".join(ch * 2 for ch in c)
            return int(c[indice * 2: indice * 2 + 2], 16)
        except Exception:
            return 255 if indice == 0 else 255
