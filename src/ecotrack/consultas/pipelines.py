"""Pipelines de agregação usados pela aplicação (espelho de database/03_consultas_analiticas.js).

Cada função devolve (coleção, pipeline). O MongoDB executa o cálculo e a
aplicação só recebe o resultado pronto.
"""

from datetime import datetime, timedelta
from typing import Any

Pipeline = list[dict[str, Any]]
Consulta = tuple[str, Pipeline]


def _arredondar(campo: str, casas: int = 1) -> dict[str, Any]:
    return {"$round": [campo, casas]}


def _lookup(colecao: str, campos: tuple[str, ...]) -> dict[str, Any]:
    return {
        "$lookup": {
            "from": colecao,
            "localField": "_id",
            "foreignField": "_id",
            "as": "origem",
            "pipeline": [{"$project": dict.fromkeys(campos, 1)}],
        }
    }


def co2_por_cliente(inicio: datetime, fim: datetime) -> Consulta:
    return "triagens", [
        {"$match": {"status": "CONCLUIDA", "concluida_em": {"$gte": inicio, "$lt": fim}}},
        {
            "$group": {
                "_id": "$cliente_id",
                "itens": {"$sum": 1},
                "co2_evitado_kg": {"$sum": "$avaliacao.co2_evitado_kg"},
                "massa_reciclada_kg": {"$sum": "$avaliacao.massa_reciclavel_kg"},
                "valor_recuperado": {"$sum": "$avaliacao.margem"},
            }
        },
        {
            "$setWindowFields": {
                "sortBy": {"co2_evitado_kg": -1},
                "output": {
                    "co2_total": {
                        "$sum": "$co2_evitado_kg",
                        "window": {"documents": ["unbounded", "unbounded"]},
                    }
                },
            }
        },
        _lookup("clientes", ("nome", "tipo")),
        {"$unwind": "$origem"},
        {
            "$project": {
                "_id": 0,
                "cliente": "$origem.nome",
                "tipo": "$origem.tipo",
                "itens": 1,
                "co2_evitado_kg": _arredondar("$co2_evitado_kg"),
                "massa_reciclada_kg": _arredondar("$massa_reciclada_kg"),
                "valor_recuperado": {"$round": [{"$toDouble": "$valor_recuperado"}, 2]},
                "participacao_pct": {
                    "$round": [{"$multiply": [{"$divide": ["$co2_evitado_kg", "$co2_total"]}, 100]}, 1]
                },
            }
        },
        {"$sort": {"co2_evitado_kg": -1}},
    ]


