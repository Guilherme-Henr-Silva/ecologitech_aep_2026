"""Implementações em memória dos repositórios (duplos de teste e modo demonstração).

Cada método faz a verificação e a gravação sem nenhum `await` no meio. Como o
asyncio só troca de tarefa em um `await`, essas operações são atômicas no laço
de eventos, reproduzindo a garantia que o índice único dá no MongoDB.
"""

import copy
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from ecotrack.dominio.entidades import Equipamento, EventoRastreabilidade, EventoTelemetria, PontoDeColeta
from ecotrack.dominio.enums import StatusEquipamento
from ecotrack.persistencia.protocolos import ConflitoDeVersaoError


class RepositorioEquipamentoMemoria:
    def __init__(self) -> None:
        self._dados: dict[str, Equipamento] = {}
        self._versoes: dict[str, int] = {}

    async def salvar(self, entidade: Equipamento) -> None:
        versao_gravada = self._versoes.get(entidade.codigo_rastreio)
        if versao_gravada is not None and entidade.versao <= versao_gravada:
            raise ConflitoDeVersaoError(entidade.codigo_rastreio)
        self._dados[entidade.codigo_rastreio] = copy.deepcopy(entidade)
        self._versoes[entidade.codigo_rastreio] = entidade.versao

    async def buscar(self, chave: str) -> Equipamento | None:
        encontrado = self._dados.get(chave)
        return copy.deepcopy(encontrado) if encontrado else None

    async def listar_por_status(self, status: StatusEquipamento, limite: int = 100) -> Sequence[Equipamento]:
        return [copy.deepcopy(e) for e in self._dados.values() if e.status is status][:limite]


class RepositorioEventoMemoria:
    def __init__(self) -> None:
        self._eventos: dict[str, list[EventoRastreabilidade]] = defaultdict(list)
        self._chaves: set[tuple[str, str]] = set()

    async def inserir(self, evento: EventoRastreabilidade) -> bool:
        chave = (evento.codigo_rastreio, evento.evento_chave)
        if chave in self._chaves:
            return False
        self._chaves.add(chave)
        self._eventos[evento.codigo_rastreio].append(evento)
        return True

    async def ultimo_hash(self, codigo_rastreio: str) -> str | None:
        eventos = self._eventos.get(codigo_rastreio)
        return eventos[-1].hash if eventos else None

    async def historico(self, codigo_rastreio: str) -> Sequence[EventoRastreabilidade]:
        return tuple(sorted(self._eventos.get(codigo_rastreio, ()), key=lambda e: e.ts))


class RepositorioTriagemMemoria:
    def __init__(self) -> None:
        self.documentos: list[dict[str, Any]] = []

    async def salvar(self, documento: dict[str, Any]) -> None:
        self.documentos.append(dict(documento))


class RepositorioTelemetriaMemoria:
    def __init__(self) -> None:
        self._chaves: set[str] = set()
        self._leituras: list[EventoTelemetria] = []

    async def registrar_se_inedita(self, chave: str) -> bool:
        if chave in self._chaves:
            return False
        self._chaves.add(chave)
        return True

    async def inserir(self, leitura: EventoTelemetria) -> None:
        self._leituras.append(leitura)

    async def contar(self) -> int:
        return len(self._leituras)


class RepositorioPontosMemoria:
    def __init__(self, pontos: Sequence[PontoDeColeta]) -> None:
        self._pontos = {p.id: p for p in pontos}

    async def listar(self) -> Sequence[PontoDeColeta]:
        return [copy.copy(p) for p in self._pontos.values()]

    async def atualizar_ocupacao(self, ponto_id: str, percentual: float, medido_em: datetime) -> None:
        ponto = self._pontos[ponto_id]
        if ponto.ocupacao_atualizada_em is None or medido_em > ponto.ocupacao_atualizada_em:
            ponto.ocupacao_percentual = percentual
            ponto.ocupacao_atualizada_em = medido_em
