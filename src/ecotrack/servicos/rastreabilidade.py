"""Cadeia de custódia: eventos imutáveis encadeados por hash SHA-256."""

import asyncio
import hashlib
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from ecotrack.dominio.entidades import EventoRastreabilidade
from ecotrack.dominio.enums import EtapaCiclo, TipoEvento
from ecotrack.persistencia.protocolos import RepositorioEvento

Relogio = Callable[[], datetime]


def calcular_hash(
    codigo_rastreio: str,
    etapa: EtapaCiclo,
    tipo: TipoEvento,
    ts: datetime,
    matricula: str,
    hash_anterior: str | None,
) -> str:
    """Mesma fórmula usada na rotina de verificação do banco (database/04_rotinas_consistencia.js)."""
    conteudo = "|".join(
        (
            codigo_rastreio,
            etapa.value,
            tipo.value,
            ts.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            matricula,
            hash_anterior or "GENESIS",
        )
    )
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


def cadeia_integra(eventos: Sequence[EventoRastreabilidade]) -> bool:
    """Recalcula o encadeamento: qualquer alteração retroativa quebra a cadeia."""
    hash_esperado: str | None = None
    for evento in eventos:
        recalculado = calcular_hash(
            evento.codigo_rastreio, evento.etapa, evento.tipo, evento.ts, evento.responsavel[0], hash_esperado
        )
        if evento.hash_anterior != hash_esperado or evento.hash != recalculado:
            return False
        hash_esperado = evento.hash
    return True


class ServicoRastreabilidade:
    def __init__(self, repositorio: RepositorioEvento, relogio: Relogio = lambda: datetime.now(UTC)) -> None:
        self._repositorio = repositorio
        self._relogio = relogio
        # Uma trava por item (e não uma global): itens diferentes nunca esperam um pelo outro.
        self._travas: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def registrar_etapa(
        self,
        codigo_rastreio: str,
        etapa: EtapaCiclo,
        tipo: TipoEvento,
        responsavel: tuple[str, str],
        dados: dict[str, Any] | None = None,
    ) -> EventoRastreabilidade | None:
        async with self._travas[codigo_rastreio]:
            hash_anterior = await self._repositorio.ultimo_hash(codigo_rastreio)
            ts = self._relogio().replace(microsecond=0)
            evento = EventoRastreabilidade(
                evento_chave=f"{etapa.value}:{tipo.value}",
                codigo_rastreio=codigo_rastreio,
                etapa=etapa,
                tipo=tipo,
                ts=ts,
                responsavel=responsavel,
                hash_anterior=hash_anterior,
                hash=calcular_hash(codigo_rastreio, etapa, tipo, ts, responsavel[0], hash_anterior),
                dados=tuple((dados or {}).items()),
            )
            inserido = await self._repositorio.inserir(evento)
            return evento if inserido else None

    async def historico(self, codigo_rastreio: str) -> Sequence[EventoRastreabilidade]:
        return await self._repositorio.historico(codigo_rastreio)

    async def verificar(self, codigo_rastreio: str) -> bool:
        return cadeia_integra(await self.historico(codigo_rastreio))
