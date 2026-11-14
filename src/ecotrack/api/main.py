"""API REST assíncrona (FastAPI). Executar: uvicorn ecotrack.api.main:app --reload"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from ecotrack.config import Configuracao
from ecotrack.container import Container, container_mongo
from ecotrack.dominio.entidades import TransicaoInvalidaError
from ecotrack.servicos.triagem import EquipamentoNaoEncontradoError


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    app.state.container = container_mongo(Configuracao.do_ambiente())
    yield
    await app.state.container.fechar()


app = FastAPI(title="EcoTrack API", version="0.2.0", lifespan=ciclo_de_vida)


def obter_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(obter_container)]


class ComponenteEntrada(BaseModel):
    tipo: str
    material_codigo: str = Field(pattern=r"^MAT-[A-Z]{2,4}$")
    massa_kg: float = Field(ge=0)
    funcional: bool = False


class EquipamentoEntrada(BaseModel):
    codigo_rastreio: str = Field(pattern=r"^EQ-[0-9A-HJKMNP-TV-Z]{26}$")
    lote_id: str
    categoria: str
    marca: str = ""
    modelo: str = ""
    peso_kg: float = Field(gt=0, le=500)
    estado: str = "NAO_AVALIADO"
    atributos: dict[str, Any] = Field(default_factory=dict)  # esquema flexível
    componentes: list[ComponenteEntrada]


class Responsavel(BaseModel):
    matricula: str
    nome: str


@app.post("/equipamentos", status_code=201)
async def receber_equipamento(
    entrada: EquipamentoEntrada, responsavel: Responsavel, container: ContainerDep
) -> dict[str, str]:
    try:
        equipamento = await container.triagem.receber(
            entrada.model_dump(), (responsavel.matricula, responsavel.nome)
        )
    except ValueError as erro:
        raise HTTPException(422, str(erro)) from erro
    return {"codigo_rastreio": equipamento.codigo_rastreio, "classe": type(equipamento).__name__}


@app.post("/equipamentos/{codigo}/triagem")
async def triar(codigo: str, responsavel: Responsavel, container: ContainerDep) -> dict[str, Any]:
    try:
        avaliado = await container.triagem.triar(codigo, (responsavel.matricula, responsavel.nome))
    except EquipamentoNaoEncontradoError as erro:
        raise HTTPException(404, f"equipamento {codigo} não encontrado") from erro
    except TransicaoInvalidaError as erro:
        raise HTTPException(409, str(erro)) from erro
    return {
        "destino": avaliado.destino,
        "valor_estimado": str(avaliado.valor_estimado),
        "margem": str(avaliado.margem),
        "co2_evitado_kg": avaliado.co2_evitado_kg,
    }


@app.get("/equipamentos/{codigo}/historico")
async def historico(codigo: str, container: ContainerDep) -> dict[str, Any]:
    eventos = await container.rastreabilidade.historico(codigo)
    return {
        "codigo_rastreio": codigo,
        "cadeia_integra": await container.rastreabilidade.verificar(codigo),
        "eventos": [
            {"etapa": e.etapa, "tipo": e.tipo, "ts": e.ts, "responsavel": e.responsavel[1], "hash": e.hash}
            for e in eventos
        ],
    }


@app.get("/relatorios/co2-por-cliente")
async def co2_por_cliente(container: ContainerDep, inicio: datetime, fim: datetime) -> list[dict[str, Any]]:
    assert container.relatorios is not None
    return await container.relatorios.co2_por_cliente(inicio, fim)


@app.get("/relatorios/ocupacao")
async def ocupacao(container: ContainerDep) -> list[dict[str, Any]]:
    assert container.relatorios is not None
    return await container.relatorios.ocupacao_ultimas_24h(datetime.now(UTC))


@app.get("/rotas/sugestao")
async def sugestao_de_rota(container: ContainerDep, limite: float = 70.0) -> dict[str, Any]:
    rota = await container.roteirizacao.sugerir(limite)
    return {
        "distancia_total_km": rota.distancia_total_km,
        "massa_prevista_kg": rota.massa_prevista_kg,
        "paradas": [{"ponto": p.nome, "ocupacao_pct": p.ocupacao_percentual} for p in rota.paradas],
    }
