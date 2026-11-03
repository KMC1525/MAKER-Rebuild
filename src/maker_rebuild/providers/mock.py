"""Provedor offline determinístico: permite testar o pipeline inteiro sem rede e sem chaves.

Não é uma IA — devolve respostas sintéticas válidas por tipo de tarefa.
"""
from __future__ import annotations

import json
import re

from .base import Completion, ChunkCb, LLMRequest, Provider


class MockProvider(Provider):
    name = "mock"
    kind = "mock"

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.calls = []

    def complete(self, req: LLMRequest, on_chunk: ChunkCb = None) -> Completion:
        self.calls.append(req)
        user = req.messages[-1]["content"] if req.messages else ""
        t = req.task
        if t == "clarify":
            out = {"ready": True, "questions": [], "assumptions": ["modo mock: sem perguntas"]}
        elif t == "plan":
            out = {"mode": "faithful", "summary": "plano sintético (mock)", "goals": ["converter com fidelidade"], "translateTo": None,
                   "features": [{"id": "f1", "title": "Poção Mock", "description": "adiciona um item e um NPC que o entrega"}]}
        elif t == "translate":
            m = re.search(r"TARGET_LANG=(\S+)", user)
            lang = m.group(1) if m else "xx"
            body = user.split("JSON:\n", 1)[1]
            items = json.loads(body[body.index("["):body.rindex("]") + 1])
            out = {"translations": [{"id": i["id"], "text": f"[{lang}] {i['text']}"} for i in items]}
        elif t == "expand":
            out = {"summary": "Adiciona Poção Mock e um NPC (mock)",
                   "db": {"items": {"add": [{"ref": "mockpotion", "name": "Poção Mock", "description": "Item gerado em modo mock.",
                                             "iconIndex": 176, "price": 20, "consumable": True, "scope": 7,
                                             "effects": [{"code": 11, "dataId": 0, "value1": 0, "value2": 50}]}]}},
                   "maps": {"update": [{"id": 1, "events": {"add": [{"name": "NPC Mock", "x": 2, "y": 2, "pages": [{
                       "image": {"characterName": "", "characterIndex": 0}, "trigger": "action",
                       "script": [{"say": ["Eu fui gerado pelo provedor mock."]}, {"give_item": "@mockpotion", "n": 1}]}]}]}}]},
                   "notes": ["mock"]}
        elif t == "port":
            body = user.split("ENTRADA:\n", 1)[-1]
            try:
                items = json.loads(body[body.index("["):body.rindex("]") + 1])
                out = {"ports": [{"id": i["id"], "js": "// port mock", "notes": "mock"} for i in items]}
            except ValueError:
                out = {"js": "MR.ext.modules['mock'] = {};", "commands": [], "limitations": ["mock"], "notes": "mock"}
        elif t == "route":
            out = {"action": "help", "args": {}}
        else:
            out = {"text": "mock"}
        text = json.dumps(out, ensure_ascii=False)
        on_chunk and on_chunk(text)
        return Completion(text, "stop")
