"""Linha de comando do EcoTrack.

python -m ecotrack demo                 # fluxo completo em memória (sem banco)
python -m ecotrack demo --mongo         # mesmo fluxo gravando no MongoDB (ECOTRACK_MONGO_URI)
python -m ecotrack relatorios           # executa as Aggregation Pipelines no MongoDB
python -m ecotrack popular              # carrega a massa de teste via aplicação
python -m ecotrack exportar-js          # regera database/02_popular_dados.js
"""

import argparse
import asyncio
import random
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from ecotrack.config import Configuracao
from ecotrack.container import Container, container_em_memoria, container_mongo
from ecotrack.dados.gerador import GeradorIds, gerar
from ecotrack.dominio.entidades import PontoDeColeta
from ecotrack.funcional.bonificacao import ranking
from ecotrack.funcional.parametros import PARAMETROS_CATEGORIA, TABELA_MATERIAIS_V3, VERSAO_TABELA_VIGENTE
from ecotrack.funcional.precificacao import agregar, avaliar_lote, somar
from ecotrack.funcional.tipos import Resumo
from ecotrack.servicos.estrategias import (
    PrecificacaoPorComponente,
    PrecificacaoPorMassa,
    PrecificacaoSpotMercado,
)

RESPONSAVEL_DEMO = ("OP-1021", "Carla Mendes")


def titulo(texto: str) -> None:
    print(f"\n{'=' * 78}\n{texto}\n{'=' * 78}")


def pontos_do_documento(documentos: list[dict[str, Any]]) -> list[PontoDeColeta]:
    return [
        PontoDeColeta(
            id=d["_id"],
            codigo=d["codigo"],
            nome=d["nome"],
            longitude=d["localizacao"]["coordinates"][0],
            latitude=d["localizacao"]["coordinates"][1],
            capacidade_kg=d["capacidade_kg"],
            ocupacao_percentual=d["ocupacao"]["percentual"],
            ocupacao_atualizada_em=d["ocupacao"]["atualizada_em"],
        )
        for d in documentos
    ]


def novos_equipamentos(lote_id: str) -> list[dict[str, Any]]:
    ids = GeradorIds(random.Random())  # códigos novos a cada execução (evita colisão no banco)
    return [
        {
            "codigo_rastreio": ids.codigo_rastreio(),
            "lote_id": lote_id,
            "categoria": "COMPUTADOR",
            "marca": "Dell",
            "modelo": "Latitude 5490",
            "peso_kg": 2.1,
            "estado": "FUNCIONAL",
            "atributos": {"processador": "Intel i5-8350U", "armazenamento_gb": 256},
            "componentes": [
                {"tipo": "placa-mae", "material_codigo": "MAT-PCI", "massa_kg": 0.25},
                {"tipo": "carcaca", "material_codigo": "MAT-AL", "massa_kg": 0.6},
                {"tipo": "bateria", "material_codigo": "MAT-LI", "massa_kg": 0.3},
                {"tipo": "tela", "material_codigo": "MAT-LCD", "massa_kg": 0.45},
            ],
        },
        {
            "codigo_rastreio": ids.codigo_rastreio(),
            "lote_id": lote_id,
            "categoria": "DISPOSITIVO_MOVEL",
            "marca": "Motorola",
            "modelo": "Moto G7",
            "peso_kg": 0.18,
            "estado": "INOPERANTE",
            "atributos": {"imei": "356938035643809"},
            "componentes": [
                {"tipo": "bateria", "material_codigo": "MAT-LI", "massa_kg": 0.05},
                {"tipo": "placa", "material_codigo": "MAT-PCI", "massa_kg": 0.04},
            ],
        },
        {
            "codigo_rastreio": ids.codigo_rastreio(),
            "lote_id": lote_id,
            "categoria": "ELETRODOMESTICO",
            "marca": "Consul",
            "modelo": "CRB36",
            "peso_kg": 48.0,
            "estado": "INOPERANTE",
            "atributos": {"voltagem": 127, "contem_gas_refrigerante": True},
            "componentes": [
                {"tipo": "carcaca", "material_codigo": "MAT-FE", "massa_kg": 27.0},
                {"tipo": "compressor", "material_codigo": "MAT-CP", "massa_kg": 8.0},
                {"tipo": "serpentina", "material_codigo": "MAT-CU", "massa_kg": 2.4},
                {"tipo": "revestimento", "material_codigo": "MAT-PL", "massa_kg": 7.0},
            ],
        },
    ]


