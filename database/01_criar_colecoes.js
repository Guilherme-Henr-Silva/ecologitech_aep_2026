// =============================================================================
// EcoTrack MVP - 01_criar_colecoes.js  (DDL: colecoes, JSON Schema e indices)
// Executar: mongosh "mongodb://localhost:27017/ecotrack" database/01_criar_colecoes.js
// ATENCAO: o script recria as colecoes do zero (drop + create). Use so em dev/homolog.
// =============================================================================
db = db.getSiblingDB("ecotrack");

const COLECOES = ["clientes", "pontos_coleta", "materiais", "coletas", "lotes", "equipamentos",
  "triagens", "eventos_rastreabilidade", "leituras_telemetria", "controle_ingestao", "resumos_mensais"];
COLECOES.forEach(nome => { if (db.getCollectionNames().includes(nome)) db[nome].drop(); });

const ETAPAS = ["COLETA", "TRIAGEM", "DESCARTE", "RECONDICIONAMENTO", "COMERCIALIZACAO"];
const DESTINOS = ["RECONDICIONAR", "DESMONTAR", "DESCARTAR"];
const CATEGORIAS = ["COMPUTADOR", "DISPOSITIVO_MOVEL", "ELETRODOMESTICO", "PERIFERICO", "BATERIA", "OUTRO"];
const RESPONSAVEL = { bsonType: "object", required: ["matricula", "nome"],
  properties: { matricula: { bsonType: "string" }, nome: { bsonType: "string" } } };

// ---------------------------------------------------------------- clientes
db.createCollection("clientes", { validator: { $jsonSchema: {
  bsonType: "object", title: "Gerador do residuo (cliente)",
  required: ["tipo", "nome", "documento", "status", "criado_em"],
  properties: {
    tipo:      { enum: ["CORPORATIVO", "ORGAO_PUBLICO", "PROGRAMA_RESIDENCIAL"] },
    nome:      { bsonType: "string", minLength: 3, maxLength: 120 },
    documento: { bsonType: "string", pattern: "^[0-9]{2}\\.[0-9]{3}\\.[0-9]{3}/[0-9]{4}-[0-9]{2}$" },
    contatos:  { bsonType: "array", items: { bsonType: "object", required: ["tipo", "valor"] } },
    enderecos: { bsonType: "array" },
    bonificacao: { bsonType: "object" },
    status:    { enum: ["ATIVO", "INATIVO"] },
    criado_em: { bsonType: "date" }
  } } }, validationLevel: "strict", validationAction: "error" });

// ----------------------------------------------------------- pontos_coleta
db.createCollection("pontos_coleta", { validator: { $jsonSchema: {
  bsonType: "object", title: "Ponto de coleta com coletor IoT",
  required: ["codigo", "nome", "tipo", "localizacao", "capacidade_kg", "limite_alerta_percentual", "status"],
  properties: {
    codigo:     { bsonType: "string", pattern: "^PC-[0-9]{3}$" },
    nome:       { bsonType: "string" },
    tipo:       { enum: ["VAREJO", "CONDOMINIO", "ORGAO_PUBLICO", "EMPRESA", "INSTITUICAO_ENSINO"] },
    cliente_id: { bsonType: ["objectId", "null"] },
    localizacao: { bsonType: "object", required: ["type", "coordinates"],
      properties: { type: { enum: ["Point"] },
                    coordinates: { bsonType: "array", minItems: 2, maxItems: 2, items: { bsonType: "double" } } } },
    capacidade_kg: { bsonType: "double", minimum: 1 },
    limite_alerta_percentual: { bsonType: "double", minimum: 0, maximum: 100 },
    ocupacao: { bsonType: "object", properties: {
      percentual: { bsonType: "double", minimum: 0, maximum: 100 },
      massa_estimada_kg: { bsonType: "double", minimum: 0 },
      atualizada_em: { bsonType: "date" } } },
    status: { enum: ["ATIVO", "MANUTENCAO", "INATIVO"] }
  } } }, validationLevel: "strict", validationAction: "error" });

