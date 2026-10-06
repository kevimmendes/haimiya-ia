#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict, Any, Optional


class Router:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.models = {
            "local": self.config.get("local_model", "llama-3.1-8b"),
            "groq": self.config.get("groq_model", "llama-3.1-70b-versatile"),
            "nvidia": self.config.get("nvidia_model", "deepseek-r1-distill-llama-8b"),
        }

    def route(self, task_type: str = "general") -> Dict[str, str]:
        # Roteamento simples e extensível
        routes = {
            "general": "groq",
            "reasoning": "local",
            "vision": "nvidia",
            "code": "groq",
            "creative": "local",
        }
        provider = routes.get(task_type, "groq")
        return {"provider": provider, "model": self.models.get(provider, self.models["groq"])}


def get_router() -> Router:
    return Router()
