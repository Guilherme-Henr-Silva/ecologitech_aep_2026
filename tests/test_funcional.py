"""Testes do módulo funcional: exemplos e propriedades (monoide, pureza, monotonicidade)."""

import random
from decimal import Decimal

import pytest

from ecotrack.dominio.enums import Categoria, Destino, EstadoEquipamento, FaixaBonus
from ecotrack.funcional.bonificacao import faixa, pontos
from ecotrack.funcional.composicao import compor
from ecotrack.funcional.parametros import PARAMETROS_CATEGORIA, TABELA_MATERIAIS_V3, VERSAO_TABELA_VIGENTE
from ecotrack.funcional.precificacao import (
    RESUMO_VAZIO,
    agregar,
    avaliar_lote,
    decidir_destino,
    precificar,
    somar,
    valor_item,
)
from ecotrack.funcional.rotas import PontoRota, sugerir_rota
from ecotrack.funcional.tipos import ComponenteItem, ItemTriagem, Resumo

CASOS_ALEATORIOS = 200


def item(
    categoria: Categoria = Categoria.COMPUTADOR,
    estado: EstadoEquipamento = EstadoEquipamento.INOPERANTE,
    componentes: tuple[ComponenteItem, ...] = (
        ComponenteItem("placa", "MAT-PCI", 0.5),
        ComponenteItem("gabinete", "MAT-FE", 3.0),
    ),
) -> ItemTriagem:
    return ItemTriagem(
        "EQ-TESTE",
        categoria,
        estado,
        sum(c.massa_kg for c in componentes),
        componentes,
        PARAMETROS_CATEGORIA[categoria],
    )


def item_aleatorio(gerador: random.Random) -> ItemTriagem:
    materiais = list(TABELA_MATERIAIS_V3)
    componentes = tuple(
        ComponenteItem("parte", gerador.choice(materiais), round(gerador.uniform(0.01, 20), 3))
        for _ in range(gerador.randint(1, 5))
    )
    return ItemTriagem(
        f"EQ-{gerador.randint(0, 10**6)}",
        gerador.choice(list(Categoria)),
        gerador.choice(list(EstadoEquipamento)),
        round(sum(c.massa_kg for c in componentes), 3),
        componentes,
        PARAMETROS_CATEGORIA[Categoria.OUTRO],
    )


def resumo_aleatorio(gerador: random.Random) -> Resumo:
    return Resumo(
        gerador.randint(0, 9),
        round(gerador.uniform(0, 99), 3),
        round(gerador.uniform(0, 99), 3),
        Decimal(str(round(gerador.uniform(-50, 500), 2))),
        round(gerador.uniform(0, 99), 3),
        gerador.randint(0, 3),
    )


def test_valor_item_soma_contribuicao_de_cada_material() -> None:
    # 0,5 kg × 0,85 × R$ 45,00 + 3,0 kg × 0,95 × R$ 0,90 = 19,125 + 2,565
    assert valor_item(item(), TABELA_MATERIAIS_V3) == Decimal("21.69")


def test_item_funcional_e_recondicionavel_vai_para_recondicionamento() -> None:
    funcional = item(estado=EstadoEquipamento.FUNCIONAL)
    assert decidir_destino(funcional, valor_item(funcional, TABELA_MATERIAIS_V3)) is Destino.RECONDICIONAR


def test_bateria_nunca_e_recondicionada() -> None:
    bateria = item(
        Categoria.BATERIA, EstadoEquipamento.FUNCIONAL, (ComponenteItem("celulas", "MAT-LI", 5.0),)
    )
    assert decidir_destino(bateria, valor_item(bateria, TABELA_MATERIAIS_V3)) is not Destino.RECONDICIONAR


def test_precificar_e_deterministica_mesma_tabela_mesmo_resultado() -> None:
    gerador = random.Random(1)
    avaliar = precificar(TABELA_MATERIAIS_V3, VERSAO_TABELA_VIGENTE)
    for _ in range(CASOS_ALEATORIOS):
        candidato = item_aleatorio(gerador)
        assert avaliar(candidato) == precificar(TABELA_MATERIAIS_V3, VERSAO_TABELA_VIGENTE)(candidato)