// --------------------------------------------------------------- materiais
db.createCollection("materiais", { validator: { $jsonSchema: {
  bsonType: "object", title: "Tabela versionada de materiais",
  required: ["codigo", "versao", "nome", "categoria", "preco_por_kg", "rendimento_recuperacao", "fator_co2_evitado", "vigencia_inicio"],
  properties: {
    codigo: { bsonType: "string", pattern: "^MAT-[A-Z]{2,4}$" },
    versao: { bsonType: "int", minimum: 1 },
    preco_por_kg: { bsonType: "decimal" },
    rendimento_recuperacao: { bsonType: "double", minimum: 0, maximum: 1 },
    fator_co2_evitado: { bsonType: "double", minimum: 0 },
    vigencia_inicio: { bsonType: "date" },
    vigencia_fim: { bsonType: ["date", "null"] }
  } } }, validationLevel: "strict", validationAction: "error" });

// ----------------------------------------------------------------- coletas
db.createCollection("coletas", { validator: { $jsonSchema: {
  bsonType: "object", title: "Operacao de recolhimento em um ponto",
  required: ["codigo", "ponto_coleta", "status", "responsavel"],
  properties: {
    codigo: { bsonType: "string", pattern: "^COL-[0-9]{4}-[0-9]{4}$" },
    ponto_coleta: { bsonType: "object", required: ["_id", "codigo"] },
    status: { enum: ["AGENDADA", "REALIZADA", "CANCELADA"] },
    agendada_para: { bsonType: "date" },
    realizada_em: { bsonType: ["date", "null"] },
    responsavel: RESPONSAVEL,
    massa_total_kg: { bsonType: "double", minimum: 0 },
    quantidade_lotes: { bsonType: "int", minimum: 0 }
  } } }, validationLevel: "strict", validationAction: "error" });

// ------------------------------------------------------------------- lotes
db.createCollection("lotes", { validator: { $jsonSchema: {
  bsonType: "object", title: "Lote: unidade de rastreabilidade perante o cliente",
  required: ["codigo", "coleta_id", "cliente", "cliente_id", "ponto_coleta_id", "status", "aberto_em"],
  properties: {
    codigo: { bsonType: "string", pattern: "^LT-[0-9]{4}-[0-9]{4}$" },
    coleta_id: { bsonType: "objectId" },
    cliente_id: { bsonType: "objectId" },          // prefixo da chave de fragmento { cliente_id, codigo }
    cliente: { bsonType: "object", required: ["_id", "nome", "tipo"] },   // referencia com extensao
    ponto_coleta_id: { bsonType: "objectId" },
    status: { enum: ["EM_ABERTO", "CONCLUIDO"] },
    aberto_em: { bsonType: "date" },
    concluido_em: { bsonType: ["date", "null"] },
    resumo: { bsonType: "object", properties: {
      quantidade_itens: { bsonType: "int" },
      massa_recebida_kg: { bsonType: "double" },
      massa_recuperada_kg: { bsonType: "double" },
      valor_total: { bsonType: "decimal" },
      co2_evitado_kg: { bsonType: "double" } } },
    certificado: { bsonType: "object", required: ["numero", "emitido_em", "hash_sha256"] }
  } } }, validationLevel: "strict", validationAction: "error" });

