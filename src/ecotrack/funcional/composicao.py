"""Utilitários de alta ordem para compor pipelines."""

from collections.abc import Callable
from functools import reduce
from typing import Any


def compor(*etapas: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """Compõe as etapas da esquerda para a direita: compor(f, g)(x) == g(f(x))."""
    return lambda dados: reduce(lambda acumulado, etapa: etapa(acumulado), etapas, dados)
