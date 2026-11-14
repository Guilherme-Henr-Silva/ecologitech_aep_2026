"""Configuração lida de variáveis de ambiente (sem segredos no código)."""

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Configuracao:
    mongo_uri: str | None
    banco: str
    deposito_lat: float
    deposito_lon: float
    capacidade_veiculo_kg: float
    consumidores_ingestao: int

    @classmethod
    def do_ambiente(cls) -> "Configuracao":
        return cls(
            mongo_uri=os.getenv("ECOTRACK_MONGO_URI"),
            banco=os.getenv("ECOTRACK_BANCO", "ecotrack"),
            deposito_lat=float(os.getenv("ECOTRACK_DEPOSITO_LAT", "-23.4400")),
            deposito_lon=float(os.getenv("ECOTRACK_DEPOSITO_LON", "-51.9200")),
            capacidade_veiculo_kg=float(os.getenv("ECOTRACK_CAPACIDADE_VEICULO_KG", "2500")),
            consumidores_ingestao=int(os.getenv("ECOTRACK_CONSUMIDORES", "8")),
        )
