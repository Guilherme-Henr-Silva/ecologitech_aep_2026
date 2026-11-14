"""Pipeline 1 – valorização e cálculo de reciclagem (seção 9.4.2 da 1ª entrega).

Regras do módulo:
* todas as funções são puras: dependem só dos argumentos e não fazem E/S;
* nenhuma estrutura recebida é alterada; cada etapa devolve um valor novo;
* a agregação usa a operação monoidal `somar`, por isso pode ser particionada.

    avaliarLote = agregar ∘ map(precificar) ∘ filter(elegível) ∘ map(normalizar)
"""

from collections.abc import Callable, Iterable, Mapping
from decimal import Decimal
from functools import lru_cache, partial, reduce
from typing import Any

from ecotrack.dominio.enums import Categoria, Destino, EstadoEquipamento
from ecotrack.funcional.composicao import compor
from ecotrack.funcional.tipos import (
    CENTAVO,
    ZERO,
    ComponenteItem,
    ItemAvaliado,
    ItemTriagem,
    MaterialRecuperado,
    Resumo,
    TabelaMateriais,
    TabelaParametros,
)

RETORNO_IMPOSSIVEL = Decimal("-Infinity")
RESUMO_VAZIO = Resumo()  # elemento neutro ε


# ---------------------------------------------------------------- normalização
def _normalizar_componente(documento: Mapping[str, Any]) -> ComponenteItem:
    return ComponenteItem(
        tipo=str(documento["tipo"]).strip().lower(),
        material_codigo=str(documento["material_codigo"]).strip().upper(),
        massa_kg=float(documento["massa_kg"]),
        funcional=bool(documento.get("funcional", False)),
    )


def normalizar(documento: Mapping[str, Any], parametros: TabelaParametros) -> ItemTriagem:
    """dict → ItemTriagem: padroniza nomes e unidades do documento vindo do MongoDB."""
    categoria = Categoria(str(documento.get("categoria", "OUTRO")).upper())
    return ItemTriagem(
        codigo_rastreio=str(documento["codigo_rastreio"]),
        categoria=categoria,
        estado=EstadoEquipamento(str(documento.get("estado", "NAO_AVALIADO")).upper()),
        massa_kg=float(documento.get("peso_kg", 0.0)),
        componentes=tuple(map(_normalizar_componente, documento.get("componentes", ()))),
        parametros=parametros[categoria],
    )


def elegivel(tabela: TabelaMateriais) -> Callable[[ItemTriagem], bool]:
    """Predicado: item com massa registrada e todos os materiais presentes no catálogo."""
    return lambda item: item.massa_kg > 0 and all(c.material_codigo in tabela for c in item.componentes)


# ------------------------------------------------------- funções de avaliação
def massa_recuperada(componente: ComponenteItem, tabela: TabelaMateriais) -> float:
    return componente.massa_kg * tabela[componente.material_codigo].rendimento


def valor_componente(componente: ComponenteItem, tabela: TabelaMateriais) -> Decimal:
    massa = Decimal(str(round(massa_recuperada(componente, tabela), 6)))
    return massa * tabela[componente.material_codigo].preco_por_kg


def valor_item(item: ItemTriagem, tabela: TabelaMateriais) -> Decimal:
    """valor(e) = Σ m(e,c) · η(c) · p(c)"""
    parcelas = map(partial(valor_componente, tabela=tabela), item.componentes)
    return sum(parcelas, start=ZERO).quantize(CENTAVO)


def co2_item(item: ItemTriagem, tabela: TabelaMateriais) -> float:
    """co₂(e) = Σ m(e,c) · η(c) · φ(c)"""
    return round(
        sum(massa_recuperada(c, tabela) * tabela[c.material_codigo].fator_co2 for c in item.componentes), 3
    )


def custo_descarte(item: ItemTriagem) -> Decimal:
    massa = Decimal(str(item.massa_kg))
    return (massa * item.parametros.custo_descarte_por_kg).quantize(CENTAVO)


def retorno(item: ItemTriagem, destino: Destino, valor: Decimal) -> Decimal:
    """Retorno esperado de cada destino possível (função total sobre D)."""
    parametros = item.parametros
    if destino is Destino.RECONDICIONAR:
        if item.estado is not EstadoEquipamento.FUNCIONAL or not parametros.recondicionavel:
            return RETORNO_IMPOSSIVEL
        assert parametros.valor_revenda is not None and parametros.custo_recondicionamento is not None
        return parametros.valor_revenda - parametros.custo_recondicionamento
    if destino is Destino.DESMONTAR:
        return valor - parametros.custo_processamento
    return -custo_descarte(item)


