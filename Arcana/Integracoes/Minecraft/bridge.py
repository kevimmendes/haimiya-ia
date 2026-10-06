#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import socket
from typing import Dict, Any, Optional


class MinecraftBridge:
    def __init__(self, config_path: str = "Arcana/Integracoes/Minecraft/config.json"):
        self.config_path = config_path
        self.config = self._load_config()
        self.host = self.config.get("host", "localhost")
        self.port = int(self.config.get("port", 8765))
        self.connected = False

    def _load_config(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"host": "localhost", "port": 8765}

    def conectar(self) -> bool:
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(2)
            self.sock.connect((self.host, self.port))
            self.connected = True
            return True
        except Exception:
            self.connected = False
            return False

    def enviar(self, comando: str) -> Optional[str]:
        if not self.connected:
            if not self.conectar():
                return None
        try:
            self.sock.sendall((comando + "\n").encode("utf-8"))
            data = self.sock.recv(4096)
            return data.decode("utf-8", errors="ignore")
        except Exception:
            self.connected = False
            return None

    def executar_comando(self, comando: str) -> Optional[str]:
        return self.enviar(comando)