// ------------------------------------------------------------ equipamentos
db.createCollection("equipamentos", { validator: { $jsonSchema: {
  bsonType: "object", title: "Equipamento recebido na cadeia de logistica reversa",
  required: ["codigo_rastreio", "lote_id", "categoria", "peso_kg", "estado", "status", "etapa_atual", "schema_versao", "recebido_em"],
  properties: {
    codigo_rastreio: { bsonType: "string", pattern: "^EQ-[0-9A-HJKMNP-TV-Z]{26}$" },
    lote_id: { bsonType: "objectId" }, coleta_id: { bsonType: "objectId" },
    cliente_id: { bsonType: "objectId" }, ponto_coleta_id: { bsonType: "objectId" },
    categoria: { enum: CATEGORIAS },
    marca: { bsonType: "string", maxLength: 80 }, modelo: { bsonType: "string", maxLength: 120 },
    peso_kg: { bsonType: "double", minimum: 0, maximum: 500 },
    estado: { enum: ["FUNCIONAL", "PARCIAL", "INOPERANTE", "NAO_AVALIADO"] },
    status: { enum: ["RECEBIDO", "EM_TRIAGEM", "TRIADO", "DESTINADO"] },
    etapa_atual: { enum: ETAPAS },
    destino: { enum: DESTINOS.concat([null]) },
    atributos: { bsonType: "object" },                        // esquema flexivel por categoria
    componentes: { bsonType: "array", items: { bsonType: "object",
      required: ["tipo", "material_codigo", "massa_kg"],
      properties: { tipo: { bsonType: "string" }, material_codigo: { bsonType: "string" },
                    massa_kg: { bsonType: "double", minimum: 0 }, funcional: { bsonType: "bool" } },
      additionalProperties: false } },
    exige_sanitizacao: { bsonType: "bool" },
    ultimo_evento_hash: { bsonType: ["string", "null"] },
    versao: { bsonType: "int", minimum: 1 },                  // concorrencia otimista
    schema_versao: { bsonType: "int", minimum: 1 },
    recebido_em: { bsonType: "date" }
  } } }, validationLevel: "moderate", validationAction: "error" });

// ---------------------------------------------------------------- triagens
db.createCollection("triagens", { validator: { $jsonSchema: {
  bsonType: "object", title: "Triagem e avaliacao de um equipamento",
  required: ["equipamento_id", "codigo_rastreio", "categoria_equipamento", "lote_id", "status", "iniciada_em", "responsavel"],
  properties: {
    equipamento_id: { bsonType: "objectId" }, lote_id: { bsonType: "objectId" },
    cliente_id: { bsonType: "objectId" }, ponto_coleta_id: { bsonType: "objectId" },
    categoria_equipamento: { enum: CATEGORIAS },
    peso_kg: { bsonType: "double", minimum: 0 },
    responsavel: RESPONSAVEL,
    status: { enum: ["EM_ANDAMENTO", "CONCLUIDA"] },
    coletado_em: { bsonType: "date" }, iniciada_em: { bsonType: "date" }, concluida_em: { bsonType: ["date", "null"] },
    avaliacao: { bsonType: "object",
      required: ["tabela_versao", "valor_estimado", "custo_atribuido", "margem", "co2_evitado_kg", "massa_reciclavel_kg"],
      properties: { tabela_versao: { bsonType: "int" }, valor_estimado: { bsonType: "decimal" },
                    custo_atribuido: { bsonType: "decimal" }, margem: { bsonType: "decimal" },
                    co2_evitado_kg: { bsonType: "double", minimum: 0 }, massa_reciclavel_kg: { bsonType: "double", minimum: 0 } } },
    materiais_recuperados: { bsonType: "array", items: { bsonType: "object",
      required: ["material_codigo", "categoria_material", "massa_kg"],
      properties: { massa_kg: { bsonType: "double", minimum: 0 } } } },
    destino: { enum: DESTINOS.concat([null]) }
  } } }, validationLevel: "strict", validationAction: "error" });

// ------------------------------------------------- eventos_rastreabilidade
db.createCollection("eventos_rastreabilidade", { validator: { $jsonSchema: {
  bsonType: "object", title: "Evento imutavel da cadeia de custodia",
  required: ["evento_chave", "equipamento_id", "codigo_rastreio", "etapa", "tipo", "ts", "responsavel", "hash"],
  properties: {
    evento_chave: { bsonType: "string", maxLength: 120 },     // chave natural -> idempotencia
    equipamento_id: { bsonType: "objectId" }, lote_id: { bsonType: "objectId" },
    codigo_rastreio: { bsonType: "string" },
    etapa: { enum: ETAPAS },
    tipo: { enum: ["ENTRADA", "SAIDA", "SANITIZACAO", "PESAGEM", "DESTINACAO", "EMISSAO_CERTIFICADO"] },
    ts: { bsonType: "date" },
    responsavel: RESPONSAVEL,
    local: { bsonType: "object" }, dados: { bsonType: "object" },
    hash_anterior: { bsonType: ["string", "null"] },
    hash: { bsonType: "string", pattern: "^[a-f0-9]{64}$" }
  } } }, validationLevel: "strict", validationAction: "error" });

