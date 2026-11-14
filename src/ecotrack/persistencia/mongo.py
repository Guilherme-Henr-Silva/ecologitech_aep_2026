"""Implementações dos repositórios sobre o MongoDB (API assíncrona do PyMongo).

Cada classe recebe a instância do banco pelo construtor (injeção de dependência)
e converte entre objetos de domínio e documentos BSON.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from ecotrack.dominio.entidades import Equipamento, EventoRastreabilidade, EventoTelemetria, PontoDeColeta
from ecotrack.dominio.enums import EtapaCiclo, StatusEquipamento, TipoEvento
from ecotrack.dominio.fabrica import FabricaEquipamento
from ecotrack.persistencia.conversores import de_bson, para_bson
from ecotrack.persistencia.protocolos import ConflitoDeVersaoError

Documento = dict[str, Any]


class RepositorioEquipamentoMongo:
    def __init__(self, banco: AsyncDatabase[Documento]) -> None:
        self._colecao = banco["equipamentos"]

    async def salvar(self, entidade: Equipamento) -> None:
        documento = para_bson(entidade.para_documento())
        if entidade.versao == 1:
            documento["recebido_em"] = datetime.now(UTC)
            await self._colecao.insert_one(documento)
            return
        resultado = await self._colecao.update_one(
            {"codigo_rastreio": entidade.codigo_rastreio, "versao": entidade.versao - 1},
            {"$set": documento},
        )
        if resultado.matched_count == 0:
            raise ConflitoDeVersaoError(entidade.codigo_rastreio)

    async def buscar(self, chave: str) -> Equipamento | None:
        documento = await self._colecao.find_one({"codigo_rastreio": chave})
        return FabricaEquipamento.criar(de_bson(documento)) if documento else None

    async def listar_por_status(self, status: StatusEquipamento, limite: int = 100) -> Sequence[Equipamento]:
        cursor = self._colecao.find({"status": status.value}).sort("recebido_em", -1).limit(limite)
        return [FabricaEquipamento.criar(de_bson(d)) async for d in cursor]


class RepositorioEventoMongo:
    def __init__(self, banco: AsyncDatabase[Documento]) -> None:
        self._eventos = banco["eventos_rastreabilidade"]
        self._equipamentos = banco["equipamentos"]

    async def _id_do_equipamento(self, codigo_rastreio: str) -> ObjectId | None:
        documento = await self._equipamentos.find_one({"codigo_rastreio": codigo_rastreio}, {"_id": 1})
        return documento["_id"] if documento else None

    async def inserir(self, evento: EventoRastreabilidade) -> bool:
        equipamento_id = await self._id_do_equipamento(evento.codigo_rastreio)
        matricula, nome = evento.responsavel
        try:
            await self._eventos.insert_one(
                {
                    "evento_chave": evento.evento_chave,
                    "equipamento_id": equipamento_id,
                    "codigo_rastreio": evento.codigo_rastreio,
                    "etapa": evento.etapa.value,
                    "tipo": evento.tipo.value,
                    "ts": evento.ts,
                    "responsavel": {"matricula": matricula, "nome": nome},
                    "dados": dict(evento.dados),
                    "hash_anterior": evento.hash_anterior,
                    "hash": evento.hash,
                }
            )
        except DuplicateKeyError:
            return False  # reenvio: o índice uk_evento_idempotente barrou a duplicata
        return True

    async def ultimo_hash(self, codigo_rastreio: str) -> str | None:
        equipamento_id = await self._id_do_equipamento(codigo_rastreio)
        ultimo = await self._eventos.find_one(
            {"equipamento_id": equipamento_id}, sort=[("ts", -1), ("_id", -1)]
        )
        return ultimo["hash"] if ultimo else None

    async def historico(self, codigo_rastreio: str) -> Sequence[EventoRastreabilidade]:
        equipamento_id = await self._id_do_equipamento(codigo_rastreio)
        cursor = self._eventos.find({"equipamento_id": equipamento_id}).sort(
            [("ts", 1), ("_id", 1)]
        )  # ix_historico_item
        return [
            EventoRastreabilidade(
                evento_chave=d["evento_chave"],
                codigo_rastreio=d["codigo_rastreio"],
                etapa=EtapaCiclo(d["etapa"]),
                tipo=TipoEvento(d["tipo"]),
                ts=d["ts"],
                responsavel=(d["responsavel"]["matricula"], d["responsavel"]["nome"]),
                hash_anterior=d.get("hash_anterior"),
                hash=d["hash"],
                dados=tuple(d.get("dados", {}).items()),
            )
            async for d in cursor
        ]


class RepositorioTriagemMongo:
    """Grava a triagem como referência com extensão (copia campos do equipamento e evita $lookup)."""

    def __init__(self, banco: AsyncDatabase[Documento]) -> None:
        self._colecao = banco["triagens"]
        self._equipamentos = banco["equipamentos"]

    async def salvar(self, documento: dict[str, Any]) -> None:
        equipamento = await self._equipamentos.find_one({"codigo_rastreio": documento["codigo_rastreio"]})
        origem = equipamento or {}
        extensao = {
            "equipamento_id": origem.get("_id"),
            "cliente_id": origem.get("cliente_id"),
            "ponto_coleta_id": origem.get("ponto_coleta_id"),
            "coletado_em": origem.get("recebido_em"),
        }
        presentes = {campo: valor for campo, valor in extensao.items() if valor is not None}
        await self._colecao.insert_one({**para_bson(documento), **presentes})


class RepositorioTelemetriaMongo:
    def __init__(self, banco: AsyncDatabase[Documento]) -> None:
        self._controle = banco["controle_ingestao"]
        self._leituras = banco["leituras_telemetria"]

    async def registrar_se_inedita(self, chave: str) -> bool:
        try:
            await self._controle.insert_one({"_id": chave, "registrada_em": datetime.now(UTC)})
        except DuplicateKeyError:
            return False
        return True

    async def inserir(self, leitura: EventoTelemetria) -> None:
        await self._leituras.insert_one(
            {
                "ts": leitura.ts,
                "meta": {
                    "ponto_id": ObjectId(leitura.ponto_id),
                    "dispositivo_id": leitura.dispositivo_id,
                    "tipo": leitura.tipo,
                },
                "valor": float(leitura.valor),
                "unidade": leitura.unidade,
                "seq": leitura.seq,
            }
        )

    async def contar(self) -> int:
        return int(await self._leituras.count_documents({}))


class RepositorioPontosMongo:
    def __init__(self, banco: AsyncDatabase[Documento]) -> None:
        self._colecao = banco["pontos_coleta"]

    async def listar(self) -> Sequence[PontoDeColeta]:
        cursor = self._colecao.find({"status": "ATIVO"})
        return [
            PontoDeColeta(
                id=str(d["_id"]),
                codigo=d["codigo"],
                nome=d["nome"],
                longitude=d["localizacao"]["coordinates"][0],
                latitude=d["localizacao"]["coordinates"][1],
                capacidade_kg=d["capacidade_kg"],
                limite_alerta_percentual=d.get("limite_alerta_percentual", 80.0),
                ocupacao_percentual=d.get("ocupacao", {}).get("percentual", 0.0),
                ocupacao_atualizada_em=d.get("ocupacao", {}).get("atualizada_em"),
            )
            async for d in cursor
        ]

    async def atualizar_ocupacao(self, ponto_id: str, percentual: float, medido_em: datetime) -> None:
        # Atualização condicional e atômica: leitura atrasada não sobrescreve a mais nova.
        await self._colecao.update_one(
            {
                "_id": ObjectId(ponto_id),
                "$or": [
                    {"ocupacao.atualizada_em": {"$lt": medido_em}},
                    {"ocupacao.atualizada_em": {"$exists": False}},
                ],
            },
            {"$set": {"ocupacao.percentual": float(percentual), "ocupacao.atualizada_em": medido_em}},
        )


class RepositorioConsultasMongo:
    def __init__(self, banco: AsyncDatabase[Documento]) -> None:
        self._banco = banco

    async def executar(self, colecao: str, pipeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cursor = await self._banco[colecao].aggregate(pipeline)
        return [de_bson(documento) async for documento in cursor]
