"""Factory Method: cria a subclasse correta de Equipamento a partir do documento JSON."""

from collections.abc import Mapping
from typing import Any, ClassVar

from ecotrack.dominio.entidades import (
    Bateria,
    Componente,
    Computador,
    DispositivoMovel,
    Eletrodomestico,
    Equipamento,
    OutroEquipamento,
    Periferico,
)
from ecotrack.dominio.enums import Categoria, EstadoEquipamento, EtapaCiclo, StatusEquipamento

CAMPOS_DE_ORIGEM = ("coleta_id", "cliente_id", "ponto_coleta_id")


class FabricaEquipamento:
    _registro: ClassVar[dict[Categoria, type[Equipamento]]] = {
        Categoria.COMPUTADOR: Computador,
        Categoria.DISPOSITIVO_MOVEL: DispositivoMovel,
        Categoria.ELETRODOMESTICO: Eletrodomestico,
        Categoria.PERIFERICO: Periferico,
        Categoria.BATERIA: Bateria,
        Categoria.OUTRO: OutroEquipamento,
    }

    @classmethod
    def registrar_tipo(cls, categoria: Categoria, classe: type[Equipamento]) -> None:
        """Nova categoria = nova subclasse registrada; o código existente não muda."""
        cls._registro[categoria] = classe

    @classmethod
    def criar(cls, documento: Mapping[str, Any]) -> Equipamento:
        categoria = Categoria(str(documento["categoria"]).upper())
        classe = cls._registro.get(categoria, OutroEquipamento)
        componentes = tuple(
            Componente(c["tipo"], c["material_codigo"], float(c["massa_kg"]), bool(c.get("funcional", False)))
            for c in documento.get("componentes", ())
        )
        return classe(
            codigo_rastreio=str(documento["codigo_rastreio"]),
            lote_id=str(documento["lote_id"]),
            peso_kg=float(documento["peso_kg"]),
            estado=EstadoEquipamento(documento.get("estado", "NAO_AVALIADO")),
            componentes=componentes,
            atributos=documento.get("atributos", {}),
            marca=documento.get("marca", ""),
            modelo=documento.get("modelo", ""),
            status=StatusEquipamento(documento.get("status", "RECEBIDO")),
            etapa_atual=EtapaCiclo(documento.get("etapa_atual", "COLETA")),
            versao=int(documento.get("versao", 1)),
            origem={campo: str(documento[campo]) for campo in CAMPOS_DE_ORIGEM if documento.get(campo)},
        )
