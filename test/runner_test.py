# https://fgimian.github.io/blog/2014/04/10/using-the-python-mock-library-to-fake-regular-functions-during-tests/
# https://stackoverflow.com/questions/4481954/trying-to-mock-datetime-date-today-but-not-working
import unittest
from unittest.mock import patch
from time import sleep as pause
import datetime
import threading
from trader.AlgoManager import *
from trader.Algorithm import *



class SpoofTime(datetime.datetime):

    spoofed_date = datetime.datetime(2019,9,10,8,30)

    @staticmethod
    def increment_date():
        while True:
            pause(0.1)
            SpoofTime.spoofed_date += datetime.timedelta(minutes=1)

    @staticmethod
    def now(timezone=None):
        return SpoofTime.spoofed_date


def sleep_stub(n):
    pause(0.025)



class RunnerTests(unittest.TestCase):

    def setUp(self):
        datetime.datetime = SpoofTime
        time.sleep = sleep_stub
        self.date_thread = threading.Thread(target=SpoofTime.increment_date)
        self.date_thread.start()

    @patch('time.sleep', side_effect=sleep_stub)
    @patch.object(Algorithm, 'run')
    def test_runner(self, runspoof, sleepspoof):
        # Start Runner
        algo = Algorithm(schedule="30 9 * * *")
        manager = Manager()
        manager.add(algo, allocation=1)
        manager.start()
        while datetime.datetime.now().time() < datetime.time(9,30):
            assert not runspoof.called
        pause(1)
        runspoof.assert_called_once()
        manager.stop()
