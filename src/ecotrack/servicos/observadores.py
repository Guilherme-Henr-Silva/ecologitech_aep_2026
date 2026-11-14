"""Padrão Observer: ações disparadas a cada leitura de telemetria persistida."""

from typing import Protocol

from ecotrack.dominio.entidades import EventoTelemetria
from ecotrack.persistencia.protocolos import RepositorioPontos

TIPO_OCUPACAO = "OCUPACAO"


class ObservadorEvento(Protocol):
    async def atualizar(self, leitura: EventoTelemetria) -> None: ...


class AtualizadorOcupacao:
    """Mantém a ocupação corrente incorporada no documento do ponto (padrão de acesso PA02)."""

    def __init__(self, pontos: RepositorioPontos) -> None:
        self._pontos = pontos

    async def atualizar(self, leitura: EventoTelemetria) -> None:
        if leitura.tipo == TIPO_OCUPACAO:
            await self._pontos.atualizar_ocupacao(leitura.ponto_id, leitura.valor, leitura.ts)


class GeradorAlertaColeta:
    """Registra o primeiro alerta de cada ponto que ultrapassa o limite de ocupação."""

    def __init__(self, limite_percentual: float) -> None:
        self._limite = limite_percentual
        self._alertados: dict[str, float] = {}

    @property
    def alertas(self) -> dict[str, float]:
        return dict(self._alertados)

    async def atualizar(self, leitura: EventoTelemetria) -> None:
        if leitura.tipo == TIPO_OCUPACAO and leitura.valor >= self._limite:
            self._alertados.setdefault(leitura.ponto_id, leitura.valor)
