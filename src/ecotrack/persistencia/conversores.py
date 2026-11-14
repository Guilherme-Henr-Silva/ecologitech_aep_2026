"""Conversão entre tipos Python do domínio e tipos BSON do MongoDB."""

import re
from decimal import Decimal
from typing import Any

from bson import Decimal128, ObjectId

_HEX24 = re.compile(r"^[0-9a-f]{24}$")


def para_bson(valor: Any, chave: str = "") -> Any:
    """Decimal → Decimal128; identificadores hexadecimais (*_id) → ObjectId."""
    if isinstance(valor, dict):
        return {k: para_bson(v, k) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [para_bson(v, chave) for v in valor]
    if isinstance(valor, Decimal):
        return Decimal128(str(valor))
    if isinstance(valor, str) and (chave == "_id" or chave.endswith("_id")) and _HEX24.match(valor):
        return ObjectId(valor)
    return valor


def de_bson(valor: Any) -> Any:
    """Caminho inverso, usado ao devolver dados para a aplicação."""
    if isinstance(valor, dict):
        return {k: de_bson(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [de_bson(v) for v in valor]
    if isinstance(valor, Decimal128):
        return valor.to_decimal()
    if isinstance(valor, ObjectId):
        return str(valor)
    return valor
