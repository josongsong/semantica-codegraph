"""Sample test to verify test monitoring system"""

import time

import pytest


def test_fast():
    """Fast test (< 0.5s)"""
    assert 1 + 1 == 2


def test_medium():
    """Medium test (~2s)"""
    time.sleep(2.2)
    assert True


@pytest.mark.slow
def test_slow():
    """Slow test (>5s)"""
    time.sleep(5.5)
    assert True


def test_instant():
    """Instant test"""
    result = sum([1, 2, 3, 4, 5])
    assert result == 15