// ----------------------------------- telemetria (series temporais) + dedup
db.createCollection("leituras_telemetria", {
  timeseries: { timeField: "ts", metaField: "meta", granularity: "minutes" },
  expireAfterSeconds: 15552000                                // 180 dias no nivel bruto
});
db.createCollection("controle_ingestao");                     // _id = "<dispositivo_id>:<seq>"

// --------------------------------------------------------- resumos_mensais
db.createCollection("resumos_mensais", { validator: { $jsonSchema: {
  bsonType: "object", required: ["cliente_id", "competencia", "categoria_equipamento", "itens"],
  properties: { competencia: { bsonType: "string", pattern: "^[0-9]{4}-[0-9]{2}$" }, itens: { bsonType: "int" } }
} }, validationLevel: "strict", validationAction: "error" });

// ================================================================= INDICES
// Unicidade e identificacao
db.equipamentos.createIndex({ lote_id: 1, codigo_rastreio: 1 }, { unique: true, name: "uk_lote_codigo" });
db.equipamentos.createIndex({ codigo_rastreio: 1 }, { name: "ix_codigo_rastreio" });
db.clientes.createIndex({ documento: 1 }, { unique: true, name: "uk_documento" });
db.pontos_coleta.createIndex({ codigo: 1 }, { unique: true, name: "uk_ponto" });
db.materiais.createIndex({ codigo: 1, versao: -1 }, { unique: true, name: "uk_material_versao" });
db.coletas.createIndex({ codigo: 1 }, { unique: true, name: "uk_coleta" });
db.lotes.createIndex({ cliente_id: 1, codigo: 1 }, { unique: true, name: "uk_lote_cliente_codigo" });

// Idempotencia e historico da cadeia de custodia
db.eventos_rastreabilidade.createIndex({ equipamento_id: 1, evento_chave: 1 }, { unique: true, name: "uk_evento_idempotente" });
db.eventos_rastreabilidade.createIndex({ equipamento_id: 1, ts: 1 }, { name: "ix_historico_item" });

// Consultas operacionais e analiticas
db.equipamentos.createIndex({ status: 1, etapa_atual: 1, recebido_em: -1 }, { name: "ix_fila_operacao" });
db.equipamentos.createIndex({ "componentes.material_codigo": 1 }, { name: "ix_multikey_material" });
db.triagens.createIndex({ concluida_em: -1, destino: 1 }, { name: "ix_triagem_periodo" });
db.triagens.createIndex({ cliente_id: 1, concluida_em: -1 }, { name: "ix_triagem_cliente" });
db.triagens.createIndex({ ponto_coleta_id: 1, status: 1 }, { name: "ix_triagem_ponto" });
db.lotes.createIndex({ "cliente._id": 1, concluido_em: -1 }, { name: "ix_lotes_cliente" });
db.lotes.createIndex({ status: 1, aberto_em: 1 }, { partialFilterExpression: { status: "EM_ABERTO" }, name: "ix_lotes_abertos" });
db.resumos_mensais.createIndex({ cliente_id: 1, competencia: 1, categoria_equipamento: 1 }, { unique: true, name: "uk_resumo_mensal" });

// Busca textual, geoespacial e telemetria
db.equipamentos.createIndex({ marca: "text", modelo: "text", descricao: "text" }, { default_language: "portuguese", name: "tx_busca_equipamento" });
db.pontos_coleta.createIndex({ localizacao: "2dsphere" }, { name: "geo_pontos" });
db.leituras_telemetria.createIndex({ "meta.ponto_id": 1, ts: -1 }, { name: "ix_leituras_ponto" });
db.controle_ingestao.createIndex({ registrada_em: 1 }, { expireAfterSeconds: 86400, name: "ttl_janela_reenvio" });

print("Colecoes criadas: " + db.getCollectionNames().sort().join(", "));
COLECOES.forEach(c => print("  " + c.padEnd(26) + db[c].getIndexes().map(i => i.name).join(", ")));
