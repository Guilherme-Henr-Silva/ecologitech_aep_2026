"""Raiz de composição (injeção de dependência).

É o único lugar que conhece as classes concretas. Os serviços recebem as
dependências pelo construtor, então trocar MongoDB por memória (nos testes ou na
demonstração) não exige mudar nenhuma linha dos serviços.
"""

from dataclasses import dataclass
from typing import Any

from ecotrack.concorrencia.ingestao import ProcessadorEventosAssincrono
from ecotrack.config import Configuracao
from ecotrack.dominio.entidades import PontoDeColeta
from ecotrack.funcional.parametros import TABELA_MATERIAIS_V3, VERSAO_TABELA_VIGENTE
from ecotrack.persistencia import memoria
from ecotrack.persistencia.protocolos import (
    RepositorioConsultas,
    RepositorioEquipamento,
    RepositorioEvento,
    RepositorioPontos,
    RepositorioTelemetria,
    RepositorioTriagem,
)
from ecotrack.servicos.estrategias import PrecificacaoPorComponente
from ecotrack.servicos.observadores import AtualizadorOcupacao, GeradorAlertaColeta
from ecotrack.servicos.precificacao import ServicoPrecificacao
from ecotrack.servicos.rastreabilidade import ServicoRastreabilidade
from ecotrack.servicos.relatorios import ServicoRelatorios
from ecotrack.servicos.roteirizacao import ServicoRoteirizacao
from ecotrack.servicos.triagem import ServicoTriagem


@dataclass(slots=True)
class Repositorios:
    equipamentos: RepositorioEquipamento
    eventos: RepositorioEvento
    triagens: RepositorioTriagem
    telemetria: RepositorioTelemetria
    pontos: RepositorioPontos
    consultas: RepositorioConsultas | None = None


class Container:
    def __init__(
        self, repositorios: Repositorios, configuracao: Configuracao, cliente_banco: Any = None
    ) -> None:
        self.repositorios = repositorios
        self.configuracao = configuracao
        self._cliente_banco = cliente_banco

        self.precificacao = ServicoPrecificacao(
            PrecificacaoPorComponente(TABELA_MATERIAIS_V3), TABELA_MATERIAIS_V3, VERSAO_TABELA_VIGENTE
        )
        self.rastreabilidade = ServicoRastreabilidade(repositorios.eventos)
        self.triagem = ServicoTriagem(
            repositorios.equipamentos, repositorios.triagens, self.precificacao, self.rastreabilidade
        )
        self.roteirizacao = ServicoRoteirizacao(
            repositorios.pontos,
            (configuracao.deposito_lat, configuracao.deposito_lon),
            configuracao.capacidade_veiculo_kg,
        )
        self.alertas = GeradorAlertaColeta(limite_percentual=80.0)
        self.ingestao = ProcessadorEventosAssincrono(
            repositorios.telemetria,
            observadores=(AtualizadorOcupacao(repositorios.pontos), self.alertas),
            consumidores=configuracao.consumidores_ingestao,
        )
        self.relatorios = ServicoRelatorios(repositorios.consultas) if repositorios.consultas else None

    async def fechar(self) -> None:
        if self._cliente_banco is not None:
            await self._cliente_banco.close()


def container_em_memoria(pontos: list[PontoDeColeta], configuracao: Configuracao | None = None) -> Container:
    repositorios = Repositorios(
        equipamentos=memoria.RepositorioEquipamentoMemoria(),
        eventos=memoria.RepositorioEventoMemoria(),
        triagens=memoria.RepositorioTriagemMemoria(),
        telemetria=memoria.RepositorioTelemetriaMemoria(),
        pontos=memoria.RepositorioPontosMemoria(pontos),
    )
    return Container(repositorios, configuracao or Configuracao.do_ambiente())


def container_mongo(configuracao: Configuracao) -> Container:
    from pymongo import AsyncMongoClient  # import tardio: os testes não dependem do driver

    from ecotrack.persistencia import mongo

    if not configuracao.mongo_uri:
        raise ValueError("defina ECOTRACK_MONGO_URI para usar o MongoDB")
    cliente: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(configuracao.mongo_uri, tz_aware=True)
    banco = cliente[configuracao.banco]
    repositorios = Repositorios(
        equipamentos=mongo.RepositorioEquipamentoMongo(banco),
        eventos=mongo.RepositorioEventoMongo(banco),
        triagens=mongo.RepositorioTriagemMongo(banco),
        telemetria=mongo.RepositorioTelemetriaMongo(banco),
        pontos=mongo.RepositorioPontosMongo(banco),
        consultas=mongo.RepositorioConsultasMongo(banco),
    )
    return Container(repositorios, configuracao, cliente_banco=cliente)
