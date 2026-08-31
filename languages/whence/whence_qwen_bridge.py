#!/usr/bin/env python3
"""
Research Bridge: Connect Whence Language to Qwen 3.6 API on NUC.

This module allows Whence scripts to offload specific AI tasks to the 
Qwen 3.6 model running on the Intel NUC via its proxy API endpoint.
This is a hybrid execution pattern: deterministic logic in Whence, 
intelligent inference in Qwen.

Author: Jaby (Autonomous Research Session)
Date: 2026-08-27
"""

import requests
import json
from typing import Optional


class NucBridgeConfig:
    """Configuration for connecting to the NUC's Qwen3.6 API."""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8080"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
    def health_check(self) -> bool:
        """Verify connectivity to the NUC bridge."""
        try:
            resp = self.session.get(f"{self.base_url}/healthz", timeout=5)
            return resp.status_code == 200 and resp.json().get("ok")
        except Exception:
            return False

    def execute_script(self, task_description: str, max_tokens: int = 2048) -> dict:
        """Send a research task to Qwen 3.6 via the proxy API."""
        payload = {
            "model": "qwen36-tools",
            "messages": [
                {"role": "system", "content": "You are an assistant executing precise tasks from a provenance-first reasoning engine."},
                {"role": "user", "content": task_description}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.1
        }
        
        try:
            resp = self.session.post(
                f"{self.base_url}/v1/chat/completions", 
                json=payload, 
                timeout=90
            )
            resp.raise_for_status()
            data = resp.json()
            
            return {
                "status": "success",
                "content": data["choices"][0]["message"]["content"],
                "usage": data.get("usage", {}),
                "finish_reason": data["choices"][0].get("finish_reason")
            }
        except requests.exceptions.RequestException as e:
            return {"status": "error", "detail": str(e)}


# Singleton instance for easy access in automated workflows
_bridge_instance: Optional[NucBridgeConfig] = None

def get_bridge():
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = NucBridgeConfig()
    return _bridge_instance
