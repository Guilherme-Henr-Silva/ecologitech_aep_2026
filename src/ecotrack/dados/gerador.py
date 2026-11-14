"""Gerador determinístico da massa de dados de demonstração do MVP.

A mesma semente produz sempre os mesmos documentos. Os valores de triagem e o
resumo dos lotes são calculados pelo próprio pipeline funcional, e os eventos
são encadeados pela mesma função de hash do serviço de rastreabilidade, então a
massa de teste é coerente com as regras do sistema.
"""

import hashlib
import random
from collections.abc import Iterator
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

from ecotrack.dominio.enums import ETAPA_POR_DESTINO, Categoria, EtapaCiclo, TipoEvento
from ecotrack.funcional.parametros import PARAMETROS_CATEGORIA, TABELA_MATERIAIS_V3, VERSAO_TABELA_VIGENTE
from ecotrack.funcional.precificacao import agregar, normalizar, precificar
from ecotrack.servicos.rastreabilidade import calcular_hash

Documento = dict[str, Any]
SEMENTE = 2026
ALFABETO_ULID = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
INICIO_OPERACAO = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
FIM_TELEMETRIA = datetime(2026, 11, 13, 0, 0, tzinfo=UTC)
LOTES = 24
ITENS_POR_LOTE = 6

CLIENTES = (
    ("CORPORATIVO", "Metalurgica Vale Verde Ltda", "11.222.333/0001-01"),
    ("CORPORATIVO", "Hospital Santa Clara de Maringa", "22.333.444/0001-02"),
    ("CORPORATIVO", "Cooperativa Agroindustrial Norte PR", "33.444.555/0001-03"),
    ("CORPORATIVO", "Escritorio Contabil Alfa", "44.555.666/0001-04"),
    ("CORPORATIVO", "Rede Supermercados Bom Preco", "55.666.777/0001-05"),
    ("ORGAO_PUBLICO", "Secretaria Municipal de Educacao (ficticia)", "66.777.888/0001-06"),
    ("CORPORATIVO", "Universidade Exemplo - Campus Centro", "77.888.999/0001-07"),
    ("PROGRAMA_RESIDENCIAL", "Programa Descarte Consciente - consumidores", "88.999.000/0001-08"),
)

PONTOS = (  # (nome, tipo, lat, lon, capacidade_kg)
    ("Shopping Avenida Centro", "VAREJO", -23.4205, -51.9331, 800.0),
    ("Condominio Parque das Flores", "CONDOMINIO", -23.4031, -51.9478, 400.0),
    ("Paco Municipal", "ORGAO_PUBLICO", -23.4253, -51.9386, 600.0),
    ("Hipermercado Zona Norte", "VAREJO", -23.3897, -51.9302, 1000.0),
    ("Campus Universitario", "INSTITUICAO_ENSINO", -23.4089, -51.9395, 700.0),
    ("Hospital Santa Clara", "EMPRESA", -23.4312, -51.9262, 500.0),
    ("Condominio Jardim Alvorada", "CONDOMINIO", -23.4421, -51.9518, 300.0),
    ("Loja de Eletronicos Centro", "VAREJO", -23.4227, -51.9289, 350.0),
    ("Parque Industrial Sul", "EMPRESA", -23.4588, -51.9167, 1500.0),
    ("Terminal Rodoviario", "ORGAO_PUBLICO", -23.4146, -51.9410, 450.0),
    ("Supermercado Vila Operaria", "VAREJO", -23.4335, -51.9461, 500.0),
    ("Cooperativa Norte PR", "EMPRESA", -23.3804, -51.9586, 1200.0),
)