def material_reciclado_no_mes(inicio_mes: datetime, fim_mes: datetime) -> Consulta:
    return "triagens", [
        {
            "$match": {
                "status": "CONCLUIDA",
                "destino": "DESMONTAR",
                "concluida_em": {"$gte": inicio_mes, "$lt": fim_mes},
            }
        },
        {"$unwind": "$materiais_recuperados"},
        {
            "$group": {
                "_id": "$materiais_recuperados.categoria_material",
                "massa_kg": {"$sum": "$materiais_recuperados.massa_kg"},
                "materiais": {"$addToSet": "$materiais_recuperados.material_codigo"},
                "equipamentos": {"$addToSet": "$equipamento_id"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "categoria_material": "$_id",
                "massa_kg": _arredondar("$massa_kg", 2),
                "materiais": {"$sortArray": {"input": "$materiais", "sortBy": 1}},
                "equipamentos_desmontados": {"$size": "$equipamentos"},
            }
        },
        {"$sort": {"massa_kg": -1}},
    ]


def tempo_medio_por_ponto() -> Consulta:
    return "triagens", [
        {"$match": {"status": "CONCLUIDA"}},
        {
            "$project": {
                "ponto_coleta_id": 1,
                "horas": {"$divide": [{"$subtract": ["$concluida_em", "$coletado_em"]}, 3_600_000]},
            }
        },
        {
            "$group": {
                "_id": "$ponto_coleta_id",
                "itens": {"$sum": 1},
                "media_h": {"$avg": "$horas"},
                "minimo_h": {"$min": "$horas"},
                "maximo_h": {"$max": "$horas"},
            }
        },
        _lookup("pontos_coleta", ("codigo", "nome")),
        {"$unwind": "$origem"},
        {
            "$project": {
                "_id": 0,
                "ponto": {"$concat": ["$origem.codigo", " - ", "$origem.nome"]},
                "itens": 1,
                "media_h": _arredondar("$media_h"),
                "minimo_h": _arredondar("$minimo_h"),
                "maximo_h": _arredondar("$maximo_h"),
            }
        },
        {"$sort": {"media_h": -1}},
    ]


def ocupacao_ultimas_24h(referencia: datetime) -> Consulta:
    return "leituras_telemetria", [
        {
            "$match": {
                "meta.tipo": "OCUPACAO",
                "ts": {"$gte": referencia - timedelta(hours=24), "$lt": referencia},
            }
        },
        {"$sort": {"meta.ponto_id": 1, "ts": 1}},
        {
            "$group": {
                "_id": "$meta.ponto_id",
                "leituras": {"$sum": 1},
                "media_pct": {"$avg": "$valor"},
                "pico_pct": {"$max": "$valor"},
                "primeira_pct": {"$first": "$valor"},
                "ultima_pct": {"$last": "$valor"},
            }
        },
        _lookup("pontos_coleta", ("codigo", "nome", "capacidade_kg", "limite_alerta_percentual")),
        {"$unwind": "$origem"},
        {
            "$project": {
                "_id": 0,
                "ponto": "$origem.codigo",
                "nome": "$origem.nome",
                "leituras": 1,
                "media_pct": _arredondar("$media_pct"),
                "pico_pct": 1,
                "ultima_pct": 1,
                "crescimento_24h_pct": {"$round": [{"$subtract": ["$ultima_pct", "$primeira_pct"]}, 1]},
                "massa_estimada_kg": {
                    "$round": [{"$multiply": ["$origem.capacidade_kg", {"$divide": ["$ultima_pct", 100]}]}, 0]
                },
                "precisa_coleta": {"$gte": ["$ultima_pct", "$origem.limite_alerta_percentual"]},
            }
        },
        {"$sort": {"ultima_pct": -1}},
    ]


def destinacao_por_categoria() -> Consulta:
    return "triagens", [
        {"$match": {"status": "CONCLUIDA"}},
        {
            "$facet": {
                "por_categoria": [
                    {
                        "$group": {
                            "_id": {"categoria": "$categoria_equipamento", "destino": "$destino"},
                            "itens": {"$sum": 1},
                        }
                    },
                    {
                        "$group": {
                            "_id": "$_id.categoria",
                            "total": {"$sum": "$itens"},
                            "destinos": {"$push": {"k": "$_id.destino", "v": "$itens"}},
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "categoria": "$_id",
                            "total": 1,
                            "destinos": {"$arrayToObject": "$destinos"},
                        }
                    },
                    {
                        "$addFields": {
                            "taxa_recondicionamento_pct": {
                                "$round": [
                                    {
                                        "$multiply": [
                                            {
                                                "$divide": [
                                                    {"$ifNull": ["$destinos.RECONDICIONAR", 0]},
                                                    "$total",
                                                ]
                                            },
                                            100,
                                        ]
                                    },
                                    1,
                                ]
                            }
                        }
                    },
                    {"$sort": {"total": -1}},
                ],
                "geral": [{"$group": {"_id": "$destino", "itens": {"$sum": 1}}}, {"$sort": {"itens": -1}}],
            }
        },
    ]


def pontos_para_rota(
    longitude: float, latitude: float, raio_m: int = 15_000, ocupacao_minima: float = 60.0
) -> Consulta:
    return "pontos_coleta", [
        {
            "$geoNear": {
                "near": {"type": "Point", "coordinates": [longitude, latitude]},
                "distanceField": "distancia_m",
                "spherical": True,
                "maxDistance": raio_m,
                "query": {"status": "ATIVO", "ocupacao.percentual": {"$gte": ocupacao_minima}},
            }
        },
        {
            "$project": {
                "_id": 0,
                "codigo": 1,
                "nome": 1,
                "ocupacao_pct": "$ocupacao.percentual",
                "massa_estimada_kg": "$ocupacao.massa_estimada_kg",
                "distancia_km": {"$round": [{"$divide": ["$distancia_m", 1000]}, 2]},
            }
        },
        {"$sort": {"ocupacao_pct": -1}},
    ]


def resumos_de_lotes_por_cliente() -> Consulta:
    """Entrada do pipeline de bonificação: um resumo por lote concluído."""
    return "lotes", [
        {"$match": {"status": "CONCLUIDO"}},
        {
            "$lookup": {
                "from": "triagens",
                "localField": "_id",
                "foreignField": "lote_id",
                "as": "t",
                "pipeline": [{"$match": {"destino": "RECONDICIONAR"}}, {"$count": "n"}],
            }
        },
        {
            "$project": {
                "_id": 0,
                "cliente_id": 1,
                "cliente": "$cliente.nome",
                "massa_recuperada_kg": "$resumo.massa_recuperada_kg",
                "co2_evitado_kg": "$resumo.co2_evitado_kg",
                "recondicionados": {"$ifNull": [{"$first": "$t.n"}, 0]},
            }
        },
    ]