def test_propriedade_monoide_associatividade_comutatividade_e_neutro() -> None:
    gerador = random.Random(2)
    for _ in range(CASOS_ALEATORIOS):
        a, b, c = (resumo_aleatorio(gerador) for _ in range(3))
        assert somar(a, RESUMO_VAZIO) == a
        assert somar(a, b) == somar(b, a)
        assert somar(somar(a, b), c).valor_total == somar(a, somar(b, c)).valor_total
        assert somar(somar(a, b), c).itens == somar(a, somar(b, c)).itens


def test_agregacao_particionada_igual_a_agregacao_total() -> None:
    gerador = random.Random(3)
    avaliar = precificar(TABELA_MATERIAIS_V3, VERSAO_TABELA_VIGENTE)
    avaliados = tuple(avaliar(item_aleatorio(gerador)) for _ in range(60))
    corte = gerador.randint(1, 59)
    total, partes = agregar(avaliados), somar(agregar(avaliados[:corte]), agregar(avaliados[corte:]))
    assert (total.itens, total.valor_total, total.recondicionados) == (
        partes.itens,
        partes.valor_total,
        partes.recondicionados,
    )
    assert total.co2_evitado_kg == pytest.approx(partes.co2_evitado_kg)


def test_pipeline_nao_altera_os_documentos_de_entrada() -> None:
    documentos = [
        {
            "codigo_rastreio": "EQ-1",
            "categoria": "periferico",
            "estado": "parcial",
            "peso_kg": 2.0,
            "componentes": [{"tipo": "Carcaca ", "material_codigo": "mat-pl", "massa_kg": 2.0}],
        }
    ]
    copia = [dict(d, componentes=[dict(c) for c in d["componentes"]]) for d in documentos]
    avaliados, resumo = avaliar_lote(
        documentos, TABELA_MATERIAIS_V3, VERSAO_TABELA_VIGENTE, PARAMETROS_CATEGORIA
    )
    assert documentos == copia
    assert resumo.itens == 1 and avaliados[0].categoria is Categoria.PERIFERICO


def test_itens_sem_massa_ou_fora_do_catalogo_sao_filtrados() -> None:
    documentos = [
        {"codigo_rastreio": "EQ-1", "categoria": "OUTRO", "peso_kg": 0, "componentes": []},
        {
            "codigo_rastreio": "EQ-2",
            "categoria": "OUTRO",
            "peso_kg": 1.0,
            "componentes": [{"tipo": "x", "material_codigo": "MAT-XX", "massa_kg": 1.0}],
        },
    ]
    avaliados, resumo = avaliar_lote(
        documentos, TABELA_MATERIAIS_V3, VERSAO_TABELA_VIGENTE, PARAMETROS_CATEGORIA
    )
    assert avaliados == () and resumo == RESUMO_VAZIO


def test_pontos_sao_monotonicos_e_nunca_negativos() -> None:
    gerador = random.Random(4)
    for _ in range(CASOS_ALEATORIOS):
        lotes = [resumo_aleatorio(gerador) for _ in range(gerador.randint(0, 6))]
        acrescimo = resumo_aleatorio(gerador)
        assert pontos(lotes) >= 0
        assert pontos([*lotes, acrescimo]) >= pontos(lotes)


@pytest.mark.parametrize(
    ("total", "esperada"),
    [
        (0, FaixaBonus.BRONZE),
        (500, FaixaBonus.PRATA),
        (1499, FaixaBonus.PRATA),
        (1500, FaixaBonus.OURO),
        (3000, FaixaBonus.PLATINA),
    ],
)
def test_faixas_de_bonus_nos_limites(total: int, esperada: FaixaBonus) -> None:
    assert faixa(total) is esperada


def test_compor_aplica_da_esquerda_para_a_direita() -> None:
    assert compor(lambda x: x + 1, lambda x: x * 10)(2) == 30


def test_rota_respeita_limite_de_ocupacao_e_capacidade_do_veiculo() -> None:
    pontos_rota = (
        PontoRota("a", "A", -23.42, -51.93, 95.0, 600),
        PontoRota("b", "B", -23.40, -51.94, 85.0, 600),
        PontoRota("c", "C", -23.43, -51.92, 40.0, 100),
        PontoRota("d", "D", -23.39, -51.95, 90.0, 600),
    )
    rota = sugerir_rota((-23.44, -51.92), pontos_rota, limite_percentual=70, capacidade_veiculo_kg=1300)
    assert {p.ponto_id for p in rota.paradas} <= {"a", "b", "d"}
    assert rota.massa_prevista_kg <= 1300 and len(rota.paradas) == 2
