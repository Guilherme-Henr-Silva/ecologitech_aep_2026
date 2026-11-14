"""Módulo concorrente/assíncrono: ingestão simultânea de telemetria de vários pontos.

Como a corrida de dados é evitada:
* cada produtor (ponto de coleta) tem seu próprio gerador aleatório e sua própria
  sequência; nada é compartilhado entre produtores;
* produtores e consumidores só se comunicam pela asyncio.Queue, que é segura
  para uso concorrente e aplica contrapressão quando está cheia;
* os consumidores não somam em variáveis globais: cada um devolve um resultado
  imutável, e os resultados são combinados no final com uma redução (monoide);
* a deduplicação é uma operação atômica do repositório (índice único no MongoDB),
  então dois consumidores nunca gravam a mesma leitura.
"""

import asyncio
import random
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import reduce

from ecotrack.dominio.entidades import EventoTelemetria, PontoDeColeta
from ecotrack.persistencia.protocolos import RepositorioTelemetria
from ecotrack.servicos.observadores import TIPO_OCUPACAO, ObservadorEvento

FIM_DA_FILA = None


@dataclass(frozen=True, slots=True)
class ResultadoProdutor:
    ponto_id: str
    leituras_unicas: int
    reenvios: int


@dataclass(frozen=True, slots=True)
class ResultadoConsumidor:
    persistidas: int = 0
    duplicadas_descartadas: int = 0

    def __add__(self, outro: "ResultadoConsumidor") -> "ResultadoConsumidor":
        return ResultadoConsumidor(
            self.persistidas + outro.persistidas, self.duplicadas_descartadas + outro.duplicadas_descartadas
        )


@dataclass(frozen=True, slots=True)
class EstatisticasIngestao:
    pontos: int
    consumidores: int
    leituras_unicas_emitidas: int
    reenvios_emitidos: int
    persistidas: int
    duplicadas_descartadas: int
    duracao_s: float

    @property
    def sem_perda_nem_duplicidade(self) -> bool:
        return (
            self.persistidas == self.leituras_unicas_emitidas
            and self.duplicadas_descartadas == self.reenvios_emitidos
        )

    @property
    def vazao_por_segundo(self) -> float:
        total = self.persistidas + self.duplicadas_descartadas
        return round(total / self.duracao_s, 1) if self.duracao_s else 0.0


async def simular_ponto(
    ponto: PontoDeColeta,
    total_leituras: int,
    fila: asyncio.Queue[EventoTelemetria | None],
    semente: int,
    probabilidade_reenvio: float,
    inicio: datetime,
) -> ResultadoProdutor:
    """Produtor: simula o dispositivo IoT de um ponto enviando leituras, às vezes repetidas."""
    gerador = random.Random(semente)  # gerador local: nenhum estado compartilhado
    dispositivo_id = f"IOT-{ponto.codigo}"
    ocupacao = ponto.ocupacao_percentual
    reenvios = 0
    for seq in range(1, total_leituras + 1):
        ocupacao = max(0.0, min(100.0, ocupacao + gerador.uniform(-0.05, 0.15)))
        leitura = EventoTelemetria(
            ponto_id=ponto.id,
            dispositivo_id=dispositivo_id,
            seq=seq,
            ts=inicio + timedelta(seconds=30 * seq),
            tipo=TIPO_OCUPACAO,
            valor=round(ocupacao, 1),
            unidade="%",
        )
        await fila.put(leitura)
        if gerador.random() < probabilidade_reenvio:  # falha de rede: o dispositivo reenvia
            await fila.put(leitura)
            reenvios += 1
        await asyncio.sleep(gerador.uniform(0, 0.002))  # intervalo irregular entre envios
    return ResultadoProdutor(ponto.id, total_leituras, reenvios)


class ProcessadorEventosAssincrono:
    def __init__(
        self,
        repositorio: RepositorioTelemetria,
        observadores: Sequence[ObservadorEvento] = (),
        consumidores: int = 8,
        tamanho_fila: int = 500,
    ) -> None:
        self._repositorio = repositorio
        self._observadores = list(observadores)
        self._consumidores = consumidores
        self._tamanho_fila = tamanho_fila

    def adicionar_observador(self, observador: ObservadorEvento) -> None:
        self._observadores.append(observador)

    async def processar(self, leitura: EventoTelemetria) -> bool:
        if not await self._repositorio.registrar_se_inedita(leitura.chave_idempotencia):
            return False
        await self._repositorio.inserir(leitura)
        await self._notificar(leitura)
        return True

    async def _notificar(self, leitura: EventoTelemetria) -> None:
        for observador in self._observadores:
            await observador.atualizar(leitura)

    async def _consumir(self, fila: asyncio.Queue[EventoTelemetria | None]) -> ResultadoConsumidor:
        persistidas = descartadas = 0  # variáveis locais da corrotina, não compartilhadas
        while (leitura := await fila.get()) is not FIM_DA_FILA:
            if await self.processar(leitura):
                persistidas += 1
            else:
                descartadas += 1
            fila.task_done()
        fila.task_done()
        return ResultadoConsumidor(persistidas, descartadas)

    async def executar_simulacao(
        self,
        pontos: Sequence[PontoDeColeta],
        leituras_por_ponto: int,
        probabilidade_reenvio: float = 0.08,
        semente: int = 2026,
        inicio: datetime | None = None,
    ) -> EstatisticasIngestao:
        fila: asyncio.Queue[EventoTelemetria | None] = asyncio.Queue(maxsize=self._tamanho_fila)
        inicio_simulado = inicio or datetime.now(UTC)
        relogio = time.perf_counter()

        async with asyncio.TaskGroup() as grupo:
            tarefas_consumo = [grupo.create_task(self._consumir(fila)) for _ in range(self._consumidores)]
            async with asyncio.TaskGroup() as grupo_produtores:
                tarefas_producao = [
                    grupo_produtores.create_task(
                        simular_ponto(
                            ponto,
                            leituras_por_ponto,
                            fila,
                            semente + indice,
                            probabilidade_reenvio,
                            inicio_simulado,
                        )
                    )
                    for indice, ponto in enumerate(pontos)
                ]
            for _ in tarefas_consumo:  # todos os produtores terminaram: avisa cada consumidor
                await fila.put(FIM_DA_FILA)

        produzido = [t.result() for t in tarefas_producao]
        consumido = reduce(lambda a, b: a + b, (t.result() for t in tarefas_consumo), ResultadoConsumidor())
        return EstatisticasIngestao(
            pontos=len(pontos),
            consumidores=self._consumidores,
            leituras_unicas_emitidas=sum(p.leituras_unicas for p in produzido),
            reenvios_emitidos=sum(p.reenvios for p in produzido),
            persistidas=consumido.persistidas,
            duplicadas_descartadas=consumido.duplicadas_descartadas,
            duracao_s=round(time.perf_counter() - relogio, 3),
        )
