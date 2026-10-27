# SPDX-License-Identifier: GPL-2.0-or-later


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: builds or runs against real game data (minutes)")
