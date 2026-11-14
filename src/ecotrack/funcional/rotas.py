"""Priorização de pontos e sugestão de rota de coleta.

A interface é funcional (entrada imutável → saída nova). Dentro de
`_vizinho_mais_proximo` o algoritmo é imperativo, com laços e listas locais,
porque é mais simples e rápido assim; o estado mutável nunca sai da função.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

RAIO_TERRA_KM = 6378.1  # mesmo raio usado pelo MongoDB nas consultas 2dsphere


@dataclass(frozen=True, slots=True)
class PontoRota:
    ponto_id: str
    nome: str
    latitude: float
    longitude: float
    ocupacao_percentual: float
    massa_estimada_kg: float


@dataclass(frozen=True, slots=True)
class RotaSugerida:
    paradas: tuple[PontoRota, ...]
    distancia_total_km: float
    massa_prevista_kg: float


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Fórmula de Haversine."""
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * RAIO_TERRA_KM * asin(sqrt(a))


def priorizar(pontos: Iterable[PontoRota], limite_percentual: float) -> tuple[PontoRota, ...]:
    """Mantém só os pontos acima do limite, do mais cheio para o menos cheio."""
    acima_do_limite = filter(lambda p: p.ocupacao_percentual >= limite_percentual, pontos)
    return tuple(sorted(acima_do_limite, key=lambda p: (-p.ocupacao_percentual, p.ponto_id)))


def _vizinho_mais_proximo(
    origem: tuple[float, float], candidatos: tuple[PontoRota, ...], capacidade_kg: float
) -> tuple[list[PontoRota], float, float]:
    pendentes = list(candidatos)
    paradas: list[PontoRota] = []
    lat, lon = origem
    distancia_total = 0.0
    carga = 0.0
    while pendentes:
        indice_mais_proximo = 0
        menor_distancia = distancia_km(lat, lon, pendentes[0].latitude, pendentes[0].longitude)
        for i in range(1, len(pendentes)):
            d = distancia_km(lat, lon, pendentes[i].latitude, pendentes[i].longitude)
            if d < menor_distancia:
                indice_mais_proximo, menor_distancia = i, d
        proximo = pendentes.pop(indice_mais_proximo)
        if carga + proximo.massa_estimada_kg > capacidade_kg:
            continue
        paradas.append(proximo)
        carga += proximo.massa_estimada_kg
        distancia_total += menor_distancia
        lat, lon = proximo.latitude, proximo.longitude
    distancia_total += distancia_km(lat, lon, *origem)  # retorno ao depósito
    return paradas, distancia_total, carga


def sugerir_rota(
    deposito: tuple[float, float],
    pontos: Iterable[PontoRota],
    limite_percentual: float,
    capacidade_veiculo_kg: float,
) -> RotaSugerida:
    prioritarios = priorizar(pontos, limite_percentual)
    paradas, distancia, carga = _vizinho_mais_proximo(deposito, prioritarios, capacidade_veiculo_kg)
    return RotaSugerida(tuple(paradas), round(distancia, 2), round(carga, 1))
