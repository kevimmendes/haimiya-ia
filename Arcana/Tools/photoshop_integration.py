import os
import threading
import time


class PhotoshopIntegration:
    """Integração com o Adobe Photoshop no Windows.

    Estratégia em 2 camadas:
      1. Bridge oficial via COM (win32com.client) + ExtendScript (DoJavaScript)
         - método fiável, dá acesso a toda a API do Photoshop
      2. Fallback por automação de UI (pyautogui) quando o COM não responde

    Todos os imports são preguiçosos para que a app arranque mesmo sem Photoshop.

    NOTA SOBRE O ExtendScript: não se pode confiar no "completion value" de
    blocos if/else em JavaScript. Todo o script devolve o valor numa variavel
    `r` explicita e termina em `r;`, caso contrario o Photoshop lanca
    "Erro 23: nao possui um valor".
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
            return True
        except Exception:
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
        if self.ligar():
            self.log("[PS] Photoshop ligado.")
            return True
        try:
            import subprocess
            alvos = [
                r"C:\Program Files\Adobe\Adobe Photoshop 2025\Photoshop.exe",
                r"C:\Program Files\Adobe\Adobe Photoshop 2024\Photoshop.exe",
                r"C:\Program Files\Adobe\Adobe Photoshop 2023\Photoshop.exe",
                r"C:\Program Files\Adobe\Adobe Photoshop 2022\Photoshop.exe",
                r"C:\Program Files\Adobe\Adobe Photoshop 2026\Photoshop.exe",
            ]
            for a in alvos:
                if os.path.exists(a):
                    subprocess.Popen([a])
                    self.log(f"[PS] Photoshop iniciado a partir de {a}")
                    return True
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
            self.log("[PS] Photoshop nao encontrado nos caminhos habituais.")
            return False
        except Exception as e:
            self.log(f"[PS] Erro ao abrir Photoshop: {e}")
            return False

    def fechar(self, guardar=False):
        if self._app is not None:
            try:
                self._app.Quit(2 if guardar else 1)
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
            return True
        except Exception as e:
            self.log(f"[PS] Erro: {e}")
            return False

    # ======================================================
    # PONTE ExtendScript
    # ======================================================

    @staticmethod
    def _alerta_ps():
        """Procura o alerta modal do Photoshop (janela PSDialogBox) e carrega
        no botao de confirmacao.

        Um alerta destes bloqueia o COM para SEMPRE: o DoJavaScript so'
        volta quando alguem carrega em OK. Devolve o texto do alerta que se
        desbloqueou, ou None se nao havia nada.
        """
        try:
            import ctypes
            from ctypes import wintypes
            import psutil

            pid = None
            for p in psutil.process_iter(["name", "pid"]):
                if "photoshop" in (p.info["name"] or "").lower():
                    pid = p.info["pid"]
                    break
            if not pid:
                return None

            u = ctypes.windll.user32
            EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND,
                                          wintypes.LPARAM)
            janelas = []

            def ver(hwnd, _):
                dono = wintypes.DWORD()
                u.GetWindowThreadProcessId(hwnd, ctypes.byref(dono))
                if dono.value == pid:
                    cls = ctypes.create_unicode_buffer(64)
                    u.GetClassNameW(hwnd, cls, 64)
                    if cls.value == "PSDialogBox":
                        janelas.append(hwnd)
                return True

            u.EnumWindows(EnumProc(ver), 0)
            if not janelas:
                return None

            texto, alvo = None, None
            for h in janelas:
                filhos = []

                def ler(ch, _):
                    n = ctypes.create_unicode_buffer(1024)
                    u.GetWindowTextW(ch, n, 1024)
                    if n.value.strip():
                        filhos.append((ch, n.value.strip()))
                    return True

                u.EnumChildWindows(h, EnumProc(ler), 0)
                for ch, t in filhos:
                    alta = t.upper()
                    if alta in ("OK", "SIM", "YES", "S", "ENTRAR", "CONTINUAR"):
                        alvo = alvo or ch
                    elif alta in ("CANCELAR", "CANCEL", "NAO", "NÃO", "NO"):
                        alvo = alvo or ch
                    elif t != "Adobe Photoshop":
                        texto = t  # frase do alerta
            if alvo:
                u.SendMessageW(alvo, 0x00F5, 0, 0)  # BM_CLICK
                return texto or "(alerta sem texto)"
            return None
        except Exception:
            return None

    def _do_js(self, codigo):
        """DoJavaScript no fio principal, com um vigia de alertas a correr
        em paralelo. Devolve (estado, valor)."""
        parar = threading.Event()

        def vigiar():
            # enquanto o script corre, se o Photoshop abrir um alerta
            # modal este fio carrega em OK: senao o DoJavaScript fica'
            # bloqueado para sempre a espera do utilizador.
            while not parar.wait(0.5):
                texto = self._alerta_ps()
                if texto:
                    self.log(f"[PS] Alerta do Photoshop desbloqueado: {texto}")

        fio = threading.Thread(target=vigiar, daemon=True)
        fio.start()
        try:
            return "ok", self._app.DoJavaScript(codigo)
        except Exception as e:
            return "erro", e
        finally:
            parar.set()

    @staticmethod
    def _limpar_erro(msg):
        """Tira o preambulo generico do Photoshop e fica' so' com a frase.

        O erro chega muitas vezes como repr de tupla com \\n escapados,
        por isso trata os dois formatos.
        """
        texto = str(msg)
        for sep in ("\n- ", "\\n- "):
            if sep in texto:
                texto = texto.split(sep, 1)[1]
                break
        for sep in ("\\r\\n", "\\n", "\r\n", "\n", "\r"):
            texto = texto.replace(sep, " ")
        return " ".join(texto.split())[:200] or str(msg)[:200]

    def js(self, codigo, fallback_ui=None):
        """Corre ExtendScript dentro do Photoshop. Cai para UI se o COM falhar.

        Duas proteccoes apuradas a rodar (sem elas a app trava para sempre):
        1. DialogModes.NO em TODOS os scripts: sem isto o Photoshop abre
           alertas modais (ex.: "Desfoque Gaussiano... area selecionada
           vazia") e o DoJavaScript so' volta quando alguem carrega em OK.
           Com DialogModes.NO o mesmo erro vem como excecao JS e e'
           tratado como qualquer outro erro.
        2. Vigia de alertas: um fio em paralelo vigia as janelas PSDialogBox
           do Photoshop e carrega em OK, para que nenhum dialogo que escape
           ao DialogModes.NO consiga bloquear a app.
        """
        if self.ligar():
            script = "app.displayDialogs = DialogModes.NO; " + codigo
            ultimo = None
            for tentativa in range(12):
                estado, val = self._do_js(script)
                if estado == "ok":
                    return val
                ultimo = val
                msg = str(val)
                ocupado = ("ocupado" in msg or "-2147417846" in msg
                           or "-2147418111" in msg or "RETRY" in msg.upper())
                if ocupado:
                    try:
                        import pythoncom
                        pythoncom.PumpWaitingMessages()
                    except Exception:
                        pass
                    time.sleep(0.4)
                    continue
                self.log(f"[PS] ExtendScript falhou: {self._limpar_erro(msg)}")
                ultimo = None  # ja' registado; so' o fim das 12 tentativas avisa
                break
            if ultimo is not None:
                # Antes o erro final era descartado e a app ficava muda.
                self.log(f"[PS] Photoshop continuou ocupado apos 12 tentativas: "
                         f"{self._limpar_erro(ultimo)}")
        if fallback_ui and self.computer:
            try:
                return fallback_ui()
            except Exception as e:
                self.log(f"[PS] Fallback de interface tambem falhou: {e}")
        return None

    @staticmethod
    def _cor(cor, campo="foregroundColor"):
        return (
            f'app.{campo}.rgb.red = {PhotoshopIntegration._hex(cor, 0)};'
            f'app.{campo}.rgb.green = {PhotoshopIntegration._hex(cor, 1)};'
            f'app.{campo}.rgb.blue = {PhotoshopIntegration._hex(cor, 2)};'
        )

    # ======================================================
    # DOCUMENTO
    # ======================================================
    def criar_documento(self, largura=1920, altura=1080, resolucao=72, nome="Documento", cor="FFFFFF"):
        # Factos apurados neste Photoshop (21.0.2):
        #  - DocumentFill como 5o argumento e' ILEGAL (Erro 1246)
        #  - o 4o argumento (modo) vaza para o nome do documento -> "NewDocumentMode.RGB"
        #  - Document.name nao pode ser atribuido por script
        # Logo: 3 argumentos, e devolvemos o nome REAL que o Photoshop deu.
        script = (
            'var r = ""; '
            'if (app.documents.length < 1) { '
            f'var d = app.documents.add({int(largura)}, {int(altura)}, {int(resolucao)}); '
            f'{self._cor(cor)} '
            'r = d.name; } else { r = ""; } r;'
        )
        real = self.js(script)
        if real:
            self.log(f"[PS] Documento criado: {largura}x{altura} @ {resolucao}ppi (nome Photoshop: '{real}')")
            if nome and nome != "Documento":
                self.log(f"[PS] Nota: este Photoshop nao deixa renomear documentos por script. Pedi '{nome}'.")
            return True
        self.log("[PS] Nao criado (ja ha documento aberto?)")
        return False

    def fechar_documento(self, guardar=False):
        modo = 'SaveOptions.SAVECHANGES' if guardar else 'SaveOptions.DONOTSAVECHANGES'
        script = (
            'var r = ""; '
            'if (app.documents.length > 0) { app.activeDocument.close(' + modo + '); r = "ok"; } '
            'else { r = "sem documento"; } r;'
        )
        res = self.js(script)
        if res == "ok":
            self.log("[PS] Documento fechado.")
            return True
        return False

    def estado(self):
        """Le o estado real do Photoshop: documento, layers e dimensoes."""
        script = (
            'var r = ""; '
            'if (app.documents.length < 1) { r = "sem documento aberto"; } else { '
            'var d = app.activeDocument; var nomes = []; '
            'for (var i = 0; i < d.artLayers.length; i++) { nomes.push(d.artLayers[i].name); } '
            'r = "doc=" + d.name + " | " + Math.round(d.width.as("px")) + "x" + Math.round(d.height.as("px")) '
            '+ " | layers=" + nomes.length + " | " + nomes.join(" >> "); } r;'
        )
        res = self.js(script)
        if res:
            self.log(f"[PS] Estado: {res}")
            return res
        return "Photoshop nao respondeu"

    # ======================================================
    # LAYERS
    # ======================================================
    def criar_layer(self, nome="Layer"):
        script = (
            'var r = ""; '
            'if (app.documents.length < 1) { r = "sem documento aberto"; } else { '
            f'var l = app.activeDocument.artLayers.add(); l.name = "{nome}"; r = "ok"; }} r;'
        )
        res = self.js(script)
        if res == "ok":
            self.log(f"[PS] Layer criada: '{nome}'")
            return True
        self.log(f"[PS] Layer nao criada: {res}")
        return False

    def renomear_layer(self, antigo, novo):
        script = (
            'var r = ""; '
            'if (app.documents.length < 1) { r = "sem documento aberto"; } else { '
            'var d = app.activeDocument; r = "nao encontrada"; '
            f'for (var i = 0; i < d.artLayers.length; i++) {{ '
            f'if (d.artLayers[i].name == "{antigo}") {{ d.artLayers[i].name = "{novo}"; r = "ok"; }} }} }} r;'
        )
        res = self.js(script)
        ok = res == "ok"
        self.log(f"[PS] Layer '{antigo}' -> '{novo}': {'renomeada' if ok else res}")
        return ok

    def duplicar_layer(self, nome="Layer", vezes=1):
        script = (
            'var r = ""; '
            'if (app.documents.length < 1) { r = "sem documento aberto"; } else { '
            'var d = app.activeDocument; '
            f'for (var i = 1; i <= {int(vezes)}; i++) {{ var c = d.artLayers[d.artLayers.length - 1].duplicate(); c.name = "{nome} " + i; }} '
            'r = "ok"; } r;'
        )
        if self.js(script) == "ok":
            self.log(f"[PS] Layer '{nome}' duplicada x{vezes}")
            return True
        return False

    def ordernar_layers(self, criterio="topo"):
        if criterio == "nome":
            script = (
                'var r = ""; '
                'if (app.documents.length < 1) { r = "sem documento aberto"; } else { '
                'var d = app.activeDocument; var nomes = []; '
                'for (var i = 0; i < d.artLayers.length; i++) { nomes.push(d.artLayers[i].name); } '
                'nomes.sort(); var k = 0; '
                'for (var i = 0; i < d.artLayers.length; i++) { d.artLayers[i].name = nomes[k]; k++; } '
                'r = "ok"; } r;'
            )
        else:
            script = (
                'var r = ""; '
                'if (app.documents.length < 1) { r = "sem documento aberto"; } else { '
                'var d = app.activeDocument; '
                'for (var i = d.artLayers.length - 1; i > 0; i--) { d.artLayers[i].move(d.artLayers[i], ElementPlacement.PLACEAFTER); } '
                'r = "ok"; } r;'
            )
        if self.js(script) == "ok":
            self.log(f"[PS] Layers organizadas por '{criterio}'.")
            return True
        return False

    def ocultar_layer(self, nome, esconder=True):
        visivel = "false" if esconder else "true"
        script = (
            'var r = ""; '
            'if (app.documents.length < 1) { r = "sem documento aberto"; } else { '
            'var d = app.activeDocument; r = "nao encontrada"; '
            f'for (var i = 0; i < d.artLayers.length; i++) {{ '
            f'if (d.artLayers[i].name == "{nome}") {{ d.artLayers[i].visible = {visivel}; r = "ok"; }} }} }} r;'
        )
        return self.js(script) == "ok"

    def apagar_layer(self, nome, confirmar=False):
        """DESTRUTIVO - remover layer. So executa se confirmar=True."""
        if not confirmar:
            self.log(f"Atencao: confirmar apagar a layer '{nome}'? Responde 'sim' para executar.")
            return "AGUARDA_CONFIRMACAO"
        script = (
            'var r = ""; '
            'if (app.documents.length < 1) { r = "sem documento aberto"; } else { '
            'var d = app.activeDocument; r = "nao encontrada"; '
            f'for (var i = 0; i < d.artLayers.length; i++) {{ '
            f'if (d.artLayers[i].name == "{nome}") {{ d.artLayers[i].remove(); r = "ok"; }} }} }} r;'
        )
        if self.js(script) == "ok":
            self.log(f"[PS] Layer '{nome}' apagada.")
            return True
        return False

    def agrupar_layers(self, nome="Grupo"):
        script = (
            'var r = ""; '
            'if (app.documents.length < 1) { r = "sem documento aberto"; } else { '
            'var g = app.activeDocument.layerSets.add(); '
            f'g.name = "{nome}"; r = "ok"; }} r;'
        )
        if self.js(script) == "ok":
            self.log(f"[PS] Grupo '{nome}' criado.")
            return True
        return False

    # ======================================================
    # DESENHO
    # ======================================================
    def forma(self, tipo="retangulo", x=0, y=0, largura=400, altura=300, cor=None, cantos=0):
        """Desenha uma forma preenchida.

        Implementado com selection.select() + selection.fill() porque os
        pathItems NAO existem nesta versao do Photoshop (Erro 1302).
        O circulo e' um poligono de 36 pontos, que a selection aceita.
        """
        setcor = self._cor(cor) if cor else ""
        x, y = int(x), int(y)
        largura, altura = max(1, int(largura)), max(1, int(altura))
        t = str(tipo).lower()

        if t in ("circulo", "elipse", "ovalo", "ellipse"):
            cx, cy = x + largura / 2.0, y + altura / 2.0
            rx, ry = largura / 2.0, altura / 2.0
            pts = (f'var p = []; for (var i = 0; i < 36; i++) {{ var a = i * Math.PI / 18; '
                   f'p.push([{cx} + {rx} * Math.cos(a), {cy} + {ry} * Math.sin(a)]); }} d.selection.select(p);')
            nome_tipo = "circulo"
        elif t in ("linha", "line"):
            grossura = max(2, altura)
            pts = (f'd.selection.select([[{x},{y}],[{x + largura},{y}],'
                   f'[{x + largura},{y + grossura}],[{x},{y + grossura}]]);')
            nome_tipo = "linha"
        elif t == "triangulo":
            pts = f'd.selection.select([[{x + largura / 2},{y}],[{x + largura},{y + altura}],[{x},{y + altura}]]);'
            nome_tipo = "triangulo"
        elif t in ("retangulo_arredondado", "arredondado") and int(cantos) > 0:
            # Cantos arredondados de verdade: 4 arcos de 8 segmentos, forming
            # um poligono fechado. Antes isto ignorava o raio e devolvia um
            # retangulo normal sem avisar.
            raio = min(int(cantos), largura // 2, altura // 2)
            seg = 8
            # (x do canto, y do canto, sinal do centro em x, sinal em y, angulo inicial)
            cantos_arco = [
                (x, y, "+", "+", "Math.PI"),
                (x + largura, y, "-", "+", "-Math.PI / 2"),
                (x + largura, y + altura, "-", "-", "0"),
                (x, y + altura, "+", "-", "Math.PI / 2"),
            ]
            corpo = "var pts = []; "
            for cx0, cy0, sx, sy, ang in cantos_arco:
                centro_x = f"{cx0} + {raio}" if sx == "+" else f"{cx0} - {raio}"
                centro_y = f"{cy0} + {raio}" if sy == "+" else f"{cy0} - {raio}"
                corpo += (
                    f'for (var i = 0; i <= {seg}; i++) {{ '
                    f'var a = {ang} + i * (Math.PI / 2) / {seg}; '
                    f'pts.push([{centro_x} + {raio} * Math.cos(a), '
                    f'{centro_y} + {raio} * Math.sin(a)]); }} '
                )
            pts = corpo + "d.selection.select(pts);"
            nome_tipo = "retangulo_arredondado"
        else:
            pts = (f'd.selection.select([[{x},{y}],[{x + largura},{y}],'
                   f'[{x + largura},{y + altura}],[{x},{y + altura}]]);')
            nome_tipo = "retangulo"

        script = (
            'var r = ""; '
            'if (app.documents.length < 1) { r = "sem documento aberto"; } else { '
            f'var d = app.activeDocument; {setcor} {pts} '
            'd.selection.fill(app.foregroundColor); d.selection.deselect(); r = "ok"; } r;'
        )
        res = self.js(script)
        if res == "ok":
            self.log(f"[PS] Forma '{nome_tipo}' desenhada em ({x},{y}) {largura}x{altura}.")
            return True
        self.log(f"[PS] Forma nao desenhada: {res}")
        return False

    def texto(self, conteudo, x=100, y=100, tamanho=60, cor="000000", nome_layer="Texto"):
        conteudo = conteudo.replace('"', "'")
        script = (
            'var r = ""; '
            'if (app.documents.length < 1) { r = "sem documento aberto"; } else { '
            f'{self._cor(cor)} '
            f'var l = app.activeDocument.artLayers.add(); l.name = "{nome_layer}"; '
            'l.kind = LayerKind.TEXT; '
            f'l.textItem.contents = "{conteudo}"; '
            f'l.textItem.size = {float(tamanho)}; '
            f'l.textItem.position = [{int(x)}, {int(y)}]; '
            'r = "ok"; } r;'
        )
        if self.js(script) == "ok":
            self.log(f"[PS] Texto criado: '{conteudo}'")
            return True
        self.log("[PS] Texto nao criado (documento aberto?).")
        return False

    def definir_cor(self, cor, fundo=False):
        campo = "backgroundColor" if fundo else "foregroundColor"
        res = self.js(f'var r = ""; {self._cor(cor, campo)} r = "ok"; r;')
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
        }
        if tipo == "retangulo":
            acao = (f"d.selection.select([[{int(x)},{int(y)}],[{int(x + largura)},{int(y)}],"
                    f"[{int(x + largura)},{int(y + altura)}],[{int(x)},{int(y + altura)}]]);")
        elif tipo in ("elipse", "circulo", "ovalo"):
            cx, cy = int(x) + largura / 2.0, int(y) + altura / 2.0
            rx, ry = largura / 2.0, altura / 2.0
            acao = (f'var p = []; for (var i = 0; i < 36; i++) {{ var a = i * Math.PI / 18; '
                    f'p.push([{cx} + {rx} * Math.cos(a), {cy} + {ry} * Math.sin(a)]); }} d.selection.select(p);')
        else:
            acao = tipos.get(tipo)
        if not acao:
            self.log(f"[PS] Selecao '{tipo}' desconhecida.")
            return False
        script = (
            'var r = ""; '
            'if (app.documents.length < 1) { r = "sem documento aberto"; } else { '
            f'var d = app.activeDocument; {acao} r = "ok"; }} r;'
        )
        res = self.js(script)
        if res == "ok":
            self.log(f"[PS] Selecao '{tipo}' aplicada.")
            return True
        return False

    def _verificar_alvo(self):
        """Confere se a layer ativa aceita preenchimento/filtro.

        Devolve 'ok', um motivo de bloqueio, ou None se a propria verificacao
        falhar (nesse caso o chamador nao bloqueia - deixa a operacao correr e
        reportar o erro dela, em vez de inventar uma falha).

        Facto apurado: tornar uma layer ESCONDIDA ativa volta a mostra-la
        (activeLayer.visible passa a true), por isso a verificacao de
        visibilidade raramente bloqueia. A de TEXTO bloqueia sempre, porque
        selection.fill() nao existe para camadas de texto.
        """
        try:
            return self.js(
                'var r = ""; '
                'if (app.documents.length < 1) { r = "sem documento aberto"; } '
                'else if (app.activeDocument.activeLayer.visible === false) { r = "layer escondida"; } '
                'else if (app.activeDocument.activeLayer.kind == LayerKind.TEXT) { r = "layer de texto"; } '
                'else { r = "ok"; } r;'
            )
        except Exception:
            return None

    def selecionar_layer(self, nome):
        """Torna a layer indicada a layer ativa.

        NOTA: o Photoshop mostra automaticamente a layer ao defini-la como
        ativa, portanto esconder + selecionar resulta sempre numa layer visivel.
        """
        script = (
            'var r = ""; '
            'if (app.documents.length < 1) { r = "sem documento aberto"; } else { '
            'var d = app.activeDocument; r = "nao encontrada"; '
            f'for (var i = 0; i < d.artLayers.length; i++) {{ '
            f'if (d.artLayers[i].name == "{nome}") {{ d.activeLayer = d.artLayers[i]; r = "ok"; }} }} }} r;'
        )
        res = self.js(script)
        if res == "ok":
            self.log(f"[PS] Layer ativa: '{nome}'")
            return True
        self.log(f"[PS] Layer '{nome}' nao encontrada")
        return False

    def preencher(self, cor=None):
        # selection.fill e' o metodo que existe; Document.fill() nao existe nesta versao.
        alvo = self._verificar_alvo()
        if alvo == "layer escondida":
            self.log("[PS] Nao preenchi: a layer ativa esta escondida. Torna-a visivel ou escolhe outra layer.")
            return False
        if alvo == "layer de texto":
            self.log("[PS] Nao preenchi: a layer ativa e' de TEXTO, onde nao se pode preencher. "
                     "Escolhe a layer de baixo (ou cria uma nova) e preenche essa.")
            return False
        if cor:
            self.definir_cor(cor)
        script = (
            'var r = ""; '
            'if (app.documents.length < 1) { r = "sem documento aberto"; } else { '
            'var d = app.activeDocument; '
            'if (d.selection.bounds[0] < 0) { d.selection.selectAll(); } '
            'd.selection.fill(app.foregroundColor); d.selection.deselect(); r = "ok"; } r;'
        )
        if self.js(script) == "ok":
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
        tecla = atalhos.get(str(nome).lower())
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

    def _tem_selecao(self):
        """True se ha pixeis selecionados.

        IMPORTANTE: aplicar um filtro com a selecao VAZIA faz o Photoshop
        mostrar o aviso modal 'Nenhum pixel selecionado.' e o DoJavaScript fica
        bloqueado para sempre. Por isso aqui recusamos em vez de deixar travar.
        """
        try:
            res = self.js(
                'var r = ""; '
                'if (app.documents.length < 1) { r = "sem documento"; } else { '
                # sem selecao, selection.bounds lanca Erro 1302 e o erro
                # sai do script a entupir os logs: apanhamos dentro do JS
                'try { var b = app.activeDocument.selection.bounds; '
                'r = (b[2] > b[0] && b[3] > b[1]) ? "sim" : "nao"; } '
                'catch (e) { r = "nao"; } } r;'
            )
            return res == "sim"
        except Exception:
            return True  # nao sabemos -> deixa tentar

    def _layer_vazia(self):
        """True se a layer ativa nao tem nenhum pixel (bounds zero).

        Sem isto o Photoshop responde com um ALERTA MODAL do tipo "nao foi
        possivel completar o Desfoque Gaussiano porque a area selecionada
        esta' vazia" mesmo com a selecao toda preenchida - a camada e' que
        esta' vazia. Com DialogModes.NO o mesmo erro vem por excecao, mas
        avisamos primeiro com uma frase que se percebe.
        """
        try:
            res = self.js(
                'var r = ""; '
                'if (app.documents.length < 1) { r = "sem documento"; } else { '
                'var b = app.activeDocument.activeLayer.bounds; '
                'r = ((b[2] - b[0]) <= 0 && (b[3] - b[1]) <= 0) ? "vazia" : "cheia"; } r;'
            )
            return res == "vazia"
        except Exception:
            return False

    def efeito(self, nome, intensidade=50):
        """Aplica filtro na layer ativa.

        Factos: applyGaussianBlur e applyUnSharpMask existem em activeLayer.
        applyMosaic e os filtros de Document NAO existem nesta versao.
        """
        i = max(1, int(intensidade))
        filtros = {
            "blur": f"d.activeLayer.applyGaussianBlur({i});",
            "desfoque": f"d.activeLayer.applyGaussianBlur({i});",
            "gaussian_blur": f"d.activeLayer.applyGaussianBlur({i});",
            "nitidez": f"d.activeLayer.applyUnSharpMask({i}, 1.5, 0);",
            "sharpen": f"d.activeLayer.applyUnSharpMask({i}, 1.5, 0);",
        }
        acao = filtros.get(str(nome).lower())
        if not acao:
            self.log(f"[PS] Efeito '{nome}' nao suportado por script nesta versao. Usa o Photoshop para filtros avancados.")
            return False
        alvo = self._verificar_alvo()
        if alvo == "layer escondida":
            self.log("[PS] Nao apliquei o filtro: a layer ativa esta escondida. Torna-a visivel ou escolhe outra layer.")
            return False
        if alvo == "layer de texto":
            self.log("[PS] Nao apliquei o filtro a uma layer de texto. Escolhe a layer de conteudo.")
            return False
        if alvo == "ok" and self._layer_vazia():
            self.log("[PS] Nao apliquei o filtro: a layer ativa esta' vazia "
                     "(nao tem pixels nesse ponto). Desenha ou preenche antes.")
            return False
        if not self._tem_selecao():
            self.log("[PS] Nao apliquei o filtro: nao ha nada selecionado. "
                     "Faz 'selecionar tudo' ou desenha uma forma antes do efeito.")
            return False
        script = (
            'var r = ""; '
            'if (app.documents.length < 1) { r = "sem documento aberto"; } else { '
            f'var d = app.activeDocument; {acao} r = "ok"; }} r;'
        )
        if self.js(script) == "ok":
            self.log(f"[PS] Efeito '{nome}' aplicado.")
            return True
        return False

    def ajustar_niveis(self, entrada=0, saida=255):
        """Nao suportado: LevelsAdjustment nao tem construtor nesta versao do Photoshop."""
        self.log("[PS] Ajustar niveis nao e' possivel por script nesta versao. Usa Ctrl+U / Curves no Photoshop.")
        return False

    def inverter_cores(self):
        script = (
            'var r = ""; '
            'if (app.documents.length < 1) { r = "sem documento aberto"; } else { '
            'var d = app.activeDocument; d.selection.selectAll(); d.selection.invert(); '
            'd.selection.deselect(); r = "ok"; } r;'
        )
        if self.js(script) == "ok":
            self.log("[PS] Cores invertidas.")
            return True
        return False

    # ======================================================
    # GUARDAR
    # ======================================================
    def _save_options_js(self, fmt, qualidade=None):
        """Devolve o codigo JS que cria as opcoes de gravacao, ou None.

        Factos apurados neste Photoshop (21.0.2):
        - JPEGSaveOptions.quality vai de 0 a 12, NAO de 0 a 100. Passar 90
          da Erro 1239 ("valor maior que o maximo").
        - A forma que grava sem abrir dialogos e
          saveAs(ficheiro, opcoes, asCopy, Extension.LOWERCASE).
          Com apenas 2 argumentos o Photoshop abre um dialogo (Erro 8007).
        """
        f = str(fmt).lower().lstrip(".")
        if f == "psd":
            return "new PhotoshopSaveOptions()"
        if f in ("jpg", "jpeg"):
            # 0-100 do utilizador -> 0-12 do Photoshop
            q = max(0, min(12, int(round(int(qualidade if qualidade is not None else 90) * 12 / 100.0))))
            return f"new JPEGSaveOptions(), JPEGSAVE_Q={q}"
        if f == "png":
            return "new PNGSaveOptions()"
        extras = {
            "webp": "new WEBPSaveOptions()",
            "gif": "new GIFSaveOptions()",
            "tif": "new TiffSaveOptions()",
            "tiff": "new TiffSaveOptions()",
        }
        return extras.get(f)

    def _js_save(self, caminho, fmt, qualidade=None):
        """Script de gravacao. Devolve None se o formato nao for suportado."""
        opcoes = self._save_options_js(fmt, qualidade)
        if opcoes is None:
            return None
        # a opcao JPEG vem accompanied de um valor de qualidade a atribuir
        if opcoes.endswith(")") and "JPEGSAVE_Q" in opcoes:
            opcoes, _, q = opcoes.partition(", JPEGSAVE_Q=")
            qualidade_js = f' o.quality = {int(q)}; o.embedColorProfile = true;'
        else:
            qualidade_js = ""
        return (
            'var r = ""; '
            'if (app.documents.length < 1) { r = "sem documento aberto"; } else { '
            'var d = app.activeDocument; '
            f'var o = {opcoes};{qualidade_js} '
            f'd.saveAs(new File("{caminho}"), o, true, Extension.LOWERCASE); r = "ok"; }} r;'
        )

    def guardar(self, caminho=None, formato="psd"):
        if not caminho:
            caminho = self.js(
                'var r = ""; '
                'if (app.documents.length < 1) { r = ""; } else { r = app.activeDocument.fullName.fsName; } r;'
            )
            if caminho:
                self.log(f"[PS] Ja guardado em: {caminho}")
                return True
            if self.computer:
                self.computer.activate_window("Adobe Photoshop")
                self.computer.hotkey("ctrl", "s")
                self.log("[PS] Ctrl+S enviado.")
                return True
            return False

        caminho = caminho.replace("\\", "/")
        fmt = str(formato).lower().lstrip(".")
        script = self._js_save(caminho, fmt)
        if script is None:
            self.log(f"[PS] Formato '{formato}' nao suportado. Usa: psd, jpg, png, webp, gif, tif.")
            return False
        if self.js(script) == "ok":
            self.log(f"[PS] Guardado em {caminho}")
            return True
        self.log(f"[PS] Falha ao guardar em {caminho}")
        return False

    def exportar(self, caminho, formato="jpg", qualidade=90):
        caminho = caminho.replace("\\", "/")
        script = self._js_save(caminho, formato, qualidade)
        if script is None:
            self.log(f"[PS] Formato '{formato}' nao suportado. Usa: jpg, png, webp, gif, tif.")
            return False
        if self.js(script) == "ok":
            self.log(f"[PS] Exportado para {caminho} ({str(formato).lower().lstrip('.')})")
            return True
        self.log(f"[PS] Falha ao exportar para {caminho}")
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
            c = str(cor).lstrip("#")
            if len(c) == 3:
                c = "".join(ch * 2 for ch in c)
            return int(c[indice * 2: indice * 2 + 2], 16)
        except Exception:
            return 255
