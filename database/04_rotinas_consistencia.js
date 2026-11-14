// =============================================================================
// EcoTrack MVP - 04_rotinas_consistencia.js
// Rotinas de consistencia e de modelagem para relatorios de impacto ambiental.
// Executar: mongosh "mongodb://localhost:27017/ecotrack" database/04_rotinas_consistencia.js
// Em producao cada rotina vira um job agendado (frequencia indicada no titulo).
// =============================================================================
db = db.getSiblingDB("ecotrack");
const crypto = require("crypto");

// -----------------------------------------------------------------------------
// R1 (semanal) - Verificacao do encadeamento de hashes da cadeia de custodia.
// Mesma formula de src/ecotrack/servicos/rastreabilidade.py -> calcular_hash().
// -----------------------------------------------------------------------------
function hashEvento(e, anterior) {
  const conteudo = [e.codigo_rastreio, e.etapa, e.tipo, e.ts.toISOString(),
                    e.responsavel.matricula, anterior || "GENESIS"].join("|");
  return crypto.createHash("sha256").update(conteudo, "utf8").digest("hex");
}
let verificados = 0, quebrados = [];
db.eventos_rastreabilidade.aggregate([
  { $sort: { equipamento_id: 1, ts: 1, _id: 1 } },
  { $group: { _id: "$equipamento_id", codigo: { $first: "$codigo_rastreio" }, eventos: { $push: "$$ROOT" } } }
], { allowDiskUse: true }).forEach(item => {
  let anterior = null;
  const integro = item.eventos.every(e => {
    const ok = e.hash_anterior === anterior && e.hash === hashEvento(e, anterior);
    anterior = e.hash;
    return ok;
  });
  verificados++;
  if (!integro) quebrados.push(item.codigo);
});
print(`R1 - cadeia de custodia: ${verificados} equipamentos verificados, ${quebrados.length} com quebra`);
if (quebrados.length) printjson(quebrados);

// -----------------------------------------------------------------------------
// R2 (diaria) - Referencias orfas (MongoDB nao tem integridade referencial declarativa)
// -----------------------------------------------------------------------------
const orfaos = db.equipamentos.aggregate([
  { $lookup: { from: "lotes", localField: "lote_id", foreignField: "_id", as: "lote", pipeline: [{ $project: { _id: 1 } }] } },
  { $match: { lote: { $size: 0 } } },
  { $project: { _id: 0, codigo_rastreio: 1, lote_id: 1 } }
]).toArray();
const triagensSemEquipamento = db.triagens.aggregate([
  { $lookup: { from: "equipamentos", localField: "equipamento_id", foreignField: "_id", as: "eq", pipeline: [{ $project: { _id: 1 } }] } },
  { $match: { eq: { $size: 0 } } }, { $count: "total" }
]).toArray();
print(`R2 - equipamentos sem lote: ${orfaos.length}; triagens sem equipamento: ${triagensSemEquipamento.length ? triagensSemEquipamento[0].total : 0}`);

// -----------------------------------------------------------------------------
// R3 (diaria) - Recalculo do resumo incorporado nos lotes a partir das triagens
// $merge com pipeline em whenMatched: so os campos do resumo sao atualizados.
// -----------------------------------------------------------------------------
db.triagens.aggregate([
  { $match: { status: "CONCLUIDA" } },
  { $group: { _id: "$lote_id",
              massa_recuperada_kg: { $sum: "$avaliacao.massa_reciclavel_kg" },
              co2_evitado_kg: { $sum: "$avaliacao.co2_evitado_kg" },
              valor_total: { $sum: "$avaliacao.margem" } } },
  { $project: { resumo_recalculado: {
      massa_recuperada_kg: { $round: ["$massa_recuperada_kg", 3] },
      co2_evitado_kg: { $round: ["$co2_evitado_kg", 3] },
      valor_total: "$valor_total" } } },
  { $merge: { into: "lotes", on: "_id", whenNotMatched: "discard",
              whenMatched: [{ $set: {
                "resumo.massa_recuperada_kg": "$$new.resumo_recalculado.massa_recuperada_kg",
                "resumo.co2_evitado_kg": "$$new.resumo_recalculado.co2_evitado_kg",
                "resumo.valor_total": "$$new.resumo_recalculado.valor_total",
                "resumo.atualizado_em": "$$NOW" } }] } }
]);
print("R3 - resumo dos lotes recalculado a partir das triagens");

// -----------------------------------------------------------------------------
// R4 (mensal) - Consolidacao em resumos_mensais (cliente x mes x categoria)
// Reprocessar e idempotente: whenMatched "replace" sobre a chave unica uk_resumo_mensal.
// -----------------------------------------------------------------------------
db.triagens.aggregate([
  { $match: { status: "CONCLUIDA" } },
  { $group: {
      _id: { cliente_id: "$cliente_id",
             competencia: { $dateToString: { format: "%Y-%m", date: "$concluida_em" } },
             categoria: "$categoria_equipamento" },
      itens: { $sum: 1 }, lotes: { $addToSet: "$lote_id" },
      massa_recebida_kg: { $sum: "$peso_kg" },
      massa_recuperada_kg: { $sum: "$avaliacao.massa_reciclavel_kg" },
      co2_evitado_kg: { $sum: "$avaliacao.co2_evitado_kg" },
      valor_recuperado: { $sum: "$avaliacao.margem" } } },
  { $project: { _id: 0, cliente_id: "$_id.cliente_id", competencia: "$_id.competencia",
                categoria_equipamento: "$_id.categoria", itens: 1, quantidade_lotes: { $size: "$lotes" },
                massa_recebida_kg: { $round: ["$massa_recebida_kg", 2] },
                massa_recuperada_kg: { $round: ["$massa_recuperada_kg", 2] },
                co2_evitado_kg: { $round: ["$co2_evitado_kg", 2] },
                valor_recuperado: 1, atualizado_em: "$$NOW" } },
  { $merge: { into: "resumos_mensais", on: ["cliente_id", "competencia", "categoria_equipamento"],
              whenMatched: "replace", whenNotMatched: "insert" } }
]);
print(`R4 - resumos_mensais: ${db.resumos_mensais.countDocuments({})} documentos consolidados`);

// Como a soma e associativa, o total de um trimestre sai dos resumos mensais, sem tocar no dado bruto:
printjson(db.resumos_mensais.aggregate([
  { $match: { competencia: { $in: ["2026-09", "2026-10", "2026-11"] } } },
  { $group: { _id: "$competencia", co2_evitado_kg: { $sum: "$co2_evitado_kg" }, itens: { $sum: "$itens" } } },
  { $sort: { _id: 1 } }
]).toArray());

// -----------------------------------------------------------------------------
// R5 (ao alterar cliente) - Propagacao do campo duplicado lotes.cliente.nome
// -----------------------------------------------------------------------------
db.lotes.aggregate([
  { $lookup: { from: "clientes", localField: "cliente_id", foreignField: "_id", as: "origem",
               pipeline: [{ $project: { nome: 1, tipo: 1 } }] } },
  { $unwind: "$origem" },
  { $match: { $expr: { $or: [{ $ne: ["$cliente.nome", "$origem.nome"] }, { $ne: ["$cliente.tipo", "$origem.tipo"] }] } } },
  { $project: { cliente: { _id: "$cliente._id", nome: "$origem.nome", tipo: "$origem.tipo" } } },  // objeto inteiro
  { $merge: { into: "lotes", on: "_id", whenMatched: "merge", whenNotMatched: "discard" } }
]);
print("R5 - nomes de cliente propagados para os lotes divergentes");
