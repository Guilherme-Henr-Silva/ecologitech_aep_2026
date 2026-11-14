"""Tabelas de referência imutáveis (valores fictícios usados no MVP acadêmico).

MappingProxyType expõe um dicionário somente leitura: qualquer tentativa de
alteração levanta TypeError, o que reforça a imutabilidade dos parâmetros.
"""

from decimal import Decimal
from types import MappingProxyType

from ecotrack.dominio.enums import Categoria, FaixaBonus
from ecotrack.funcional.tipos import MaterialRef, ParametrosCategoria, TabelaMateriais

VERSAO_TABELA_VIGENTE = 3


def _material(
    codigo: str, nome: str, categoria: str, preco: str, rendimento: float, fator: float
) -> MaterialRef:
    return MaterialRef(codigo, nome, categoria, VERSAO_TABELA_VIGENTE, Decimal(preco), rendimento, fator)


TABELA_MATERIAIS_V3: TabelaMateriais = MappingProxyType(
    {
        m.codigo: m
        for m in (
            _material("MAT-CU", "Cobre", "METAL_NAO_FERROSO", "38.00", 0.92, 3.5),
            _material("MAT-AL", "Aluminio", "METAL_NAO_FERROSO", "7.50", 0.90, 9.0),
            _material("MAT-FE", "Aco e ferro", "METAL_FERROSO", "0.90", 0.95, 1.5),
            _material("MAT-PL", "Plastico ABS", "POLIMERO", "1.20", 0.70, 1.8),
            _material("MAT-PCI", "Placa de circuito impresso", "ELETRONICO", "45.00", 0.85, 2.0),
            _material("MAT-LI", "Bateria de ion-litio", "BATERIA", "12.00", 0.65, 4.0),
            _material("MAT-VD", "Vidro", "VIDRO", "0.15", 0.80, 0.3),
            _material("MAT-LCD", "Tela LCD", "ELETRONICO", "3.00", 0.60, 1.0),
            _material("MAT-CB", "Cabos e fios", "METAL_NAO_FERROSO", "9.00", 0.75, 2.5),
            _material("MAT-CP", "Compressor", "METAL_FERROSO", "2.50", 0.80, 1.2),
        )
    }
)

PARAMETROS_CATEGORIA = MappingProxyType(
    {
        Categoria.COMPUTADOR: ParametrosCategoria(
            Decimal("12.50"), Decimal("1.20"), Decimal("650.00"), Decimal("180.00")
        ),
        Categoria.DISPOSITIVO_MOVEL: ParametrosCategoria(
            Decimal("6.00"), Decimal("1.20"), Decimal("320.00"), Decimal("90.00")
        ),
        Categoria.ELETRODOMESTICO: ParametrosCategoria(
            Decimal("31.00"), Decimal("0.80"), Decimal("400.00"), Decimal("220.00")
        ),
        Categoria.PERIFERICO: ParametrosCategoria(
            Decimal("8.00"), Decimal("1.00"), Decimal("120.00"), Decimal("45.00")
        ),
        Categoria.BATERIA: ParametrosCategoria(Decimal("9.50"), Decimal("2.50")),
        Categoria.OUTRO: ParametrosCategoria(Decimal("10.00"), Decimal("1.00")),
    }
)

# Pesos do programa de bonificação (α, β, γ) e limites das faixas (t1, t2, t3).
PESO_MASSA = 1.0
PESO_CO2 = 2.0
PESO_RECONDICIONADO = 15
LIMITES_FAIXA = (500, 1500, 3000)
DESCONTO_POR_FAIXA = MappingProxyType(
    {
        FaixaBonus.BRONZE: Decimal("0"),
        FaixaBonus.PRATA: Decimal("0.05"),
        FaixaBonus.OURO: Decimal("0.10"),
        FaixaBonus.PLATINA: Decimal("0.15"),
    }
)