async def demonstrar_poo_e_rastreabilidade(container: Container, lote_id: str) -> None:
    titulo("1) POO + injecao de dependencia: recebimento, triagem e cadeia de custodia")
    documentos = novos_equipamentos(lote_id)
    for documento in documentos:
        equipamento = await container.triagem.receber(documento, RESPONSAVEL_DEMO)
        avaliado = await container.triagem.triar(equipamento.codigo_rastreio, RESPONSAVEL_DEMO)
        historico = await container.rastreabilidade.historico(equipamento.codigo_rastreio)
        integra = await container.rastreabilidade.verificar(equipamento.codigo_rastreio)
        print(
            f"{type(equipamento).__name__:<17} {equipamento.codigo_rastreio}  destino={avaliado.destino:<13} "
            f"valor=R$ {avaliado.valor_estimado:>7}  margem=R$ {avaliado.margem:>7}  CO2={avaliado.co2_evitado_kg:>6} kg"
        )
        print(f"{'':<17} cuidados: {', '.join(equipamento.cuidados_especiais()) or '-'}")
        print(
            f"{'':<17} {len(historico)} eventos: {' > '.join(f'{e.etapa}/{e.tipo}' for e in historico)}  | cadeia integra: {integra}"
        )

    titulo("2) Strategy: o mesmo item precificado por tres politicas")
    item = await container.repositorios.equipamentos.buscar(documentos[0]["codigo_rastreio"])
    assert item is not None
    for estrategia in (
        PrecificacaoPorComponente(TABELA_MATERIAIS_V3),
        PrecificacaoPorMassa(Decimal("4.50")),
        PrecificacaoSpotMercado(TABELA_MATERIAIS_V3, {"MAT-PCI": Decimal("1.18"), "MAT-AL": Decimal("0.95")}),
    ):
        container.precificacao.definir_estrategia(estrategia)
        print(f"  {estrategia.nome:<15} -> R$ {container.precificacao.precificar(item)}")


def demonstrar_funcional(dados: dict[str, list[dict[str, Any]]]) -> None:
    titulo(
        "3) Modulo funcional: avaliarLote = agregar . map(precificar) . filter(elegivel) . map(normalizar)"
    )
    lote = dados["lotes"][0]
    documentos = tuple(e for e in dados["equipamentos"] if e["lote_id"] == lote["_id"])
    avaliados, resumo = avaliar_lote(
        documentos, TABELA_MATERIAIS_V3, VERSAO_TABELA_VIGENTE, PARAMETROS_CATEGORIA
    )
    for a in avaliados:
        print(
            f"  {a.codigo_rastreio}  {a.categoria:<18} {a.destino:<13} margem=R$ {a.margem:>8}  CO2={a.co2_evitado_kg:>7}"
        )
    print(f"  Resumo {lote['codigo']}: {resumo}")
    metade = len(avaliados) // 2
    particionado = somar(agregar(avaliados[:metade]), agregar(avaliados[metade:]))
    print(f"  Propriedade monoidal: agregar(L1) (+) agregar(L2) == agregar(L)? {particionado == resumo}")
    print(
        f"  Entrada intacta (imutabilidade)? {documentos == tuple(e for e in dados['equipamentos'] if e['lote_id'] == lote['_id'])}"
    )

    titulo("4) Bonificacao de clientes (pipeline funcional sobre os lotes concluidos)")

    def resumo_do_lote(lote_concluido: dict[str, Any]) -> Resumo:
        itens = (e for e in dados["equipamentos"] if e["lote_id"] == lote_concluido["_id"])
        return avaliar_lote(itens, TABELA_MATERIAIS_V3, VERSAO_TABELA_VIGENTE, PARAMETROS_CATEGORIA)[1]

    concluidos = (lote for lote in dados["lotes"] if lote["status"] == "CONCLUIDO")
    pares = tuple((lote["cliente"]["nome"], resumo_do_lote(lote)) for lote in concluidos)
    for b in ranking(pares):
        print(f"  {b.cliente_id:<46} {b.pontos:>6} pts  {b.faixa:<8} desconto {b.desconto:.0%}")