# categoria → (faixa de peso, modelos possíveis, componentes [(tipo, material, fração da massa)])
CATALOGO: dict[
    Categoria, tuple[tuple[float, float], tuple[tuple[str, str], ...], tuple[tuple[str, str, float], ...]]
] = {
    Categoria.COMPUTADOR: (
        (2.0, 9.5),
        (
            ("Dell", "Optiplex 3080"),
            ("Lenovo", "ThinkPad T480"),
            ("HP", "ProDesk 400"),
            ("Positivo", "Master D580"),
        ),
        (
            ("placa-mae", "MAT-PCI", 0.12),
            ("gabinete", "MAT-FE", 0.45),
            ("carcaca", "MAT-PL", 0.18),
            ("dissipador", "MAT-AL", 0.08),
            ("cabos", "MAT-CB", 0.05),
        ),
    ),
    Categoria.DISPOSITIVO_MOVEL: (
        (0.15, 0.7),
        (
            ("Samsung", "Galaxy A32"),
            ("Motorola", "Moto G60"),
            ("Apple", "iPhone 8"),
            ("Xiaomi", "Redmi Note 10"),
        ),
        (
            ("bateria", "MAT-LI", 0.28),
            ("placa", "MAT-PCI", 0.22),
            ("tela", "MAT-LCD", 0.25),
            ("carcaca", "MAT-PL", 0.15),
            ("chassi", "MAT-AL", 0.10),
        ),
    ),
    Categoria.ELETRODOMESTICO: (
        (12.0, 58.0),
        (("Consul", "CRB36"), ("Electrolux", "ME41"), ("Brastemp", "BWK11"), ("Panasonic", "NN-ST27")),
        (
            ("carcaca", "MAT-FE", 0.55),
            ("compressor", "MAT-CP", 0.15),
            ("revestimento", "MAT-PL", 0.15),
            ("serpentina", "MAT-CU", 0.05),
            ("porta", "MAT-VD", 0.05),
        ),
    ),
    Categoria.PERIFERICO: (
        (0.6, 8.0),
        (("HP", "DeskJet 2774"), ("LG", "Monitor 24MK430"), ("Epson", "L3150"), ("Logitech", "K120")),
        (
            ("placa", "MAT-PCI", 0.08),
            ("carcaca", "MAT-PL", 0.55),
            ("estrutura", "MAT-FE", 0.20),
            ("cabos", "MAT-CB", 0.07),
        ),
    ),
    Categoria.BATERIA: (
        (1.5, 12.0),
        (("SMS", "Nobreak 1200VA"), ("Moura", "12V 7Ah"), ("Intelbras", "XB 1200")),
        (("celulas", "MAT-LI", 0.70), ("invólucro", "MAT-PL", 0.15), ("estrutura", "MAT-FE", 0.10)),
    ),
}

RESPONSAVEIS = (
    ("OP-1021", "Carla Mendes"),
    ("OP-1034", "Joao Batista"),
    ("OP-1047", "Luana Prado"),
    ("OP-1052", "Marcos Teixeira"),
)


class GeradorIds:
    """ObjectIds determinísticos (24 hexadecimais) e códigos no formato ULID."""

    def __init__(self, gerador: random.Random) -> None:
        self._gerador = gerador
        self._contador = 0

    def object_id(self, instante: datetime) -> str:
        self._contador += 1
        return f"{int(instante.timestamp()):08x}{self._gerador.getrandbits(40):010x}{self._contador:06x}"

    def codigo_rastreio(self) -> str:
        return "EQ-" + "".join(self._gerador.choice(ALFABETO_ULID) for _ in range(26))


def _atributos(categoria: Categoria, gerador: random.Random) -> dict[str, Any]:
    if categoria is Categoria.COMPUTADOR:
        return {
            "processador": gerador.choice(("Intel i5-8500", "Intel i3-10100", "AMD Ryzen 5 3400G")),
            "memoria_gb": gerador.choice((4, 8, 16)),
            "armazenamento_gb": gerador.choice((240, 500, 1000)),
            "possui_armazenamento": True,
        }
    if categoria is Categoria.DISPOSITIVO_MOVEL:
        return {
            "imei": "".join(gerador.choice("0123456789") for _ in range(15)),
            "ciclos_bateria": gerador.randint(150, 900),
        }
    if categoria is Categoria.ELETRODOMESTICO:
        return {"voltagem": gerador.choice((127, 220)), "contem_gas_refrigerante": gerador.random() < 0.5}
    if categoria is Categoria.PERIFERICO:
        return {
            "tipo": gerador.choice(("impressora", "monitor", "teclado")),
            "conexao": gerador.choice(("USB", "HDMI", "Wi-Fi")),
        }
    return {"quimica": gerador.choice(("chumbo-acido", "ion-litio")), "tensao_v": 12}


def _estado(gerador: random.Random) -> str:
    return gerador.choices(("FUNCIONAL", "PARCIAL", "INOPERANTE"), weights=(35, 30, 35))[0]


def _datas_uteis(gerador: random.Random) -> Iterator[datetime]:
    """Datas de coleta espalhadas entre setembro e o início de novembro de 2026."""
    for indice in range(LOTES):
        dia = INICIO_OPERACAO + timedelta(
            days=round(indice * 70 / LOTES) + gerador.randint(0, 1), hours=gerador.randint(0, 8)
        )
        yield dia.replace(minute=0, second=0, microsecond=0)


