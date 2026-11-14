"""Gera o script DML database/02_popular_dados.js a partir do gerador determinístico.

Os tipos são escritos com os construtores do mongosh para respeitar o JSON
Schema das coleções: ObjectId, ISODate, NumberDecimal e Double (no mongosh um
número inteiro como 2 seria gravado como int, e peso_kg exige double).
"""

import json
import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from ecotrack.dados.gerador import Documento, contagem, gerar, total_documentos

_HEX24 = re.compile(r"^[0-9a-f]{24}$")
ORDEM_DE_INSERCAO = (
    "materiais",
    "clientes",
    "pontos_coleta",
    "coletas",
    "lotes",
    "equipamentos",
    "triagens",
    "eventos_rastreabilidade",
    "leituras_telemetria",
)


def _e_identificador(chave: str, valor: str) -> bool:
    return (chave == "_id" or chave.endswith("_id")) and bool(_HEX24.match(valor))


# Ordem importa: bool é subclasse de int, por isso aparece antes.
_ESCALARES: tuple[tuple[type, Callable[[Any], str]], ...] = (
    (bool, lambda v: "true" if v else "false"),
    (int, str),
    (float, lambda v: f"Double({v!r})"),
    (Decimal, lambda v: f'NumberDecimal("{v}")'),
    (datetime, lambda v: f'ISODate("{v.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")}")'),
)


def _texto(valor: str, chave: str) -> str:
    return f'ObjectId("{valor}")' if _e_identificador(chave, valor) else json.dumps(valor, ensure_ascii=False)


def para_mongosh(valor: Any, chave: str = "") -> str:
    """Converte um valor Python na sintaxe literal do mongosh."""
    if valor is None:
        return "null"
    if isinstance(valor, str):
        return _texto(valor, chave)
    if isinstance(valor, dict):
        return "{ " + ", ".join(f"{k}: {para_mongosh(v, k)}" for k, v in valor.items()) + " }"
    if isinstance(valor, (list, tuple)):
        return "[" + ", ".join(para_mongosh(v, chave) for v in valor) + "]"
    conversor = next((converter for tipo, converter in _ESCALARES if isinstance(valor, tipo)), None)
    if conversor is None:
        raise TypeError(f"tipo não suportado: {type(valor)!r}")
    return conversor(valor)


def _bloco(colecao: str, documentos: Iterable[Documento]) -> str:
    linhas = ",\n  ".join(para_mongosh(d) for d in documentos)
    return f"print('  -> {colecao}');\ndb.{colecao}.insertMany([\n  {linhas}\n], {{ ordered: true }});\n"


def gerar_script() -> str:
    dados = gerar()
    resumo = "\n".join(
        f"//   {colecao:<26} {quantidade:>4} documentos" for colecao, quantidade in contagem(dados).items()
    )
    cabecalho = f"""// =============================================================================
// EcoTrack MVP - 02_popular_dados.js  (DML / carga de demonstracao)
// Gerado por: python -m ecotrack exportar-js   (semente fixa = dados reproduziveis)
// Executar:   mongosh "mongodb://localhost:27017/ecotrack" database/02_popular_dados.js
//
// Total: {total_documentos(dados)} documentos simulando transacoes reais de set/2026 a nov/2026
{resumo}
// =============================================================================
db = db.getSiblingDB("ecotrack");
print("Limpando colecoes de dados (estrutura e indices sao mantidos)...");
{chr(10).join(f"db.{c}.deleteMany({{}});" for c in ORDEM_DE_INSERCAO)}
db.controle_ingestao.deleteMany({{}});
db.resumos_mensais.deleteMany({{}});
print("Inserindo documentos...");
"""
    corpo = "\n".join(_bloco(colecao, dados[colecao]) for colecao in ORDEM_DE_INSERCAO)
    rodape = """
print("Carga concluida. Contagem por colecao:");
["materiais", "clientes", "pontos_coleta", "coletas", "lotes", "equipamentos", "triagens",
 "eventos_rastreabilidade", "leituras_telemetria"].forEach(c => print("  " + c.padEnd(26) + db[c].countDocuments({})));
"""
    return cabecalho + corpo + rodape


def exportar(destino: Path) -> Path:
    destino.write_text(gerar_script(), encoding="utf-8")
    return destino
