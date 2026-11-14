"""Sugestão de rota a partir da ocupação corrente dos pontos."""

from ecotrack.funcional.rotas import PontoRota, RotaSugerida, sugerir_rota
from ecotrack.persistencia.protocolos import RepositorioPontos


class ServicoRoteirizacao:
    def __init__(
        self, pontos: RepositorioPontos, deposito: tuple[float, float], capacidade_veiculo_kg: float
    ) -> None:
        self._pontos = pontos
        self._deposito = deposito
        self._capacidade = capacidade_veiculo_kg

    async def sugerir(self, limite_percentual: float = 70.0) -> RotaSugerida:
        pontos = await self._pontos.listar()
        candidatos = tuple(
            PontoRota(p.id, p.nome, p.latitude, p.longitude, p.ocupacao_percentual, p.massa_estimada_kg)
            for p in pontos
        )
        return sugerir_rota(self._deposito, candidatos, limite_percentual, self._capacidade)