def gerar() -> dict[str, list[Documento]]:
    gerador = random.Random(SEMENTE)
    ids = GeradorIds(gerador)
    criado_em = INICIO_OPERACAO - timedelta(days=30)

    materiais = [
        {
            "_id": ids.object_id(criado_em),
            "codigo": m.codigo,
            "versao": m.versao,
            "nome": m.nome,
            "categoria": m.categoria,
            "vigencia_inicio": datetime(2026, 8, 1, tzinfo=UTC),
            "vigencia_fim": None,
            "preco_por_kg": m.preco_por_kg,
            "rendimento_recuperacao": m.rendimento,
            "fator_co2_evitado": m.fator_co2,
            "fonte": "Tabela comercial EcoLogitech v3 (ficticia)",
        }
        for m in TABELA_MATERIAIS_V3.values()
    ]
    clientes = [
        {
            "_id": ids.object_id(criado_em),
            "tipo": tipo,
            "nome": nome,
            "documento": documento,
            "contatos": [{"tipo": "email", "valor": f"sustentabilidade{i}@cliente-exemplo.com.br"}],
            "enderecos": [{"cidade": "Maringa", "uf": "PR"}],
            "status": "ATIVO",
            "criado_em": criado_em,
        }
        for i, (tipo, nome, documento) in enumerate(CLIENTES, start=1)
    ]
    pontos = [
        {
            "_id": ids.object_id(criado_em),
            "codigo": f"PC-{i:03d}",
            "nome": nome,
            "tipo": tipo,
            "cliente_id": clientes[i % len(clientes)]["_id"] if tipo == "EMPRESA" else None,
            "endereco": {"cidade": "Maringa", "uf": "PR"},
            "localizacao": {"type": "Point", "coordinates": [lon, lat]},
            "capacidade_kg": capacidade,
            "limite_alerta_percentual": 80.0,
            "ocupacao": {},
            "dispositivo": {"id": f"IOT-PC-{i:03d}", "modelo": "EcoSense v2", "firmware": "2.4.1"},
            "status": "ATIVO",
            "criado_em": criado_em,
        }
        for i, (nome, tipo, lat, lon, capacidade) in enumerate(PONTOS, start=1)
    ]

    avaliar = precificar(TABELA_MATERIAIS_V3, VERSAO_TABELA_VIGENTE)
    coletas: list[Documento] = []
    lotes: list[Documento] = []
    equipamentos: list[Documento] = []
    triagens: list[Documento] = []
    eventos: list[Documento] = []

    for numero, data_coleta in enumerate(_datas_uteis(gerador), start=1):
        ponto = pontos[(numero * 5) % len(pontos)]
        cliente = clientes[numero % len(clientes)]
        responsavel = gerador.choice(RESPONSAVEIS)
        coleta: Documento = {
            "_id": ids.object_id(data_coleta),
            "codigo": f"COL-2026-{numero:04d}",
            "ponto_coleta": {"_id": ponto["_id"], "codigo": ponto["codigo"], "nome": ponto["nome"]},
            "rota": {
                "codigo": f"ROTA-{data_coleta:%m%d}",
                "ordem_parada": gerador.randint(1, 5),
                "veiculo_placa": "ECO-2026",
                "motorista": "Equipe de campo",
            },
            "status": "REALIZADA",
            "agendada_para": data_coleta - timedelta(hours=2),
            "realizada_em": data_coleta,
            "responsavel": {"matricula": responsavel[0], "nome": responsavel[1]},
            "ocupacao_no_momento_percentual": round(gerador.uniform(62, 97), 1),
            "massa_total_kg": 0.0,
            "quantidade_lotes": 1,
        }
        lote: Documento = {
            "_id": ids.object_id(data_coleta),
            "codigo": f"LT-2026-{numero:04d}",
            "coleta_id": coleta["_id"],
            "cliente": {"_id": cliente["_id"], "nome": cliente["nome"], "tipo": cliente["tipo"]},
            "cliente_id": cliente["_id"],
            "ponto_coleta_id": ponto["_id"],
            "status": "EM_ABERTO",
            "aberto_em": data_coleta,
            "concluido_em": None,
        }
        aberto = numero > LOTES - 2  # os dois lotes mais recentes ainda estão em triagem
        avaliados = []
        for _ in range(ITENS_POR_LOTE):
            categoria = gerador.choices(tuple(CATALOGO), weights=(30, 30, 12, 18, 10))[0]
            (peso_min, peso_max), modelos, composicao = CATALOGO[categoria]
            peso = round(gerador.uniform(peso_min, peso_max), 2)
            marca, modelo = gerador.choice(modelos)
            documento = {
                "_id": ids.object_id(data_coleta),
                "codigo_rastreio": ids.codigo_rastreio(),
                "lote_id": lote["_id"],
                "coleta_id": coleta["_id"],
                "cliente_id": cliente["_id"],
                "ponto_coleta_id": ponto["_id"],
                "categoria": categoria.value,
                "marca": marca,
                "modelo": modelo,
                "descricao": f"{marca} {modelo} recebido em {ponto['nome']}",
                "peso_kg": peso,
                "estado": _estado(gerador),
                "atributos": _atributos(categoria, gerador),
                "componentes": [
                    {
                        "tipo": tipo,
                        "material_codigo": material,
                        "massa_kg": round(peso * fracao, 3),
                        "funcional": gerador.random() < 0.3,
                    }
                    for tipo, material, fracao in composicao
                ],
                "exige_sanitizacao": categoria in (Categoria.COMPUTADOR, Categoria.DISPOSITIVO_MOVEL),
                "recebido_em": data_coleta + timedelta(hours=3),
                "schema_versao": 1,
            }
            avaliado = avaliar(normalizar(documento, PARAMETROS_CATEGORIA))
            em_triagem = aberto and gerador.random() < 0.5
            _concluir_documentos(
                documento,
                avaliado,
                em_triagem,
                responsavel,
                gerador,
                ids,
                triagens,
                eventos,
                lote,
                ponto,
                cliente,
            )
            equipamentos.append(documento)
            if not em_triagem:
                avaliados.append(avaliado)
        resumo = agregar(avaliados)
        coleta["massa_total_kg"] = round(sum(e["peso_kg"] for e in equipamentos[-ITENS_POR_LOTE:]), 2)
        lote["resumo"] = {
            "quantidade_itens": ITENS_POR_LOTE,
            "massa_recebida_kg": coleta["massa_total_kg"],
            "massa_recuperada_kg": resumo.massa_recuperada_kg,
            "valor_total": resumo.valor_total,
            "co2_evitado_kg": resumo.co2_evitado_kg,
            "atualizado_em": data_coleta + timedelta(days=3),
        }
        if len(avaliados) == ITENS_POR_LOTE:
            lote["status"] = "CONCLUIDO"
            lote["concluido_em"] = max(t["concluida_em"] for t in triagens[-ITENS_POR_LOTE:])
            lote["certificado"] = {
                "numero": f"CERT-2026-{numero:04d}",
                "emitido_em": lote["concluido_em"] + timedelta(hours=4),
                "hash_sha256": hashlib.sha256(lote["codigo"].encode()).hexdigest(),
            }
        coletas.append(coleta)
        lotes.append(lote)

    return {
        "materiais": materiais,
        "clientes": clientes,
        "pontos_coleta": pontos,
        "coletas": coletas,
        "lotes": lotes,
        "equipamentos": equipamentos,
        "triagens": triagens,
        "eventos_rastreabilidade": eventos,
        "leituras_telemetria": _telemetria(pontos, gerador),
    }


