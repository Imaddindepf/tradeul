"""
Column Operations for DSL
Provides a clean interface for filtering operations
"""

from typing import Any, List, Optional, Union
from enum import Enum
from dataclasses import dataclass


class Operator(str, Enum):
    """Operadores soportados"""
    EQ = "eq"           # ==
    NE = "ne"           # !=
    GT = "gt"           # >
    GE = "ge"           # >=
    LT = "lt"           # <
    LE = "le"           # <=
    BETWEEN = "between"
    ISIN = "isin"
    CONTAINS = "contains"
    IS_NULL = "is_null"
    NOT_NULL = "not_null"


@dataclass
class Condition:
    """Representa una condición de filtro"""
    column: str
    operator: Operator
    value: Any = None
    value2: Any = None  # Para BETWEEN
    
    def evaluate(self, row: dict) -> bool:
        """Evalua la condicion contra una fila de datos"""
        col_value = row.get(self.column)
        
        if self.operator == Operator.IS_NULL:
            return col_value is None
        
        if self.operator == Operator.NOT_NULL:
            return col_value is not None
        
        # Si el valor de la columna es None y no estamos chequeando null
        if col_value is None:
            return False
        
        # Si el valor es un dict o lista, no se puede comparar numericamente
        if isinstance(col_value, (dict, list)):
            if self.operator in (Operator.EQ, Operator.NE):
                return col_value == self.value if self.operator == Operator.EQ else col_value != self.value
            return False  # No se puede comparar dict/list con operadores numericos
        
        try:
            if self.operator == Operator.EQ:
                return col_value == self.value
            elif self.operator == Operator.NE:
                return col_value != self.value
            elif self.operator == Operator.GT:
                return col_value > self.value
            elif self.operator == Operator.GE:
                return col_value >= self.value
            elif self.operator == Operator.LT:
                return col_value < self.value
            elif self.operator == Operator.LE:
                return col_value <= self.value
            elif self.operator == Operator.BETWEEN:
                return self.value <= col_value <= self.value2
            elif self.operator == Operator.ISIN:
                return col_value in self.value
            elif self.operator == Operator.CONTAINS:
                return self.value.lower() in str(col_value).lower()
        except TypeError:
            # Tipos incompatibles para comparacion
            return False
        
        return False


class Column:
    """
    Representa una columna para operaciones de filtro.
    
    Usage:
        col('price') >= 10
        col('sector').isin(['Technology', 'Healthcare'])
        col('change_percent').between(-5, 5)
    """
    
    def __init__(self, name: str):
        self.name = name
    
    def __eq__(self, other: Any) -> Condition:
        return Condition(self.name, Operator.EQ, other)
    
    def __ne__(self, other: Any) -> Condition:
        return Condition(self.name, Operator.NE, other)
    
    def __gt__(self, other: Any) -> Condition:
        return Condition(self.name, Operator.GT, other)
    
    def __ge__(self, other: Any) -> Condition:
        return Condition(self.name, Operator.GE, other)
    
    def __lt__(self, other: Any) -> Condition:
        return Condition(self.name, Operator.LT, other)
    
    def __le__(self, other: Any) -> Condition:
        return Condition(self.name, Operator.LE, other)
    
    def between(self, low: Any, high: Any) -> Condition:
        """Valor entre low y high (inclusive)"""
        return Condition(self.name, Operator.BETWEEN, low, high)
    
    def isin(self, values: List[Any]) -> Condition:
        """Valor está en la lista"""
        return Condition(self.name, Operator.ISIN, values)
    
    def contains(self, substring: str) -> Condition:
        """Columna string contiene substring (case insensitive)"""
        return Condition(self.name, Operator.CONTAINS, substring)
    
    def is_null(self) -> Condition:
        """Valor es None"""
        return Condition(self.name, Operator.IS_NULL)
    
    def not_null(self) -> Condition:
        """Valor no es None"""
        return Condition(self.name, Operator.NOT_NULL)


def col(name: str) -> Column:
    """
    Función helper para crear una Column.
    
    Usage:
        col('price') >= 10
        col('change_percent') <= -3
    """
    return Column(name)

