"""Testes do módulo concorrente: 10+ pontos simultâneos, sem perda e sem duplicidade."""

import asyncio
from datetime import UTC, datetime

import pytest

from ecotrack.concorrencia.ingestao import ProcessadorEventosAssincrono
from ecotrack.dominio.entidades import EventoTelemetria, PontoDeColeta
from ecotrack.persistencia.memoria import RepositorioPontosMemoria, RepositorioTelemetriaMemoria
from ecotrack.servicos.observadores import AtualizadorOcupacao, GeradorAlertaColeta

INICIO = datetime(2026, 11, 13, 8, 0, tzinfo=UTC)


def criar_pontos(quantidade: int) -> list[PontoDeColeta]:
    return [
        PontoDeColeta(
            f"p{i:02d}", f"PC-{i:03d}", f"Ponto {i}", -23.4 - i / 100, -51.9, 500.0, ocupacao_percentual=70.0
        )
        for i in range(quantidade)
    ]


@pytest.mark.parametrize("consumidores", [1, 4, 16])
def test_ingestao_de_12_pontos_simultaneos_sem_perda_nem_duplicidade(consumidores: int) -> None:
    repositorio = RepositorioTelemetriaMemoria()
    processador = ProcessadorEventosAssincrono(repositorio, consumidores=consumidores, tamanho_fila=64)
    estatisticas = asyncio.run(
        processador.executar_simulacao(
            criar_pontos(12), leituras_por_ponto=150, probabilidade_reenvio=0.2, inicio=INICIO
        )
    )
    assert estatisticas.pontos == 12
    assert estatisticas.reenvios_emitidos > 0
    assert estatisticas.sem_perda_nem_duplicidade
    assert asyncio.run(repositorio.contar()) == 12 * 150


def test_mesma_leitura_processada_em_paralelo_e_gravada_uma_unica_vez() -> None:
    repositorio = RepositorioTelemetriaMemoria()
    processador = ProcessadorEventosAssincrono(repositorio)
    leitura = EventoTelemetria("p01", "IOT-PC-001", 7, INICIO, "OCUPACAO", 50.0, "%")

    async def disparar_em_paralelo() -> list[bool]:
        return list(await asyncio.gather(*(processador.processar(leitura) for _ in range(50))))

    resultados = asyncio.run(disparar_em_paralelo())
    assert resultados.count(True) == 1
    assert asyncio.run(repositorio.contar()) == 1


def test_observadores_atualizam_ocupacao_e_geram_alerta() -> None:
    pontos = criar_pontos(10)
    repositorio_pontos = RepositorioPontosMemoria(pontos)
    alertas = GeradorAlertaColeta(limite_percentual=72.0)
    processador = ProcessadorEventosAssincrono(
        RepositorioTelemetriaMemoria(), (AtualizadorOcupacao(repositorio_pontos), alertas), consumidores=4
    )
    asyncio.run(processador.executar_simulacao(pontos, leituras_por_ponto=100, inicio=INICIO))
    atualizados = asyncio.run(repositorio_pontos.listar())
    assert all(p.ocupacao_atualizada_em is not None for p in atualizados)
    assert len(alertas.alertas) == 10
