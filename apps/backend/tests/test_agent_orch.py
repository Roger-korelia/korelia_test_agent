
# =========================================================
# Prueba sencilla de multi_agent_orch.py

import json
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from multi_agent_orch import run_orchestrated_workflow

print("Prueba de multi_agent_orch.py")
if __name__ == "__main__":
    prompt = "Diseña una PSU 24V/3A aislada con PFC"
    print(f"Ejecutando prompt: {prompt}")
    resultado = run_orchestrated_workflow(prompt)
    print(json.dumps(resultado.get("intent_summary", resultado), indent=2, ensure_ascii=False))