def _concluir_documentos(
    documento: Documento,
    avaliado: Any,
    em_triagem: bool,
    responsavel: tuple[str, str],
    gerador: random.Random,
    ids: GeradorIds,
    triagens: list[Documento],
    eventos: list[Documento],
    lote: Documento,
    ponto: Documento,
    cliente: Documento,
) -> None:
    recebido = documento["recebido_em"]
    iniciada = recebido + timedelta(hours=gerador.randint(4, 70))
    concluida = iniciada + timedelta(minutes=gerador.randint(25, 240))
    passos = [
        (EtapaCiclo.COLETA, TipoEvento.ENTRADA, recebido, {"peso_kg": documento["peso_kg"]}),
        (EtapaCiclo.TRIAGEM, TipoEvento.ENTRADA, iniciada, {}),
    ]
    if documento["exige_sanitizacao"]:
        passos.append(
            (
                EtapaCiclo.TRIAGEM,
                TipoEvento.SANITIZACAO,
                iniciada + timedelta(minutes=15),
                {"metodo": "NIST 800-88 purge"},
            )
        )
    if not em_triagem:
        passos.append((EtapaCiclo.TRIAGEM, TipoEvento.SAIDA, concluida, {"destino": avaliado.destino.value}))
        passos.append(
            (ETAPA_POR_DESTINO[avaliado.destino], TipoEvento.DESTINACAO, concluida + timedelta(hours=6), {})
        )

    hash_anterior = None
    for etapa, tipo, ts, dados in passos:
        hash_atual = calcular_hash(
            documento["codigo_rastreio"], etapa, tipo, ts, responsavel[0], hash_anterior
        )
        eventos.append(
            {
                "_id": ids.object_id(ts),
                "evento_chave": f"{etapa.value}:{tipo.value}",
                "equipamento_id": documento["_id"],
                "lote_id": lote["_id"],
                "codigo_rastreio": documento["codigo_rastreio"],
                "etapa": etapa.value,
                "tipo": tipo.value,
                "ts": ts,
                "responsavel": {"matricula": responsavel[0], "nome": responsavel[1]},
                "local": {
                    "tipo": "PONTO_COLETA" if etapa is EtapaCiclo.COLETA else "PLANTA",
                    "referencia": ponto["codigo"] if etapa is EtapaCiclo.COLETA else "PLANTA-MGA-01",
                },
                "dados": dados,
                "hash_anterior": hash_anterior,
                "hash": hash_atual,
            }
        )
        hash_anterior = hash_atual

    documento["ultimo_evento_hash"] = hash_anterior
    if em_triagem:
        documento.update(status="EM_TRIAGEM", etapa_atual="TRIAGEM", destino=None, versao=2)
        return
    documento.update(
        status="DESTINADO",
        etapa_atual=ETAPA_POR_DESTINO[avaliado.destino].value,
        destino=avaliado.destino.value,
        versao=3,
    )
    triagens.append(
        {
            "_id": ids.object_id(concluida),
            "equipamento_id": documento["_id"],
            "codigo_rastreio": documento["codigo_rastreio"],
            "categoria_equipamento": documento["categoria"],
            "peso_kg": documento["peso_kg"],
            "lote_id": lote["_id"],
            "cliente_id": cliente["_id"],
            "ponto_coleta_id": ponto["_id"],
            "coletado_em": recebido,
            "responsavel": {"matricula": responsavel[0], "nome": responsavel[1]},
            "bancada": f"B-{gerador.randint(1, 4)}",
            "status": "CONCLUIDA",
            "iniciada_em": iniciada,
            "concluida_em": concluida,
            "diagnostico": {
                "liga": documento["estado"] == "FUNCIONAL",
                "observacao": "avaliacao visual e eletrica",
            },
            "sanitizacao": {
                "exigida": documento["exige_sanitizacao"],
                "metodo": "NIST 800-88 purge" if documento["exige_sanitizacao"] else None,
            },
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
    )


def _telemetria(pontos: list[Documento], gerador: random.Random) -> list[Documento]:
    """Últimas 24 h: ocupação a cada hora e temperatura a cada duas horas, por ponto."""
    leituras: list[Documento] = []
    for ponto in pontos:
        ocupacao = gerador.uniform(20, 55)
        dispositivo = ponto["dispositivo"]["id"]
        for hora in range(24):
            ts = FIM_TELEMETRIA - timedelta(hours=24 - hora)
            ocupacao = min(100.0, ocupacao + gerador.uniform(0.2, 2.6))
            leituras.append(
                {
                    "ts": ts,
                    "meta": {"ponto_id": ponto["_id"], "dispositivo_id": dispositivo, "tipo": "OCUPACAO"},
                    "valor": round(ocupacao, 1),
                    "unidade": "%",
                    "seq": hora + 1,
                }
            )
            if hora % 2 == 0:
                leituras.append(
                    {
                        "ts": ts,
                        "meta": {
                            "ponto_id": ponto["_id"],
                            "dispositivo_id": dispositivo,
                            "tipo": "TEMPERATURA",
                        },
                        "valor": round(gerador.uniform(21, 34), 1),
                        "unidade": "C",
                        "seq": 1000 + hora,
                    }
                )
        ponto["ocupacao"] = {
            "percentual": round(ocupacao, 1),
            "massa_estimada_kg": round(ponto["capacidade_kg"] * ocupacao / 100, 1),
            "atualizada_em": FIM_TELEMETRIA - timedelta(hours=1),
        }
    return leituras


def contagem(dados: dict[str, list[Documento]]) -> dict[str, int]:
    return {colecao: len(documentos) for colecao, documentos in dados.items()}


def total_documentos(dados: dict[str, list[Documento]]) -> int:
    return sum(contagem(dados).values())
