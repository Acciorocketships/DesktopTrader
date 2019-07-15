"""
Tests for all algorithm functions that do NOT interact directly 
with Robinhood. Nothing in this file should use real money!
"""

import unittest
from trader.Algorithm import Algorithm, Backtester, backtester
from datetime import timedelta

class AlgorithmTest(unittest.TestCase):
    def setUp(self):
        self.a = Algorithm()

class DataRetrievalTest(AlgorithmTest):
    def testHistory(self):
        ans = self.a.history("SPY")
        self.assertIsNotNone(ans)

    def testMacd(self):
        ans = self.a.macd("SPY")
        self.assertIsNotNone(ans)

    def testBollinger(self):
        ans = self.a.bollinger("SPY")
        self.assertIsNotNone(ans)

    def testRsi(self):
        ans = self.a.rsi("SPY")
        self.assertIsNotNone(ans)

    def testSma(self):
        ans = self.a.sma("SPY")
        self.assertIsNotNone(ans)

    def testEma(self):
        ans = self.a.ema("SPY")
        self.assertIsNotNone(ans)

    def testStoch(self):
        ans = self.a.stoch("SPY")
        self.assertIsNotNone(ans)

    def testPercentChange(self):
        ans = self.a.percentchange("SPY")
        self.assertIsNotNone(ans)

class ExampleOrderAlgo(Algorithm):
    def initialize(self):
        self.benchmark = "SPY"
        self.cash = 1000

    def run(self):
        self.order("SPY", 1)

class BacktestTest(unittest.TestCase):
    def setUp(self):
        self.a = Algorithm()
        self.b = backtester(self.a)

class BacktestConversionTest(BacktestTest):
    def testBacktestInstance(self):
        self.assertIsInstance(self.b, Backtester)

class BacktestOrdersTest(unittest.TestCase):
    def testOrder(self):
        a = ExampleOrderAlgo(times=['every day'])
        b = backtester(a)
        b.backtest(startdate=(1, 1, 2016), enddate=(28, 2, 2016))
        self.assertTrue(b.cash < 1000)
        self.assertTrue(self.stocks["SPY"] > 0)

