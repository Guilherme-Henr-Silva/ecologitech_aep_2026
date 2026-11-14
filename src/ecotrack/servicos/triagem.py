"""Caso de uso de recebimento e triagem de equipamentos."""

from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from ecotrack.dominio.entidades import Equipamento
from ecotrack.dominio.enums import EtapaCiclo, TipoEvento
from ecotrack.dominio.fabrica import FabricaEquipamento
from ecotrack.funcional.tipos import ItemAvaliado
from ecotrack.persistencia.protocolos import RepositorioEquipamento, RepositorioTriagem
from ecotrack.servicos.precificacao import ServicoPrecificacao
from ecotrack.servicos.rastreabilidade import ServicoRastreabilidade

Responsavel = tuple[str, str]


class EquipamentoNaoEncontradoError(LookupError):
    pass


class ServicoTriagem:
    def __init__(
        self,
        equipamentos: RepositorioEquipamento,
        triagens: RepositorioTriagem,
        precificador: ServicoPrecificacao,
        rastreabilidade: ServicoRastreabilidade,
        relogio: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._equipamentos = equipamentos
        self._triagens = triagens
        self._precificador = precificador
        self._rastreabilidade = rastreabilidade
        self._relogio = relogio

    async def receber(self, documento: Mapping[str, Any], responsavel: Responsavel) -> Equipamento:
        equipamento = FabricaEquipamento.criar(documento)
        await self._equipamentos.salvar(equipamento)
        await self._rastreabilidade.registrar_etapa(
            equipamento.codigo_rastreio,
            EtapaCiclo.COLETA,
            TipoEvento.ENTRADA,
            responsavel,
            {"peso_kg": equipamento.peso_kg},
        )
        return equipamento

    async def triar(self, codigo_rastreio: str, responsavel: Responsavel) -> ItemAvaliado:
        equipamento = await self._buscar(codigo_rastreio)
        iniciada_em = self._relogio()
        equipamento.iniciar_triagem()
        await self._equipamentos.salvar(equipamento)
        await self._registrar(equipamento, EtapaCiclo.TRIAGEM, TipoEvento.ENTRADA, responsavel)

        if equipamento.exige_sanitizacao():
            await self._registrar(
                equipamento,
                EtapaCiclo.TRIAGEM,
                TipoEvento.SANITIZACAO,
                responsavel,
                {"metodo": "NIST 800-88 purge"},
            )

        avaliado = self._precificador.avaliar(equipamento)
        etapa_destino = equipamento.registrar_destino(avaliado.destino)
        await self._equipamentos.salvar(equipamento)
        await self._triagens.salvar(self._documento_triagem(equipamento, avaliado, responsavel, iniciada_em))
        await self._registrar(
            equipamento,
            EtapaCiclo.TRIAGEM,
            TipoEvento.SAIDA,
            responsavel,
            {"destino": avaliado.destino.value},
        )
        await self._registrar(equipamento, etapa_destino, TipoEvento.DESTINACAO, responsavel)
        return avaliado

    async def _buscar(self, codigo_rastreio: str) -> Equipamento:
        equipamento = await self._equipamentos.buscar(codigo_rastreio)
        if equipamento is None:
            raise EquipamentoNaoEncontradoError(codigo_rastreio)
        return equipamento

    async def _registrar(
        self,
        equipamento: Equipamento,
        etapa: EtapaCiclo,
        tipo: TipoEvento,
        responsavel: Responsavel,
        dados: dict[str, Any] | None = None,
    ) -> None:
        await self._rastreabilidade.registrar_etapa(
            equipamento.codigo_rastreio, etapa, tipo, responsavel, dados
        )

    def _documento_triagem(
        self,
        equipamento: Equipamento,
        avaliado: ItemAvaliado,
        responsavel: Responsavel,
        iniciada_em: datetime,
    ) -> dict[str, Any]:
        return {
            "codigo_rastreio": equipamento.codigo_rastreio,
            "categoria_equipamento": equipamento.categoria.value,
            "peso_kg": float(equipamento.peso_kg),
            "lote_id": equipamento.lote_id,
            "responsavel": {"matricula": responsavel[0], "nome": responsavel[1]},
            "status": "CONCLUIDA",
            "iniciada_em": iniciada_em,
            "concluida_em": self._relogio(),
            "avaliacao": {
                "tabela_versao": avaliado.tabela_versao,
                "valor_estimado": avaliado.valor_estimado,
                "custo_atribuido": avaliado.custo_atribuido,
                "margem": avaliado.margem,
                "co2_evitado_kg": avaliado.co2_evitado_kg,
                "massa_reciclavel_kg": avaliado.massa_reciclavel_kg,
            },
            "materiais_recuperados": [asdict(m) for m in avaliado.materiais_recuperados],
            "destino": avaliado.destino.value,
        }
