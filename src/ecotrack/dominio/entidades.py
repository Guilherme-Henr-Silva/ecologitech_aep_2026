"""Núcleo do domínio (paradigma orientado a objetos).

As entidades têm identidade, estado e ciclo de vida. O comportamento que varia
por categoria fica nas subclasses de Equipamento (polimorfismo), e o esqueleto
comum de conversão para o pipeline fica na classe base (Template Method).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar

from ecotrack.dominio.enums import (
    ETAPA_POR_DESTINO,
    Categoria,
    Destino,
    EstadoEquipamento,
    EtapaCiclo,
    StatusEquipamento,
    TipoEvento,
)
from ecotrack.funcional.parametros import PARAMETROS_CATEGORIA
from ecotrack.funcional.tipos import ComponenteItem, ItemTriagem


class TransicaoInvalidaError(Exception):
    """Disparada quando uma operação não é permitida no status atual do equipamento."""


@dataclass(frozen=True, slots=True)
class Componente:
    tipo: str
    material_codigo: str
    massa_kg: float
    funcional: bool = False

    def para_item(self) -> ComponenteItem:
        return ComponenteItem(self.tipo, self.material_codigo, self.massa_kg, self.funcional)


class Equipamento(ABC):
    """Item recebido na cadeia de logística reversa (classe abstrata)."""

    categoria: ClassVar[Categoria]
    atributos_obrigatorios: ClassVar[tuple[str, ...]] = ()

    def __init__(
        self,
        codigo_rastreio: str,
        lote_id: str,
        peso_kg: float,
        estado: EstadoEquipamento,
        componentes: tuple[Componente, ...],
        atributos: Mapping[str, Any] | None = None,
        marca: str = "",
        modelo: str = "",
        status: StatusEquipamento = StatusEquipamento.RECEBIDO,
        etapa_atual: EtapaCiclo = EtapaCiclo.COLETA,
        versao: int = 1,
        origem: Mapping[str, str] | None = None,
    ) -> None:
        self.codigo_rastreio = codigo_rastreio
        self.lote_id = lote_id
        self.peso_kg = peso_kg
        self.estado = estado
        self.componentes = componentes
        self.atributos = dict(atributos or {})
        self.marca = marca
        self.modelo = modelo
        self.status = status
        self.etapa_atual = etapa_atual
        self.versao = versao
        self.destino: Destino | None = None
        self.origem = dict(origem or {})  # coleta_id, cliente_id e ponto_coleta_id
        self._validar_atributos()

    # ----------------------------------------------------------- polimorfismo
    @abstractmethod
    def cuidados_especiais(self) -> tuple[str, ...]:
        """Cuidados de manuseio próprios da categoria."""

    def exige_sanitizacao(self) -> bool:
        return False

    @property
    def custo_processamento(self) -> Decimal:
        return PARAMETROS_CATEGORIA[self.categoria].custo_processamento

    # ------------------------------------------------------ comportamento comum
    def _validar_atributos(self) -> None:
        faltantes = [nome for nome in self.atributos_obrigatorios if nome not in self.atributos]
        if faltantes:
            raise ValueError(f"{self.categoria}: atributos obrigatórios ausentes: {', '.join(faltantes)}")

    def iniciar_triagem(self) -> None:
        if self.status is not StatusEquipamento.RECEBIDO:
            raise TransicaoInvalidaError(f"{self.codigo_rastreio} não está aguardando triagem")
        self.status = StatusEquipamento.EM_TRIAGEM
        self.etapa_atual = EtapaCiclo.TRIAGEM
        self.versao += 1

    def registrar_destino(self, destino: Destino) -> EtapaCiclo:
        if self.status is not StatusEquipamento.EM_TRIAGEM:
            raise TransicaoInvalidaError(
                f"{self.codigo_rastreio} precisa estar em triagem para receber destino"
            )
        self.destino = destino
        self.status = StatusEquipamento.DESTINADO
        self.etapa_atual = ETAPA_POR_DESTINO[destino]
        self.versao += 1
        return self.etapa_atual

    def para_item_triagem(self) -> ItemTriagem:
        """Template Method: ponte entre o objeto de domínio e o pipeline funcional."""
        return ItemTriagem(
            codigo_rastreio=self.codigo_rastreio,
            categoria=self.categoria,
            estado=self.estado,
            massa_kg=self.peso_kg,
            componentes=tuple(c.para_item() for c in self.componentes),
            parametros=PARAMETROS_CATEGORIA[self.categoria],
        )

    def para_documento(self) -> dict[str, Any]:
        return {
            "codigo_rastreio": self.codigo_rastreio,
            "lote_id": self.lote_id,
            "categoria": self.categoria.value,
            "marca": self.marca,
            "modelo": self.modelo,
            "peso_kg": float(self.peso_kg),
            "estado": self.estado.value,
            "status": self.status.value,
            "etapa_atual": self.etapa_atual.value,
            "destino": self.destino.value if self.destino else None,
            "atributos": dict(self.atributos),
            "componentes": [
                {
                    "tipo": c.tipo,
                    "material_codigo": c.material_codigo,
                    "massa_kg": float(c.massa_kg),
                    "funcional": c.funcional,
                }
                for c in self.componentes
            ],
            "exige_sanitizacao": self.exige_sanitizacao(),
            "versao": self.versao,
            "schema_versao": 1,
            **self.origem,
        }

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.codigo_rastreio}, {self.peso_kg} kg, {self.status})"


class Computador(Equipamento):
    categoria = Categoria.COMPUTADOR
    atributos_obrigatorios = ("processador", "armazenamento_gb")

    def exige_sanitizacao(self) -> bool:
        return True  # mídias podem conter dados pessoais (LGPD)

    def cuidados_especiais(self) -> tuple[str, ...]:
        return ("sanitizar armazenamento antes da desmontagem",)


class DispositivoMovel(Equipamento):
    categoria = Categoria.DISPOSITIVO_MOVEL
    atributos_obrigatorios = ("imei",)

    def exige_sanitizacao(self) -> bool:
        return True

    def cuidados_especiais(self) -> tuple[str, ...]:
        return ("sanitizar memória interna", "remover bateria antes da trituração")


class Eletrodomestico(Equipamento):
    categoria = Categoria.ELETRODOMESTICO
    atributos_obrigatorios = ("voltagem",)

    def cuidados_especiais(self) -> tuple[str, ...]:
        if self.atributos.get("contem_gas_refrigerante"):
            return ("recolher gás refrigerante em equipamento certificado",)
        return ()


class Periferico(Equipamento):
    categoria = Categoria.PERIFERICO

    def cuidados_especiais(self) -> tuple[str, ...]:
        return ("separar cartuchos e toners",) if self.atributos.get("tipo") == "impressora" else ()


class Bateria(Equipamento):
    categoria = Categoria.BATERIA
    atributos_obrigatorios = ("quimica",)

    def cuidados_especiais(self) -> tuple[str, ...]:
        return ("armazenar isolada, com terminais protegidos", "risco de incêndio")


class OutroEquipamento(Equipamento):
    categoria = Categoria.OUTRO

    def cuidados_especiais(self) -> tuple[str, ...]:
        return ()


# -------------------------------------------------------------------- demais
@dataclass(slots=True)
class Cliente:
    id: str
    nome: str
    tipo: str
    documento: str
    pontos_bonificacao: int = 0


@dataclass(slots=True)
class PontoDeColeta:
    id: str
    codigo: str
    nome: str
    latitude: float
    longitude: float
    capacidade_kg: float
    limite_alerta_percentual: float = 80.0
    ocupacao_percentual: float = 0.0
    ocupacao_atualizada_em: datetime | None = None

    @property
    def massa_estimada_kg(self) -> float:
        return round(self.capacidade_kg * self.ocupacao_percentual / 100, 1)

    def necessita_coleta(self) -> bool:
        return self.ocupacao_percentual >= self.limite_alerta_percentual


@dataclass(slots=True)
class Lote:
    id: str
    codigo: str
    cliente_id: str
    ponto_coleta_id: str
    equipamentos: list[str] = field(default_factory=list)
    status: str = "EM_ABERTO"

    def adicionar(self, codigo_rastreio: str) -> None:
        if self.status != "EM_ABERTO":
            raise TransicaoInvalidaError(f"lote {self.codigo} já foi fechado")
        self.equipamentos.append(codigo_rastreio)


@dataclass(slots=True)
class Coleta:
    id: str
    codigo: str
    ponto_coleta_id: str
    responsavel: str
    lotes: list[str] = field(default_factory=list)

    def registrar_lote(self, lote: Lote) -> None:
        self.lotes.append(lote.id)


@dataclass(frozen=True, slots=True)
class EventoTelemetria:
    ponto_id: str
    dispositivo_id: str
    seq: int
    ts: datetime
    tipo: str
    valor: float
    unidade: str

    @property
    def chave_idempotencia(self) -> str:
        return f"{self.dispositivo_id}:{self.seq}"


@dataclass(frozen=True, slots=True)
class EventoRastreabilidade:
    evento_chave: str
    codigo_rastreio: str
    etapa: EtapaCiclo
    tipo: TipoEvento
    ts: datetime
    responsavel: tuple[str, str]  # (matricula, nome)
    hash_anterior: str | None
    hash: str
    dados: tuple[tuple[str, Any], ...] = ()
