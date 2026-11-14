"""Serviço de precificação: orquestra a estratégia (POO) e o pipeline funcional."""

from collections.abc import Iterable
from decimal import Decimal

from ecotrack.dominio.entidades import Equipamento
from ecotrack.funcional.precificacao import agregar, precificar
from ecotrack.funcional.tipos import ItemAvaliado, Resumo, TabelaMateriais
from ecotrack.servicos.estrategias import EstrategiaPrecificacao


class ServicoPrecificacao:
    def __init__(
        self, estrategia: EstrategiaPrecificacao, tabela: TabelaMateriais, versao_tabela: int
    ) -> None:
        self._estrategia = estrategia
        self._avaliar = precificar(tabela, versao_tabela)

    @property
    def estrategia(self) -> str:
        return self._estrategia.nome

    def definir_estrategia(self, estrategia: EstrategiaPrecificacao) -> None:
        self._estrategia = estrategia

    def precificar(self, equipamento: Equipamento) -> Decimal:
        return self._estrategia.calcular(equipamento.para_item_triagem())

    def avaliar(self, equipamento: Equipamento) -> ItemAvaliado:
        return self._avaliar(equipamento.para_item_triagem())

    def precificar_lote(self, equipamentos: Iterable[Equipamento]) -> Resumo:
        return agregar(self.avaliar(e) for e in equipamentos)
