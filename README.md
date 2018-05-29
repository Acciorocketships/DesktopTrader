# Desktop Trader

### Overview

An Algorithm Manager that allows you to develop, test, and run stock trading algorithms on Robinhood. 

The Python library includes buy/sell functions, historical data, technical indicators, and more useful features to aid in the development quantitative algorithms. Historical data has minute resolution for 15 days, and daily resolution since the year 2000.

The manager includes a GUI (which can be opened from code or the python interactive interpreter) that allows you to track the progress of algorithms in backtests or in real time. 

Trades can be made in code by the algorithms (which can be scheduled to run at any times during the day), or manually from the python interactive interpreter. 

Multiple algorithms can run at a time. Algorithms can be added, removed, or paused, allocations can be changed, and assets can be rebalanced, all from within code or from the python interactive interpreter.

### Install

    git clone git@github.com:Acciorocketships/DesktopTrader.git
    cd DesktopTrader
    pip3 install -e .
    
_**Note:** This will install the package in developer mode, code modifications will be reflected immediately system wide. Do not remove the installation directory. If you want to install in production mode instead, omit the `-e` flag._

### Test

Test coverage is currently limited, but is constantly improving. To run all unit tests: 

    python3 -m unittest discover

This may take some time due to AlphaVantage API tests.
