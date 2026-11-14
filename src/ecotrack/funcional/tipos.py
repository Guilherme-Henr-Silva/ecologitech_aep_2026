"""Estruturas imutáveis usadas pelos pipelines funcionais.

Todas as classes são dataclasses congeladas (frozen=True): uma vez criadas, não
podem ser alteradas. Toda transformação do pipeline produz um valor novo.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from ecotrack.dominio.enums import Categoria, Destino, EstadoEquipamento

ZERO = Decimal("0")
CENTAVO = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class MaterialRef:
    """Linha da tabela versionada de materiais (parâmetros p, η e φ da especificação)."""

    codigo: str
    nome: str
    categoria: str
    versao: int
    preco_por_kg: Decimal
    rendimento: float
    fator_co2: float


@dataclass(frozen=True, slots=True)
class ComponenteItem:
    tipo: str
    material_codigo: str
    massa_kg: float
    funcional: bool = False


@dataclass(frozen=True, slots=True)
class ParametrosCategoria:
    """Custos atribuídos por categoria (parâmetro κ e valores de recondicionamento)."""

    custo_processamento: Decimal
    custo_descarte_por_kg: Decimal
    valor_revenda: Decimal | None = None
    custo_recondicionamento: Decimal | None = None

    @property
    def recondicionavel(self) -> bool:
        return self.valor_revenda is not None and self.custo_recondicionamento is not None


@dataclass(frozen=True, slots=True)
class ItemTriagem:
    """Equipamento normalizado, pronto para ser avaliado pelo pipeline."""

    codigo_rastreio: str
    categoria: Categoria
    estado: EstadoEquipamento
    massa_kg: float
    componentes: tuple[ComponenteItem, ...]
    parametros: ParametrosCategoria


@dataclass(frozen=True, slots=True)
class MaterialRecuperado:
    material_codigo: str
    categoria_material: str
    massa_kg: float


@dataclass(frozen=True, slots=True)
class ItemAvaliado:
    codigo_rastreio: str
    categoria: Categoria
    massa_kg: float
    valor_estimado: Decimal
    custo_atribuido: Decimal
    margem: Decimal
    co2_evitado_kg: float
    massa_reciclavel_kg: float
    destino: Destino
    tabela_versao: int
    materiais_recuperados: tuple[MaterialRecuperado, ...] = ()


@dataclass(frozen=True, slots=True)
class Resumo:
    """Elemento do monoide (R, ⊕, ε) usado na agregação de lotes."""

    itens: int = 0
    massa_recebida_kg: float = 0.0
    massa_recuperada_kg: float = 0.0
    valor_total: Decimal = ZERO
    co2_evitado_kg: float = 0.0
    recondicionados: int = 0


TabelaMateriais = Mapping[str, MaterialRef]
TabelaParametros = Mapping[Categoria, ParametrosCategoria]
