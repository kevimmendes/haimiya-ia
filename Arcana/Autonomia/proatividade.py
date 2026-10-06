#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional


class Proatividade:
    def __init__(self, state_path: str = "Arcana/armazen/proatividade.json"):
        self.state_path = state_path
        os.makedirs(os.path.dirname(state_path) or ".", exist_ok=True)
        self.state = self._load()

    def _load(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self.state_path):
                with open(self.state_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"missions": [], "last_check": datetime.now().isoformat(), "enabled": True}

    def _save(self):
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    def add_mission(self, mission: Dict[str, Any]) -> bool:
        if not mission.get("id"):
            mission["id"] = f"m_{datetime.now().timestamp():.0f}"
        mission["created_at"] = datetime.now().isoformat()
        mission["status"] = mission.get("status", "pending")
        self.state["missions"].append(mission)
        self._save()
        return True

    def get_pending(self) -> List[Dict[str, Any]]:
        return [m for m in self.state["missions"] if m.get("status") == "pending"]

    def complete_mission(self, mission_id: str) -> bool:
        for m in self.state["missions"]:
            if m.get("id") == mission_id:
                m["status"] = "completed"
                m["completed_at"] = datetime.now().isoformat()
                self._save()
                return True
        return False
