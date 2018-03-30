import unittest
from trader.Algorithm import Algorithm

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
