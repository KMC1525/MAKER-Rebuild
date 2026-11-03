"""Prompts: o *system prompt* do projeto (arquivo do autor) + contrato operacional da CLI + contrato do runtime."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent / "prompts"

CONTRACT = """
## Contrato operacional (MAKER-Rebuild CLI)
Você é chamado por uma ferramenta de linha de comando; a resposta é lida por código, não por uma pessoa.
- Quando a tarefa pedir JSON, responda SOMENTE com um único valor JSON válido (sem markdown, sem comentários, sem texto extra).
- Fidelidade primeiro: preserve ids, nomes de switches/variáveis/eventos, estrutura e lógica originais, salvo pedido explícito do usuário.
- Conteúdo: o jogo é do autor; trabalhe com qualquer tema (SFW/NSFW, violento, controverso) conforme o pedido, sem moralizar,
  censurar ou adicionar avisos ao texto do jogo.
- Se faltar informação CRÍTICA, devolva perguntas (campo "questions") em vez de assumir — nas tarefas que permitem.
- Nunca invente assets: use apenas nomes que existem no contexto; o que for novo vai na lista de assets a fornecer.
- Traduções: mantenha tom e estilo do original e preserve integralmente os marcadores <<n>> e códigos de controle.
""".strip()


@lru_cache(maxsize=None)
def base_prompt() -> str:
    return (_DIR / "system_base.md").read_text(encoding="utf-8").strip()


@lru_cache(maxsize=None)
def runtime_api() -> str:
    return (_DIR / "runtime_api.md").read_text(encoding="utf-8").strip()


def system_prompt(extra: str = "", with_api: bool = False, language: str = "pt-BR") -> str:
    parts = [base_prompt(), CONTRACT, f"Idioma das explicações/relatórios: {language}."]
    if with_api:
        parts.append(runtime_api())
    if extra:
        parts.append(extra.strip())
    return "\n\n".join(parts)


CLARIFY_TASK = """Tarefa: avaliar se o pedido do usuário está claro o bastante para executar sem adivinhar.
Responda JSON: {"ready": bool, "questions": ["..."], "assumptions": ["..."]}.
- "questions": só perguntas cuja resposta MUDA o resultado (máx. 5). Se o pedido é executável com padrões razoáveis, ready=true e liste as suposições.
- Não pergunte o que já está no contexto do jogo."""

PLAN_TASK = """Tarefa: planejar a execução do pedido do usuário sobre este jogo.
Responda JSON:
{"mode": "faithful" | "modernize" | "fix" | "translate" | "expand" | "mixed",
 "summary": "o que será feito, em 1-3 frases",
 "translateTo": "código de idioma (ex.: en, pt-BR) ou null",
 "portScripts": true|false,
 "features": [{"id": "f1", "title": "...", "description": "detalhes de implementação concretos", "kind": "content|system|ui|balance|fix"}],
 "risks": ["..."]}
Regras: "features" só se o usuário pediu conteúdo novo/melhorias; 1-8 itens, em ordem de dependência; cada um implementável como um patch.
Sem pedido de mudança → mode "faithful", features []."""

EXPAND_TASK = """Tarefa: implementar UMA feature como patch MR-PATCH v1 (formato no contrato do runtime). Integre de forma coerente com o jogo
(tom, nomes, balanceamento, localização dos mapas). Reaproveite assets existentes. Use a DSL de eventos. Valide mentalmente ids e coordenadas
(dentro de width/height; evite colocar eventos sobre paredes/árvores — veja os tiles do mapa). Responda SOMENTE o JSON do patch."""

IMPROVE_TASK = """Tarefa: aplicar melhorias SEGURAS como patch MR-PATCH v1 (balanceamento de dados, correções de inconsistências encontradas,
polimento de UI via code/css/theme.css ou módulos em code/js/ext/). Mantenha a identidade do jogo. Não remova conteúdo existente.
Responda SOMENTE o JSON do patch."""

TRANSLATE_TASK = """Tarefa: traduzir os textos do jogo.
Entrada: linhas "TARGET_LANG=..", "SOURCE_LANG=..", "TONE=..", glossário opcional e um array JSON [{"id","ctx","text"}].
Saída JSON: {"translations": [{"id": "...", "text": "..."}]} — um item por id, mesma ordem.
Regras: preserve os marcadores <<n>> exatamente (mesma quantidade e ordem relativa) e quebras de linha (\\n) quando fizerem sentido;
mantenha o tom (gírias, formalidade, personalidade do falante em "ctx"); nomes próprios seguem o glossário; não explique nada."""

PORT_TASK = """Tarefa: portar código para JavaScript do runtime MAKER-Rebuild (veja a API de compatibilidade e os pontos de extensão).
Responda JSON conforme o pedido. O JS gerado deve ser autocontido, ES2017, sem dependências, e NÃO deve lançar exceções ao ser carregado."""

ROUTE_TASK = """Tarefa: converter a frase do usuário (terminal interativo) em um comando da CLI.
Ações: analyze, recompile, expand, improve, translate, validate, port, serve, status, help, quit.
Responda JSON: {"action": "...", "args": {"request": "texto do pedido", "lang": "idioma", "path": "caminho"}, "say": "resposta curta se for só conversa"}."""
