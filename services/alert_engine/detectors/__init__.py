from detectors.base import BaseAlertDetector, CooldownTracker
from detectors.price_alerts import PriceAlertDetector
from detectors.volume_alerts import VolumeAlertDetector
from detectors.momentum_alerts import MomentumAlertDetector
from detectors.cross_alerts import CrossAlertDetector
from detectors.pullback_alerts import PullbackAlertDetector
from detectors.gap_alerts import GapAlertDetector
from detectors.bidask_alerts import BidAskAlertDetector
from detectors.technical_alerts import TechnicalAlertDetector
from detectors.orb_alerts import ORBAlertDetector
from detectors.consolidation_alerts import ConsolidationAlertDetector
from detectors.vwap_divergence_alerts import VWAPDivergenceAlertDetector
from detectors.checkmark_alerts import CheckMarkAlertDetector
from detectors.geometric_alerts import GeometricAlertDetector
from detectors.candle_alerts import CandleAlertDetector
from detectors.trailing_stop_alerts import TrailingStopAlertDetector
from detectors.fibonacci_alerts import FibonacciAlertDetector
from detectors.linreg_alerts import LinRegAlertDetector
from detectors.thrust_alerts import ThrustAlertDetector
from detectors.sma_cross_alerts import SMACrossAlertDetector
from detectors.macd_alerts import MACDAlertDetector
from detectors.stochastic_alerts import StochasticAlertDetector
from detectors.candle_pattern_alerts import CandlePatternAlertDetector

ALL_DETECTOR_CLASSES = [
    PriceAlertDetector,
    VolumeAlertDetector,
    MomentumAlertDetector,
    CrossAlertDetector,
    PullbackAlertDetector,
    GapAlertDetector,
    BidAskAlertDetector,
    TechnicalAlertDetector,
    ORBAlertDetector,
    ConsolidationAlertDetector,
    VWAPDivergenceAlertDetector,
    CheckMarkAlertDetector,
    GeometricAlertDetector,
    CandleAlertDetector,
    TrailingStopAlertDetector,
    FibonacciAlertDetector,
    LinRegAlertDetector,
    ThrustAlertDetector,
    SMACrossAlertDetector,
    MACDAlertDetector,
    StochasticAlertDetector,
    CandlePatternAlertDetector,
]
