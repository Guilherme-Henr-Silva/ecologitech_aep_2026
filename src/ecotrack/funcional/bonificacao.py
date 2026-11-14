"""Pipeline 2 – bonificação de clientes (seção 9.4.3 da 1ª entrega).

pontos(cl) = Σ [ α·massaRec(l) + β·co₂(l) + γ·recondicionados(l) ],  l ∈ L(cl)
faixa(x)   = BRONZE | PRATA | OURO | PLATINA  (função escalonada)
bônus(cl)  = δ(faixa(pontos(cl)))
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from itertools import groupby
from operator import itemgetter

from ecotrack.dominio.enums import FaixaBonus
from ecotrack.funcional.parametros import (
    DESCONTO_POR_FAIXA,
    LIMITES_FAIXA,
    PESO_CO2,
    PESO_MASSA,
    PESO_RECONDICIONADO,
)
from ecotrack.funcional.tipos import Resumo


@dataclass(frozen=True, slots=True)
class Bonus:
    cliente_id: str
    pontos: int
    faixa: FaixaBonus
    desconto: Decimal


def pontos_do_lote(resumo: Resumo) -> float:
    return (
        PESO_MASSA * resumo.massa_recuperada_kg
        + PESO_CO2 * resumo.co2_evitado_kg
        + PESO_RECONDICIONADO * resumo.recondicionados
    )


def pontos(resumos_dos_lotes: Iterable[Resumo]) -> int:
    """Soma de termos não negativos: a função é monotônica e nunca negativa."""
    return round(sum(map(pontos_do_lote, resumos_dos_lotes)))


def faixa(total_pontos: int, limites: tuple[int, int, int] = LIMITES_FAIXA) -> FaixaBonus:
    t1, t2, t3 = limites
    if total_pontos >= t3:
        return FaixaBonus.PLATINA
    if total_pontos >= t2:
        return FaixaBonus.OURO
    if total_pontos >= t1:
        return FaixaBonus.PRATA
    return FaixaBonus.BRONZE


def bonus(
    cliente_id: str,
    resumos_dos_lotes: Iterable[Resumo],
    descontos: Mapping[FaixaBonus, Decimal] = DESCONTO_POR_FAIXA,
) -> Bonus:
    total = pontos(resumos_dos_lotes)
    faixa_cliente = faixa(total)
    return Bonus(cliente_id, total, faixa_cliente, descontos[faixa_cliente])


def ranking(lotes_por_cliente: Iterable[tuple[str, Resumo]]) -> tuple[Bonus, ...]:
    """Agrupa (cliente_id, resumo) por cliente e devolve o ranking decrescente de pontos."""
    ordenados = sorted(lotes_por_cliente, key=itemgetter(0))
    bonus_por_cliente = (
        bonus(cliente, map(itemgetter(1), grupo)) for cliente, grupo in groupby(ordenados, key=itemgetter(0))
    )
    return tuple(sorted(bonus_por_cliente, key=lambda b: (-b.pontos, b.cliente_id)))
