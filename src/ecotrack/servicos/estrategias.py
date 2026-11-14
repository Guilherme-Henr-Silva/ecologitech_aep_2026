"""Padrão Strategy: políticas de precificação intercambiáveis.

Toda estratégia delega o cálculo a funções puras do módulo funcional; a
orientação a objetos só organiza qual regra é usada em cada situação.
"""

from collections.abc import Mapping
from decimal import Decimal
from typing import Protocol

from ecotrack.funcional.precificacao import valor_item
from ecotrack.funcional.tipos import CENTAVO, ItemTriagem, TabelaMateriais


class EstrategiaPrecificacao(Protocol):
    nome: str

    def calcular(self, item: ItemTriagem) -> Decimal: ...


class PrecificacaoPorComponente:
    """Soma a contribuição de cada material recuperável (regra padrão)."""

    nome = "por_componente"

    def __init__(self, tabela: TabelaMateriais) -> None:
        self._tabela = tabela

    def calcular(self, item: ItemTriagem) -> Decimal:
        return valor_item(item, self._tabela)


class PrecificacaoPorMassa:
    """Valor médio por quilo, usado quando a composição ainda não foi levantada."""

    nome = "por_massa"

    def __init__(self, preco_medio_por_kg: Decimal) -> None:
        self._preco = preco_medio_por_kg

    def calcular(self, item: ItemTriagem) -> Decimal:
        return (Decimal(str(item.massa_kg)) * self._preco).quantize(CENTAVO)


class PrecificacaoSpotMercado:
    """Aplica a cotação do dia (fator multiplicador por material) sobre a regra por componente."""

    nome = "spot_mercado"

    def __init__(self, tabela: TabelaMateriais, cotacoes: Mapping[str, Decimal]) -> None:
        self._tabela = tabela
        self._cotacoes = cotacoes

    def calcular(self, item: ItemTriagem) -> Decimal:
        total = Decimal("0")
        for componente in item.componentes:
            material = self._tabela[componente.material_codigo]
            fator = self._cotacoes.get(componente.material_codigo, Decimal("1"))
            massa = Decimal(str(round(componente.massa_kg * material.rendimento, 6)))
            total += massa * material.preco_por_kg * fator
        return total.quantize(CENTAVO)
