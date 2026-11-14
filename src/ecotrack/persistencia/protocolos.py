"""Contratos de persistência (padrão Repository).

Os serviços dependem apenas destes protocolos. A implementação concreta
(MongoDB ou memória) é escolhida no Container e injetada pelo construtor.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol, TypeVar

from ecotrack.dominio.entidades import Equipamento, EventoRastreabilidade, EventoTelemetria, PontoDeColeta
from ecotrack.dominio.enums import StatusEquipamento

T = TypeVar("T")


class ConflitoDeVersaoError(Exception):
    """Outra gravação alterou o documento entre a leitura e a escrita (concorrência otimista)."""


class Repositorio(Protocol[T]):
    async def salvar(self, entidade: T) -> None: ...
    async def buscar(self, chave: str) -> T | None: ...


class RepositorioEquipamento(Repositorio[Equipamento], Protocol):
    async def listar_por_status(
        self, status: StatusEquipamento, limite: int = 100
    ) -> Sequence[Equipamento]: ...


class RepositorioEvento(Protocol):
    async def inserir(self, evento: EventoRastreabilidade) -> bool:
        """Devolve False quando o evento já existe (idempotência)."""
        ...

    async def ultimo_hash(self, codigo_rastreio: str) -> str | None: ...
    async def historico(self, codigo_rastreio: str) -> Sequence[EventoRastreabilidade]: ...


class RepositorioTriagem(Protocol):
    async def salvar(self, documento: dict[str, Any]) -> None: ...


class RepositorioTelemetria(Protocol):
    async def registrar_se_inedita(self, chave: str) -> bool:
        """Operação atômica: True na primeira vez que a chave aparece, False nos reenvios."""
        ...

    async def inserir(self, leitura: EventoTelemetria) -> None: ...
    async def contar(self) -> int: ...


class RepositorioPontos(Protocol):
    async def listar(self) -> Sequence[PontoDeColeta]: ...
    async def atualizar_ocupacao(self, ponto_id: str, percentual: float, medido_em: datetime) -> None: ...


class RepositorioConsultas(Protocol):
    async def executar(self, colecao: str, pipeline: list[dict[str, Any]]) -> list[dict[str, Any]]: ...
