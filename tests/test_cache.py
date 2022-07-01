import time
import uuid

import numpy as np
import pytest

from pynbcache.cache import cache
from pynbcache.cache import get_cachemanager_for
from pynbcache.persistence import CacheManager


@pytest.fixture
def unique_test_id():
    return str(uuid.uuid4())


def test_basic_cache_success(tmpdir):
    key_cache = "compute-" + test_basic_cache_success.__name__
    path_local_cache = tmpdir.mkdir("cache")
    result_compute = np.random.randint(1, 1000)

    @cache(key=key_cache, base=path_local_cache)
    def compute():
        return result_compute

    assert compute() == result_compute


def test_assume_speed_gain(tmpdir, unique_test_id):
    key_cache = "compute-" + test_basic_cache_success.__name__
    path_local_cache = tmpdir.mkdir(f"cache-{unique_test_id}")

    @cache(key=key_cache + "a", base=path_local_cache)
    def my_calc1():
        return np.random.randn(5)

    @cache(key=key_cache + "b", base=path_local_cache)
    def my_calc2(n: int):
        return np.random.randn(n)

    my_calc1()
    my_calc1()
    my_calc2(3)
    my_calc1()
    my_calc2(6)
    my_calc2(3)

    # Create initial cache
    start_first = time.time()
    for _ in range(100):
        my_calc2(_)
    end_first = time.time()

    # Access a second time
    start_second = time.time()
    for _ in range(100):
        my_calc2(_)
    end_second = time.time()

    assert end_first - start_first > end_second - start_second

    cm = get_cachemanager_for(my_calc1)
    cm.clear_local()


def test_clear(tmpdir, unique_test_id):
    path_local_cache = tmpdir.mkdir(f"cache-{unique_test_id}")

    cm = CacheManager(path_local_cache)
    cm.clear_local()


def test_get_cm(tmpdir, unique_test_id):
    key_cache = "compute-" + test_get_cm.__name__
    path_local_cache = tmpdir.mkdir(f"cache-{unique_test_id}")

    @cache(key=key_cache, base=path_local_cache)
    def my_calc1():
        return np.random.randn(5)

    cm = get_cachemanager_for(my_calc1)
    assert cm is not None
