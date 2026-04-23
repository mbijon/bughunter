"""Tests for src/utils.py. These tests actually pass."""

import pytest

from src.utils import chunks, clamp, is_non_empty


def test_clamp_within_range():
    assert clamp(5, 0, 10) == 5


def test_clamp_below_range():
    assert clamp(-3, 0, 10) == 0


def test_clamp_above_range():
    assert clamp(42, 0, 10) == 10


def test_clamp_invalid_range():
    with pytest.raises(ValueError):
        clamp(5, 10, 0)


def test_chunks_even():
    assert chunks([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]


def test_chunks_uneven():
    assert chunks([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_chunks_empty():
    assert chunks([], 3) == []


def test_chunks_invalid_size():
    with pytest.raises(ValueError):
        chunks([1, 2, 3], 0)


def test_is_non_empty_none():
    assert is_non_empty(None) is False


def test_is_non_empty_empty_string():
    assert is_non_empty("") is False


def test_is_non_empty_string():
    assert is_non_empty("hello") is True


def test_is_non_empty_list():
    assert is_non_empty([1]) is True
