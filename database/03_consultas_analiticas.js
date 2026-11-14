// =============================================================================
// EcoTrack MVP - 03_consultas_analiticas.js  (Aggregation Framework)
// Executar: mongosh "mongodb://localhost:27017/ecotrack" database/03_consultas_analiticas.js
// As mesmas pipelines estao em src/ecotrack/consultas/pipelines.py e sao chamadas
// pela aplicacao (ServicoRelatorios) - o banco executa e devolve os dados prontos.
// Relatorios pesados podem rodar em no secundario: readPref("secondaryPreferred").
// =============================================================================
db = db.getSiblingDB("ecotrack");
db.getMongo().setReadPref("secondaryPreferred");   // isola a carga analitica (ver 05)

const INICIO = ISODate("2026-09-01T00:00:00Z");
const FIM    = ISODate("2026-12-01T00:00:00Z");
const MES_INICIO = ISODate("2026-10-01T00:00:00Z");   // mes analisado: outubro/2026
const MES_FIM    = ISODate("2026-11-01T00:00:00Z");
const REFERENCIA = ISODate("2026-11-13T00:00:00Z");   // "agora" da demonstracao
const DEPOSITO   = { type: "Point", coordinates: [-51.9200, -23.4400] };  // planta (ficticia)
const mostrar = (titulo, cursor) => { print("\n=== " + titulo); printjson(cursor.toArray()); };

// -----------------------------------------------------------------------------
// A1 - Total de CO2 evitado por cliente no periodo (com participacao no total)
// Indice usado: ix_triagem_periodo
// -----------------------------------------------------------------------------
mostrar("A1 - CO2 evitado por cliente", db.triagens.aggregate([
  { $match: { status: "CONCLUIDA", concluida_em: { $gte: INICIO, $lt: FIM } } },
  { $group: {
      _id: "$cliente_id",
      itens: { $sum: 1 },
      co2_evitado_kg: { $sum: "$avaliacao.co2_evitado_kg" },
      massa_reciclada_kg: { $sum: "$avaliacao.massa_reciclavel_kg" },
      valor_recuperado: { $sum: "$avaliacao.margem" } } },
  { $setWindowFields: {                                   // total geral sem nova consulta
      sortBy: { co2_evitado_kg: -1 },
      output: { co2_total: { $sum: "$co2_evitado_kg", window: { documents: ["unbounded", "unbounded"] } } } } },
  { $lookup: { from: "clientes", localField: "_id", foreignField: "_id", as: "cliente",
               pipeline: [{ $project: { nome: 1, tipo: 1 } }] } },
  { $unwind: "$cliente" },
  { $project: {
      _id: 0, cliente: "$cliente.nome", tipo: "$cliente.tipo", itens: 1,
      co2_evitado_kg: { $round: ["$co2_evitado_kg", 1] },
      massa_reciclada_kg: { $round: ["$massa_reciclada_kg", 1] },
      valor_recuperado: { $round: [{ $toDouble: "$valor_recuperado" }, 2] },
      participacao_pct: { $round: [{ $multiply: [{ $divide: ["$co2_evitado_kg", "$co2_total"] }, 100] }, 1] } } },
  { $sort: { co2_evitado_kg: -1 } }
]));

// -----------------------------------------------------------------------------
// A2 - Volume de material reciclado por categoria no mes (desmontagem)
// Indice usado: ix_triagem_periodo  |  $unwind no vetor incorporado
// -----------------------------------------------------------------------------
mostrar("A2 - Material reciclado por categoria (out/2026)", db.triagens.aggregate([
  { $match: { status: "CONCLUIDA", destino: "DESMONTAR", concluida_em: { $gte: MES_INICIO, $lt: MES_FIM } } },
  { $unwind: "$materiais_recuperados" },
  { $group: {
      _id: "$materiais_recuperados.categoria_material",
      massa_kg: { $sum: "$materiais_recuperados.massa_kg" },
      materiais: { $addToSet: "$materiais_recuperados.material_codigo" },
      equipamentos: { $addToSet: "$equipamento_id" } } },
  { $project: {
      _id: 0, categoria_material: "$_id",
      massa_kg: { $round: ["$massa_kg", 2] },
      materiais: { $sortArray: { input: "$materiais", sortBy: 1 } },
      equipamentos_desmontados: { $size: "$equipamentos" } } },
  { $sort: { massa_kg: -1 } }
]));

// -----------------------------------------------------------------------------
// A3 - Tempo medio de processamento por ponto de coleta (coleta -> fim da triagem)
// Indice usado: ix_triagem_ponto
// -----------------------------------------------------------------------------
mostrar("A3 - Tempo medio de processamento por ponto", db.triagens.aggregate([
  { $match: { status: "CONCLUIDA" } },
  { $project: { ponto_coleta_id: 1,
                horas: { $divide: [{ $subtract: ["$concluida_em", "$coletado_em"] }, 3600000] } } },
  { $group: { _id: "$ponto_coleta_id", itens: { $sum: 1 },
              media_h: { $avg: "$horas" }, minimo_h: { $min: "$horas" }, maximo_h: { $max: "$horas" } } },
  { $lookup: { from: "pontos_coleta", localField: "_id", foreignField: "_id", as: "ponto",
               pipeline: [{ $project: { codigo: 1, nome: 1 } }] } },
  { $unwind: "$ponto" },
  { $project: { _id: 0, ponto: { $concat: ["$ponto.codigo", " - ", "$ponto.nome"] }, itens: 1,
                media_h: { $round: ["$media_h", 1] }, minimo_h: { $round: ["$minimo_h", 1] },
                maximo_h: { $round: ["$maximo_h", 1] } } },
  { $sort: { media_h: -1 } }
]));

