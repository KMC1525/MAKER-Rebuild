"""Fluxos de IA de alto nível: esclarecer → planejar → expandir/melhorar → revisar."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .. import ui
from ..build.validate import validate_game
from . import prompts
from .client import AIClient, AIOutputError
from .context import digest
from .patch import ApplyResult, PatchError, apply_patch


# ---------------------------------------------------------------------------------- clarify / plan
def clarify(ai: AIClient, game: Any, instruction: str, interactive: bool, ask: Callable[[str], str] = ui.ask) -> str:
    """Devolve o texto final do pedido (instrução + respostas + suposições)."""
    ctx = digest(game, 20000, getattr(game, "notes", None))
    data = ai.ask_json("clarify", f"CONTEXTO DO JOGO:\n{ctx}\n\nPEDIDO DO USUÁRIO:\n{instruction}", extra_system=prompts.CLARIFY_TASK,
                       desc="analisando o pedido")
    qs = [str(q) for q in (data.get("questions") or [])][:5] if isinstance(data, dict) else []
    assumptions = [str(a) for a in (data.get("assumptions") or [])] if isinstance(data, dict) else []
    answers: List[str] = []
    if qs and not (isinstance(data, dict) and data.get("ready") and not interactive):
        if interactive:
            ui.info("Preciso de alguns esclarecimentos antes de começar:")
            for q in qs:
                a = ask(q, "")
                answers.append(f"P: {q}\nR: {a or '(sem resposta — usar padrão razoável)'}")
        else:
            ui.warn("Perguntas pendentes (modo não interativo; assumindo padrões): " + " | ".join(qs))
    out = instruction
    if answers:
        out += "\n\nRESPOSTAS DO USUÁRIO:\n" + "\n".join(answers)
    if assumptions:
        out += "\n\nSUPOSIÇÕES ADOTADAS:\n- " + "\n- ".join(assumptions)
    return out


def plan(ai: AIClient, game: Any, request: str) -> Dict[str, Any]:
    ctx = digest(game, ai.cfg.context_chars // 2, getattr(game, "notes", None))
    data = ai.ask_json("plan", f"CONTEXTO DO JOGO:\n{ctx}\n\nPEDIDO (já esclarecido):\n{request}", extra_system=prompts.PLAN_TASK,
                       desc="planejando")
    if not isinstance(data, dict):
        raise AIOutputError("plano inválido (esperado objeto)")
    data.setdefault("features", [])
    data["features"] = [f for f in data["features"] if isinstance(f, dict)][:8]
    return data


# ---------------------------------------------------------------------------------- expand / improve
@dataclass
class ExpandReport:
    applied: List[Dict[str, Any]] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    assets_todo: List[Dict[str, str]] = field(default_factory=list)
    placeholders: List[str] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def _implement(ai: AIClient, game: Any, mode: str, request: str, feature: Dict[str, Any], history: List[str],
               errors: Optional[List[str]] = None, prev: str = "") -> Any:
    detail = [m for m in game.maps][:3]
    ctx = digest(game, ai.cfg.context_chars, getattr(game, "notes", None), detail_maps=detail)
    task = prompts.EXPAND_TASK if mode == "expand" else prompts.IMPROVE_TASK
    user = (f"CONTEXTO ATUAL DO JOGO (já inclui features aplicadas antes):\n{ctx}\n\nPEDIDO GERAL:\n{request}\n\n"
            f"FEATURE A IMPLEMENTAR AGORA:\n{json.dumps(feature, ensure_ascii=False)}\n\n"
            + ("FEATURES JÁ APLICADAS:\n- " + "\n- ".join(history) + "\n\n" if history else ""))
    if errors:
        user += ("SEU PATCH ANTERIOR FOI REJEITADO. Corrija e devolva o patch completo.\nERROS:\n- " + "\n- ".join(errors) +
                 f"\nPATCH ANTERIOR:\n{prev[:12000]}")
    return ai.ask_json("expand", user, extra_system=task, with_api=True, desc=f"implementando: {feature.get('title', '?')}",
                       max_tokens=ai.cfg.max_tokens)


def expand_game(ai: AIClient, game: Any, request: str, mode: str = "expand", features: Optional[List[Dict[str, Any]]] = None,
                max_features: int = 6, on_progress: Optional[Callable[[int, int, str], None]] = None) -> ExpandReport:
    rep = ExpandReport()
    if not features:
        pl = plan(ai, game, request)
        features = pl.get("features") or []
        if not features:
            features = [{"id": "f1", "title": request[:60], "description": request, "kind": "content"}]
    features = features[:max_features]
    history: List[str] = []
    for i, feat in enumerate(features, 1):
        if on_progress:
            on_progress(i, len(features), feat.get("title", ""))
        errors: Optional[List[str]] = None
        prev = ""
        for attempt in range(3):
            try:
                patch = _implement(ai, game, mode, request, feat, history, errors, prev)
                prev = json.dumps(patch, ensure_ascii=False)
                res = apply_patch(game, patch)
                break
            except (PatchError, AIOutputError) as e:
                errors = [str(e)]
                if attempt == 2:
                    rep.failed.append(f"{feat.get('title')}: {e}")
                    res = None
        else:
            res = None
        if res is None:
            continue
        history.append(f"{feat.get('title')}: {res.summary}")
        rep.applied.append({"feature": feat.get("title"), "summary": res.summary, "added": res.added, "updated": res.updated})
        rep.assets_todo += res.assets_todo
        rep.placeholders += res.placeholders
        rep.files += res.files
        rep.warnings += res.warnings
        rep.notes += res.notes
    return rep


# ---------------------------------------------------------------------------------- revisão
def review(ai: AIClient, game: Any, report: Dict[str, Any]) -> str:
    ctx = digest(game, ai.cfg.context_chars // 2)
    slim = {k: report.get(k) for k in ("errors", "warnings", "missing_assets", "info")}
    return ai.complete("review", f"CONTEXTO:\n{ctx}\n\nRELATÓRIO DE VALIDAÇÃO:\n{json.dumps(slim, ensure_ascii=False)[:12000]}\n\n"
                       "Resuma em até 10 linhas os riscos reais para o jogador e as correções prioritárias.",
                       json_mode=False, desc="revisando")
