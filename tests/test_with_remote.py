import json
import os
import uuid
import warnings

import numpy as np
import pytest
import s3fs

from pynbcache.cache import cache
from pynbcache.cache import get_cachemanager_for


@pytest.fixture
def unique_test_id():
    return str(uuid.uuid4())


@pytest.fixture
def remote_s3_path(unique_test_id):
    accesskey, secretkey, base, endpoint = prepare_remote_test()
    if accesskey is None:
        yield None, None, None, None
        return

    path_base_remote = os.path.join(base, unique_test_id)

    yield accesskey, secretkey, path_base_remote, endpoint

    s3client = s3fs.S3FileSystem(
        key=accesskey,
        secret=secretkey,
        use_ssl=True,
        client_kwargs={
            "endpoint_url": endpoint,
        },
    )
    for path_remote_file in s3client.ls(path_base_remote):
        s3client.delete(path_remote_file)
    s3client.delete(path_base_remote)


def prepare_remote_test():
    path_config = "config.json"
    if not os.path.exists(path_config):
        warnings.warn("No test configuration file for S3FS found.")
        return None, None, None, None

    with open(path_config, "r") as handle:
        config = json.load(handle)

    if "accesskey" not in config or len(config["accesskey"]) < 1:
        warnings.warn("No valid configuration for S3FS found.")
        return None, None, None, None

    accesskey = config["accesskey"]
    secretkey = config["secretkey"]
    base = config["base"]
    endpoint = config["endpoint"] if "endpoint" in config else None

    return accesskey, secretkey, base, endpoint


def test_remote_cache(tmpdir, unique_test_id):
    accesskey, secretkey, base, endpoint = prepare_remote_test()
    if accesskey is None:
        return

    key_cache = "compute-test_remote_clear_cache"
    path_cache_local = tmpdir.mkdir(f"cache-{unique_test_id}")

    @cache(
        key=key_cache + "a",
        base=path_cache_local,
        s3_base=base,
        s3_access_key=accesskey,
        s3_secret_key=secretkey,
        s3_endpoint=endpoint,
    )
    def my_calc1():
        return np.random.randn(5)

    @cache(
        key=key_cache + "b",
        base=path_cache_local,
        s3_base=base,
        s3_access_key=accesskey,
        s3_secret_key=secretkey,
        s3_endpoint=endpoint,
    )
    def my_calc2(n: int):
        return np.random.randn(n)

    my_calc1()
    my_calc1()
    my_calc2(3)
    my_calc1()
    my_calc2(6)

    cm = get_cachemanager_for(my_calc1)
    cm.clear_local()


# flake8: noqa: F841
def test_remote_clear_cache(tmpdir, unique_test_id, remote_s3_path):
    accesskey, secretkey, path_base_remote, endpoint = remote_s3_path
    if path_base_remote is None:
        return
    key_cache = "compute-test_remote_clear_cache"
    path_cache_local = str(tmpdir.mkdir(f"cache-{unique_test_id}"))

    return  # TODO jjs: temporarily deactivated from here on

    @cache(
        key=key_cache,
        base=path_cache_local,
        s3_base=path_base_remote,
        s3_access_key=accesskey,
        s3_secret_key=secretkey,
        s3_endpoint=endpoint,
    )
    def compute():
        return np.random.randint(1, 100)

    compute()
    cm = get_cachemanager_for(compute)
    cm._sync_to(path_cache_local, cm._s3fs, path_base_remote)

    files_local = os.listdir(path_cache_local)

    assert len(cm._s3fs.ls(path_base_remote)) > 0

    cm.clear_s3()

    assert len(cm._s3fs.ls(path_base_remote)) == 0