// -----------------------------------------------------------------------------
// A4 - Ocupacao dos pontos nas ultimas 24 h (colecao de series temporais)
// Indice usado: ix_leituras_ponto + indice automatico de meta/ts
// -----------------------------------------------------------------------------
mostrar("A4 - Ocupacao nas ultimas 24 h", db.leituras_telemetria.aggregate([
  { $match: { "meta.tipo": "OCUPACAO",
              ts: { $gte: new Date(REFERENCIA.getTime() - 24 * 3600 * 1000), $lt: REFERENCIA } } },
  { $sort: { "meta.ponto_id": 1, ts: 1 } },
  { $group: { _id: "$meta.ponto_id", leituras: { $sum: 1 },
              media_pct: { $avg: "$valor" }, pico_pct: { $max: "$valor" },
              primeira_pct: { $first: "$valor" }, ultima_pct: { $last: "$valor" } } },
  { $lookup: { from: "pontos_coleta", localField: "_id", foreignField: "_id", as: "ponto",
               pipeline: [{ $project: { codigo: 1, nome: 1, capacidade_kg: 1, limite_alerta_percentual: 1 } }] } },
  { $unwind: "$ponto" },
  { $project: {
      _id: 0, ponto: "$ponto.codigo", nome: "$ponto.nome", leituras: 1,
      media_pct: { $round: ["$media_pct", 1] }, pico_pct: 1, ultima_pct: 1,
      crescimento_24h_pct: { $round: [{ $subtract: ["$ultima_pct", "$primeira_pct"] }, 1] },
      massa_estimada_kg: { $round: [{ $multiply: ["$ponto.capacidade_kg", { $divide: ["$ultima_pct", 100] }] }, 0] },
      precisa_coleta: { $gte: ["$ultima_pct", "$ponto.limite_alerta_percentual"] } } },
  { $sort: { ultima_pct: -1 } }
]));

// -----------------------------------------------------------------------------
// A5 - Destinacao por categoria de equipamento ($facet: duas visoes em uma ida ao banco)
// -----------------------------------------------------------------------------
mostrar("A5 - Destinacao por categoria", db.triagens.aggregate([
  { $match: { status: "CONCLUIDA" } },
  { $facet: {
      por_categoria: [
        { $group: { _id: { categoria: "$categoria_equipamento", destino: "$destino" }, itens: { $sum: 1 } } },
        { $group: { _id: "$_id.categoria", total: { $sum: "$itens" },
                    destinos: { $push: { k: "$_id.destino", v: "$itens" } } } },
        { $project: { _id: 0, categoria: "$_id", total: 1, destinos: { $arrayToObject: "$destinos" } } },
        { $addFields: { taxa_recondicionamento_pct: { $round: [{ $multiply: [
            { $divide: [{ $ifNull: ["$destinos.RECONDICIONAR", 0] }, "$total"] }, 100] }, 1] } } },
        { $sort: { total: -1 } } ],
      geral: [
        { $group: { _id: "$destino", itens: { $sum: 1 } } },
        { $sort: { itens: -1 } } ] } }
]));

// -----------------------------------------------------------------------------
// A6 - Pontos prioritarios para a rota do dia ($geoNear + indice 2dsphere)
// -----------------------------------------------------------------------------
mostrar("A6 - Pontos para a rota (raio de 15 km, ocupacao >= 60%)", db.pontos_coleta.aggregate([
  { $geoNear: { near: DEPOSITO, distanceField: "distancia_m", spherical: true, maxDistance: 15000,
                query: { status: "ATIVO", "ocupacao.percentual": { $gte: 60 } } } },
  { $project: { _id: 0, codigo: 1, nome: 1, ocupacao_pct: "$ocupacao.percentual",
                massa_estimada_kg: "$ocupacao.massa_estimada_kg",
                distancia_km: { $round: [{ $divide: ["$distancia_m", 1000] }, 2] } } },
  { $sort: { ocupacao_pct: -1 } }
]));

// Plano de execucao de exemplo (prova de uso de indice)
print("\n=== explain do filtro de A1 (plano vencedor deve ser IXSCAN em ix_triagem_periodo)");
const plano = db.triagens.find({ status: "CONCLUIDA", concluida_em: { $gte: INICIO, $lt: FIM } }).explain("executionStats");
printjson({ plano: plano.queryPlanner.winningPlan, docs_examinados: plano.executionStats.totalDocsExamined,
            chaves_examinadas: plano.executionStats.totalKeysExamined });
