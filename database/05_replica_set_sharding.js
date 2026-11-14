// =============================================================================
// EcoTrack MVP - 05_replica_set_sharding.js
// Parte A (executar no piloto): configura o conjunto de replicas rs0 com 3 nos.
// Parte B (evolucao): comandos de fragmentacao, prontos para quando o volume justificar.
// Executar a parte A conectado ao no mongo1:  mongosh "mongodb://localhost:27017" 05_replica_set_sharding.js
// =============================================================================

// ------------------------------------------------------- PARTE A - REPLICA SET
const config = {
  _id: "rs0",
  members: [
    { _id: 0, host: "mongo1:27017", priority: 2 },   // preferido como primario
    { _id: 1, host: "mongo2:27017", priority: 1 },
    { _id: 2, host: "mongo3:27017", priority: 1, tags: { uso: "analitico" } }   // alvo dos relatorios
  ]
};
try { rs.status(); print("rs0 ja iniciado"); }
catch (e) { rs.initiate(config); print("rs0 iniciado - aguardando eleicao do primario..."); sleep(5000); }

// Escrita confirmada pela maioria (2 de 3): uma falha de no nao perde dado confirmado.
db.adminCommand({ setDefaultRWConcern: 1,
                  defaultWriteConcern: { w: "majority", wtimeout: 5000 },
                  defaultReadConcern: { level: "majority" } });

rs.status().members.forEach(m => print(`  ${m.name.padEnd(14)} ${m.stateStr}`));
// String de conexao da aplicacao (failover automatico e transparente para o driver):
// mongodb://mongo1:27017,mongo2:27017,mongo3:27017/ecotrack?replicaSet=rs0&retryWrites=true&w=majority
// Relatorios: readPreference=secondaryPreferred&readPreferenceTags=uso:analitico

// Teste de tolerancia a falhas (manual, no terminal):
//   docker stop mongo1            -> mongo2 ou mongo3 vira primario em ~10 s
//   rs.status()                   -> conferir novo PRIMARY
//   docker start mongo1           -> volta como SECONDARY e depois retoma o primario (priority 2)

// --------------------------------------------- PARTE B - SHARDING (EVOLUCAO)
// Pre-requisitos: 3 config servers (replica set "cfg"), 2+ shards (cada um um replica set)
// e roteadores mongos. Executar conectado ao mongos. Chaves definidas no Quadro 34 da 1a entrega.
/*
sh.enableSharding("ecotrack");
sh.shardCollection("ecotrack.equipamentos",            { lote_id: 1, codigo_rastreio: 1 });
sh.shardCollection("ecotrack.eventos_rastreabilidade", { equipamento_id: 1, evento_chave: 1 });
sh.shardCollection("ecotrack.triagens",                { equipamento_id: 1, iniciada_em: 1 });
sh.shardCollection("ecotrack.lotes",                   { cliente_id: 1, codigo: 1 });
sh.shardCollection("ecotrack.leituras_telemetria",     { "meta.ponto_id": 1, ts: 1 });   // series temporais
// clientes, pontos_coleta e materiais: nao fragmentadas (ficam no shard primario)

// Zonas por regiao (opcional, quando houver plantas em outros estados):
sh.addShardToZone("shard-sul", "SUL");
sh.updateZoneKeyRange("ecotrack.lotes", { cliente_id: MinKey(), codigo: MinKey() },
                                        { cliente_id: MaxKey(), codigo: MaxKey() }, "SUL");
sh.status();
*/