async def demonstrar_concorrencia(container: Container, pontos: list[PontoDeColeta], leituras: int) -> None:
    titulo(f"5) Modulo concorrente: {len(pontos)} pontos enviando ao mesmo tempo ({leituras} leituras cada)")
    estatisticas = await container.ingestao.executar_simulacao(
        pontos, leituras, inicio=datetime(2026, 11, 13, 8, 0, tzinfo=UTC)
    )
    print(f"  produtores={estatisticas.pontos}  consumidores={estatisticas.consumidores}")
    print(
        f"  leituras unicas emitidas={estatisticas.leituras_unicas_emitidas}  reenvios (duplicatas)={estatisticas.reenvios_emitidos}"
    )
    print(
        f"  persistidas={estatisticas.persistidas}  duplicatas descartadas={estatisticas.duplicadas_descartadas}"
    )
    print(
        f"  sem perda e sem duplicidade? {estatisticas.sem_perda_nem_duplicidade}   "
        f"tempo={estatisticas.duracao_s}s  vazao={estatisticas.vazao_por_segundo} msg/s"
    )
    print(f"  alertas de coleta (>= 80%): {len(container.alertas.alertas)} pontos")
    rota = await container.roteirizacao.sugerir(limite_percentual=70.0)
    print(
        f"  rota sugerida: {len(rota.paradas)} paradas, {rota.distancia_total_km} km, {rota.massa_prevista_kg} kg previstos"
    )
    for ordem, parada in enumerate(rota.paradas, start=1):
        print(f"    {ordem}. {parada.nome:<32} ocupacao {parada.ocupacao_percentual:>5}%")


async def comando_demo(usar_mongo: bool, leituras: int) -> None:
    dados = gerar()
    configuracao = Configuracao.do_ambiente()
    pontos = pontos_do_documento(dados["pontos_coleta"])
    container = container_mongo(configuracao) if usar_mongo else container_em_memoria(pontos, configuracao)
    if usar_mongo:
        pontos = list(await container.repositorios.pontos.listar())
    try:
        await demonstrar_poo_e_rastreabilidade(container, dados["lotes"][-1]["_id"])
        demonstrar_funcional(dados)
        await demonstrar_concorrencia(container, pontos, leituras)
    finally:
        await container.fechar()


async def comando_relatorios() -> None:
    container = container_mongo(Configuracao.do_ambiente())
    relatorios = container.relatorios
    assert relatorios is not None
    try:
        consultas = {
            "A1 - CO2 evitado por cliente": relatorios.co2_por_cliente(
                datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 12, 1, tzinfo=UTC)
            ),
            "A2 - Material reciclado por categoria (out/2026)": relatorios.material_reciclado_no_mes(
                datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)
            ),
            "A3 - Tempo medio de processamento por ponto": relatorios.tempo_medio_por_ponto(),
            "A4 - Ocupacao nas ultimas 24 h": relatorios.ocupacao_ultimas_24h(
                datetime(2026, 11, 13, tzinfo=UTC)
            ),
            "A5 - Destinacao por categoria": relatorios.destinacao_por_categoria(),
            "A6 - Pontos para a rota": relatorios.pontos_para_rota(
                container.configuracao.deposito_lon, container.configuracao.deposito_lat
            ),
        }
        for nome, corrotina in consultas.items():
            titulo(nome)
            for linha in await corrotina:
                print(" ", linha)
        titulo("Ranking de bonificacao (banco agrega + pipeline funcional pontua)")
        for b in await relatorios.ranking_bonificacao():
            print(f"  {b.cliente_id:<46} {b.pontos:>6} pts  {b.faixa}")
    finally:
        await container.fechar()


async def comando_popular() -> None:
    from pymongo import AsyncMongoClient

    from ecotrack.persistencia.conversores import para_bson

    configuracao = Configuracao.do_ambiente()
    cliente: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(configuracao.mongo_uri)
    banco = cliente[configuracao.banco]
    try:
        for colecao, documentos in gerar().items():
            await banco[colecao].delete_many({})
            await banco[colecao].insert_many([para_bson(d) for d in documentos])
            print(f"  {colecao:<26} {len(documentos):>4} documentos")
    finally:
        await cliente.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="ecotrack", description="EcoTrack MVP - EcoLogitech")
    sub = parser.add_subparsers(dest="comando", required=True)
    demo = sub.add_parser("demo", help="demonstra os tres paradigmas")
    demo.add_argument("--mongo", action="store_true", help="usa o MongoDB de ECOTRACK_MONGO_URI")
    demo.add_argument("--leituras", type=int, default=250, help="leituras por ponto na simulacao")
    sub.add_parser("relatorios", help="executa as Aggregation Pipelines")
    sub.add_parser("popular", help="carrega a massa de teste pelo driver")
    exportar = sub.add_parser("exportar-js", help="regera database/02_popular_dados.js")
    exportar.add_argument("--destino", type=Path, default=Path("database/02_popular_dados.js"))
    argumentos = parser.parse_args()

    if argumentos.comando == "demo":
        asyncio.run(comando_demo(argumentos.mongo, argumentos.leituras))
    elif argumentos.comando == "relatorios":
        asyncio.run(comando_relatorios())
    elif argumentos.comando == "popular":
        asyncio.run(comando_popular())
    else:
        from ecotrack.dados.exportador_js import exportar as exportar_js

        print(f"gerado: {exportar_js(argumentos.destino)}")


if __name__ == "__main__":
    main()
