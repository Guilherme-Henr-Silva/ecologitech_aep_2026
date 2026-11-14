"""Testes da camada POO/injeção, usando os repositórios em memória como duplos de teste."""

import asyncio
import dataclasses
from decimal import Decimal

import pytest

from ecotrack.config import Configuracao
from ecotrack.container import container_em_memoria
from ecotrack.dados.gerador import gerar, total_documentos
from ecotrack.dominio.entidades import Computador, TransicaoInvalidaError
from ecotrack.dominio.enums import Destino, StatusEquipamento
from ecotrack.dominio.fabrica import FabricaEquipamento
from ecotrack.funcional.parametros import TABELA_MATERIAIS_V3
from ecotrack.persistencia.protocolos import ConflitoDeVersaoError
from ecotrack.servicos.estrategias import PrecificacaoPorMassa
from ecotrack.servicos.rastreabilidade import cadeia_integra

RESPONSAVEL = ("OP-0001", "Teste")
CONFIG = Configuracao(None, "ecotrack", -23.44, -51.92, 2500, 4)
NOTEBOOK = {
    "codigo_rastreio": "EQ-0123456789ABCDEFGHJKMNPQRS",
    "lote_id": "6a6ef9000000000000000001",
    "categoria": "COMPUTADOR",
    "peso_kg": 2.2,
    "estado": "FUNCIONAL",
    "atributos": {"processador": "i5", "armazenamento_gb": 256},
    "componentes": [{"tipo": "placa", "material_codigo": "MAT-PCI", "massa_kg": 0.3}],
}


def test_fabrica_cria_a_subclasse_pela_categoria() -> None:
    equipamento = FabricaEquipamento.criar(NOTEBOOK)
    assert isinstance(equipamento, Computador) and equipamento.exige_sanitizacao()


def test_categoria_sem_atributo_obrigatorio_e_rejeitada() -> None:
    with pytest.raises(ValueError, match="armazenamento_gb"):
        FabricaEquipamento.criar({**NOTEBOOK, "atributos": {"processador": "i5"}})


def test_triagem_completa_registra_cadeia_de_custodia_integra() -> None:
    container = container_em_memoria([], CONFIG)

    async def fluxo() -> None:
        await container.triagem.receber(NOTEBOOK, RESPONSAVEL)
        avaliado = await container.triagem.triar(NOTEBOOK["codigo_rastreio"], RESPONSAVEL)
        historico = await container.rastreabilidade.historico(NOTEBOOK["codigo_rastreio"])
        assert avaliado.destino is Destino.RECONDICIONAR
        assert [f"{e.etapa}/{e.tipo}" for e in historico] == [
            "COLETA/ENTRADA",
            "TRIAGEM/ENTRADA",
            "TRIAGEM/SANITIZACAO",
            "TRIAGEM/SAIDA",
            "RECONDICIONAMENTO/DESTINACAO",
        ]
        assert cadeia_integra(historico)
        adulterado = [
            *historico[:2],
            dataclasses.replace(historico[2], responsavel=("OP-9999", "Outro")),
            *historico[3:],
        ]
        assert not cadeia_integra(adulterado)

    asyncio.run(fluxo())


def test_triagem_repetida_e_bloqueada_pela_maquina_de_estados() -> None:
    container = container_em_memoria([], CONFIG)

    async def fluxo() -> None:
        await container.triagem.receber(NOTEBOOK, RESPONSAVEL)
        await container.triagem.triar(NOTEBOOK["codigo_rastreio"], RESPONSAVEL)
        with pytest.raises(TransicaoInvalidaError):
            await container.triagem.triar(NOTEBOOK["codigo_rastreio"], RESPONSAVEL)

    asyncio.run(fluxo())


def test_concorrencia_otimista_rejeita_gravacao_com_versao_antiga() -> None:
    container = container_em_memoria([], CONFIG)
    repositorio = container.repositorios.equipamentos

    async def fluxo() -> None:
        await repositorio.salvar(FabricaEquipamento.criar(NOTEBOOK))
        copia_a, copia_b = (
            await repositorio.buscar(NOTEBOOK["codigo_rastreio"]),
            await repositorio.buscar(NOTEBOOK["codigo_rastreio"]),
        )
        assert copia_a and copia_b
        copia_a.iniciar_triagem()
        copia_b.iniciar_triagem()
        await repositorio.salvar(copia_a)
        with pytest.raises(ConflitoDeVersaoError):
            await repositorio.salvar(copia_b)
        salvo = await repositorio.buscar(NOTEBOOK["codigo_rastreio"])
        assert salvo and salvo.status is StatusEquipamento.EM_TRIAGEM

    asyncio.run(fluxo())


def test_strategy_troca_a_politica_sem_alterar_o_servico() -> None:
    container = container_em_memoria([], CONFIG)
    equipamento = FabricaEquipamento.criar(NOTEBOOK)
    por_componente = container.precificacao.precificar(equipamento)
    container.precificacao.definir_estrategia(PrecificacaoPorMassa(Decimal("10")))
    assert container.precificacao.precificar(equipamento) == Decimal("22.00") != por_componente


def test_massa_de_teste_tem_mais_de_100_documentos_e_e_reprodutivel() -> None:
    primeira, segunda = gerar(), gerar()
    assert total_documentos(primeira) >= 100
    assert primeira["equipamentos"][0]["codigo_rastreio"] == segunda["equipamentos"][0]["codigo_rastreio"]
    assert all(m["codigo"] in TABELA_MATERIAIS_V3 for m in primeira["materiais"])
