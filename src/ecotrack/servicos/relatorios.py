"""Relatórios de impacto ambiental e operação: o banco agrega, o serviço só orquestra."""

from datetime import datetime
from typing import Any

from ecotrack.consultas import pipelines
from ecotrack.funcional.bonificacao import Bonus, ranking
from ecotrack.funcional.tipos import Resumo
from ecotrack.persistencia.protocolos import RepositorioConsultas

Linhas = list[dict[str, Any]]


class ServicoRelatorios:
    def __init__(self, consultas: RepositorioConsultas) -> None:
        self._consultas = consultas

    async def _executar(self, consulta: pipelines.Consulta) -> Linhas:
        colecao, pipeline = consulta
        return await self._consultas.executar(colecao, pipeline)

    async def co2_por_cliente(self, inicio: datetime, fim: datetime) -> Linhas:
        return await self._executar(pipelines.co2_por_cliente(inicio, fim))

    async def material_reciclado_no_mes(self, inicio_mes: datetime, fim_mes: datetime) -> Linhas:
        return await self._executar(pipelines.material_reciclado_no_mes(inicio_mes, fim_mes))

    async def tempo_medio_por_ponto(self) -> Linhas:
        return await self._executar(pipelines.tempo_medio_por_ponto())

    async def ocupacao_ultimas_24h(self, referencia: datetime) -> Linhas:
        return await self._executar(pipelines.ocupacao_ultimas_24h(referencia))

    async def destinacao_por_categoria(self) -> Linhas:
        return await self._executar(pipelines.destinacao_por_categoria())

    async def pontos_para_rota(self, longitude: float, latitude: float) -> Linhas:
        return await self._executar(pipelines.pontos_para_rota(longitude, latitude))

    async def ranking_bonificacao(self) -> tuple[Bonus, ...]:
        """Combina os dois mundos: o banco entrega os resumos e o pipeline funcional pontua."""
        linhas = await self._executar(pipelines.resumos_de_lotes_por_cliente())
        pares = (
            (
                linha["cliente"],
                Resumo(
                    massa_recuperada_kg=linha["massa_recuperada_kg"],
                    co2_evitado_kg=linha["co2_evitado_kg"],
                    recondicionados=int(linha["recondicionados"]),
                ),
            )
            for linha in linhas
        )
        return ranking(pares)
