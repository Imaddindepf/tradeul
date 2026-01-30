"""Test RETE Engine"""
import sys
sys.path.insert(0, '/opt/tradeul/services/scanner')

from rete.models import Condition, Operator, ScanRule, RuleOwnerType
from rete.evaluator import evaluate_condition, evaluate_ticker, get_matching_rules
from rete.compiler import compile_network
from rete.system_rules import get_system_rules
from dataclasses import dataclass


@dataclass
class MockTicker:
    symbol: str = 'TEST'
    price: float = 5.0
    gap_percent: float = 8.0
    change_percent: float = 6.0
    volume_today: int = 1000000
    rvol: float = 3.0
    chg_5min: float = 2.0
    price_from_intraday_high: float = -1.0
    price_vs_vwap: float = 0.5
    trades_z_score: float = 1.5


def test_conditions():
    print("Testing conditions...")
    assert evaluate_condition(5.0, Condition('x', Operator.GT, 3)) == True
    assert evaluate_condition(2.0, Condition('x', Operator.GT, 3)) == False
    assert evaluate_condition(5.0, Condition('x', Operator.BETWEEN, [1, 10])) == True
    assert evaluate_condition('Tech', Condition('x', Operator.IN, ['Tech', 'Health'])) == True
    assert evaluate_condition(None, Condition('x', Operator.IS_NONE, None)) == True
    print("  OK")


def test_compile():
    print("Testing compile...")
    rules = get_system_rules()
    network = compile_network(rules)
    stats = network.get_stats()
    assert stats['total_rules'] == 8
    assert stats['alpha_nodes'] > 0
    print(f"  OK: {stats}")


def test_evaluate():
    print("Testing evaluate...")
    rules = get_system_rules()
    network = compile_network(rules)
    
    ticker = MockTicker()
    matches = get_matching_rules(ticker, network)
    
    print(f"  Ticker matches: {sorted(matches)}")
    assert 'category:gappers_up' in matches  # gap 8% > 2%
    assert 'category:winners' in matches     # change 6% > 5%
    assert 'category:high_volume' in matches # rvol 3 > 2
    print("  OK")


if __name__ == '__main__':
    test_conditions()
    test_compile()
    test_evaluate()
    print("\nAll tests passed!")