def decidir_destino(item: ItemTriagem, valor: Decimal) -> Destino:
    """destino(e) = argmax retorno(e, d), d ∈ D (empate: ordem declarada em Destino)."""
    return max(Destino, key=lambda destino: retorno(item, destino, valor))


def _materiais_recuperados(item: ItemTriagem, tabela: TabelaMateriais) -> tuple[MaterialRecuperado, ...]:
    return tuple(
        MaterialRecuperado(
            c.material_codigo, tabela[c.material_codigo].categoria, round(massa_recuperada(c, tabela), 3)
        )
        for c in item.componentes
    )


def precificar(tabela: TabelaMateriais, versao: int) -> Callable[[ItemTriagem], ItemAvaliado]:
    """Função de alta ordem: recebe a tabela e devolve a função de avaliação daquela versão."""

    @lru_cache(maxsize=8192)  # memoização só é segura porque _avaliar é pura
    def _avaliar(item: ItemTriagem) -> ItemAvaliado:
        valor = valor_item(item, tabela)
        destino = decidir_destino(item, valor)
        recuperados = _materiais_recuperados(item, tabela) if destino is Destino.DESMONTAR else ()
        massa_reciclavel = {
            Destino.RECONDICIONAR: item.massa_kg,
            Destino.DESMONTAR: round(sum(m.massa_kg for m in recuperados), 3),
            Destino.DESCARTAR: 0.0,
        }[destino]
        return ItemAvaliado(
            codigo_rastreio=item.codigo_rastreio,
            categoria=item.categoria,
            massa_kg=item.massa_kg,
            valor_estimado=valor,
            custo_atribuido=item.parametros.custo_processamento,
            margem=retorno(item, destino, valor).quantize(CENTAVO),
            co2_evitado_kg=0.0 if destino is Destino.DESCARTAR else co2_item(item, tabela),
            massa_reciclavel_kg=massa_reciclavel,
            destino=destino,
            tabela_versao=versao,
            materiais_recuperados=recuperados,
        )

    return _avaliar


# ------------------------------------------------------------------ agregação
def para_resumo(avaliado: ItemAvaliado) -> Resumo:
    return Resumo(
        itens=1,
        massa_recebida_kg=avaliado.massa_kg,
        massa_recuperada_kg=avaliado.massa_reciclavel_kg,
        valor_total=avaliado.margem,
        co2_evitado_kg=avaliado.co2_evitado_kg,
        recondicionados=int(avaliado.destino is Destino.RECONDICIONAR),
    )


def somar(a: Resumo, b: Resumo) -> Resumo:
    """Operação ⊕ do monoide comutativo (R, ⊕, ε)."""
    return Resumo(
        itens=a.itens + b.itens,
        massa_recebida_kg=round(a.massa_recebida_kg + b.massa_recebida_kg, 3),
        massa_recuperada_kg=round(a.massa_recuperada_kg + b.massa_recuperada_kg, 3),
        valor_total=a.valor_total + b.valor_total,
        co2_evitado_kg=round(a.co2_evitado_kg + b.co2_evitado_kg, 3),
        recondicionados=a.recondicionados + b.recondicionados,
    )


def agregar(avaliados: Iterable[ItemAvaliado]) -> Resumo:
    return reduce(somar, map(para_resumo, avaliados), RESUMO_VAZIO)


# ------------------------------------------------------------ pipeline final
def montar_avaliacao(
    tabela: TabelaMateriais, versao: int, parametros: TabelaParametros
) -> Callable[[Iterable[Mapping[str, Any]]], tuple[ItemAvaliado, ...]]:
    """Pipeline item a item: documentos brutos → tupla imutável de itens avaliados."""
    return compor(
        partial(map, partial(normalizar, parametros=parametros)),
        partial(filter, elegivel(tabela)),
        partial(map, precificar(tabela, versao)),
        tuple,
    )


def avaliar_lote(
    documentos: Iterable[Mapping[str, Any]],
    tabela: TabelaMateriais,
    versao: int,
    parametros: TabelaParametros,
) -> tuple[tuple[ItemAvaliado, ...], Resumo]:
    """avaliarLote = agregar ∘ map(precificar) ∘ filter(elegível) ∘ map(normalizar)"""
    avaliados = montar_avaliacao(tabela, versao, parametros)(documentos)
    return avaliados, agregar(avaliados)
