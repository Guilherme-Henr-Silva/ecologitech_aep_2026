# EcoTrack MVP – EcoLogitech

MVP da AEP do 6º semestre de Engenharia de Software (UniCesumar) – 2ª entrega.
Plataforma de rastreabilidade para a logística reversa de resíduos eletroeletrônicos,
com **MongoDB** e backend **multiparadigma em Python 3.12**.

Equipe: Rennan Rentz · Gabriel Gonzales · Guilherme Henrique · Deivid Galindo

## Como os paradigmas aparecem no código

| Paradigma | Onde está | O que demonstra |
|---|---|---|
| Funcional | `src/ecotrack/funcional/` | funções puras, `frozen dataclasses`, `map`/`filter`/`reduce`, closures, `lru_cache`, composição e agregação monoidal |
| Orientado a objetos | `dominio/`, `servicos/`, `persistencia/` | herança e polimorfismo (`Equipamento`), Factory, Strategy, Repository, Observer e injeção de dependência (`container.py`) |
| Concorrente/assíncrono | `concorrencia/ingestao.py` | 12 pontos IoT enviando ao mesmo tempo, `asyncio.TaskGroup` + `asyncio.Queue`, deduplicação atômica, sem estado compartilhado |
| Imperativo (encapsulado) | `funcional/rotas.py` | núcleo do vizinho mais próximo, isolado atrás de uma interface pura |

## Estrutura

```
database/            scripts do MongoDB (mongosh)
  01_criar_colecoes.js      coleções + JSON Schema Validation + índices
  02_popular_dados.js       DML com 1.442 documentos de teste (gerado e reprodutível)
  03_consultas_analiticas.js  6 Aggregation Pipelines (A1 a A6)
  04_rotinas_consistencia.js  hash da cadeia de custódia, órfãos, $merge de resumos
  05_replica_set_sharding.js  replica set rs0 (3 nós) e comandos de sharding
src/ecotrack/        código da aplicação
tests/               28 testes (pytest), incluindo testes de propriedade
```

## Executar

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# 1) sem banco: fluxo completo em memória (bom para a primeira olhada)
PYTHONPATH=src python -m ecotrack demo

# 2) com MongoDB (replica set de 3 nós)
docker compose up -d mongo1 mongo2 mongo3 iniciar-replica
mongosh "mongodb://localhost:27017/?directConnection=true" database/01_criar_colecoes.js
mongosh "mongodb://localhost:27017/?directConnection=true" database/02_popular_dados.js
mongosh "mongodb://localhost:27017/?directConnection=true" database/03_consultas_analiticas.js
mongosh "mongodb://localhost:27017/?directConnection=true" database/04_rotinas_consistencia.js

export ECOTRACK_MONGO_URI="mongodb://localhost:27017/?directConnection=true"
PYTHONPATH=src python -m ecotrack relatorios      # a aplicação executa as pipelines no banco
PYTHONPATH=src python -m ecotrack demo --mongo    # o fluxo da demo gravando no banco
uvicorn ecotrack.api.main:app --app-dir src       # API REST (documentação em /docs)
```

## Qualidade

```bash
pytest                          # 28 testes
ruff check src tests            # estilo e complexidade (máx. 8 por função)
MYPYPATH=src mypy -p ecotrack   # tipagem estática em modo strict
```

A esteira `.github/workflows/ci.yml` roda essas três verificações a cada push e,
em seguida, executa os scripts do banco contra um MongoDB 8.0 de serviço.

> Dados de clientes, pontos e preços são fictícios, criados para fins acadêmicos.
