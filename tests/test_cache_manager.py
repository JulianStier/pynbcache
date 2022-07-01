import os
import uuid

from unittest.mock import patch

import numpy as np
import pytest

from pynbcache.persistence import CacheManager


@pytest.fixture
def unique_test_id():
    return str(uuid.uuid4())


def test_instantiate(tmpdir):
    path_cache_local = tmpdir.mkdir("cache")
    CacheManager(path_cache_local)


def side_effect_raise_permission_error(path):
    raise PermissionError("Access Denied.")


@patch("s3fs.S3FileSystem.open", side_effect=open)
@patch("s3fs.S3FileSystem.ls", side_effect=os.listdir)
@patch("s3fs.S3FileSystem.exists", side_effect=os.path.exists)
def test_instantiate_with_s3fs_success(
    mock_s3fs_exists, mock_s3fs_ls, mock_s3fs_open, tmpdir, unique_test_id
):
    path_cache_local = tmpdir.mkdir(f"cache-{unique_test_id}")
    path_base_remote = tmpdir.mkdir(f"remote-{unique_test_id}")

    CacheManager(
        path_cache_local,
        access_key="my-key",
        secret_key="my-secret",
        path_remote_base=path_base_remote,
        endpoint="http://localhost/",
    )


@patch("s3fs.S3FileSystem.open", side_effect=open)
@patch("s3fs.S3FileSystem.ls", side_effect=side_effect_raise_permission_error)
def test_instantiate_with_s3fs_without_permission(
    mock_s3fs_ls, mock_s3fs_open, tmpdir, unique_test_id
):
    path_cache_local = tmpdir.mkdir(f"cache-{unique_test_id}")
    path_base_remote = tmpdir.mkdir(f"remote-{unique_test_id}")

    with pytest.warns(UserWarning) as recorded_warnings:
        CacheManager(
            path_cache_local,
            access_key="my-key",
            secret_key="my-secret",
            path_remote_base=path_base_remote,
            endpoint="http://localhost/",
        )

    assert "Access Denied" in str(recorded_warnings[0].message)


@patch("s3fs.S3FileSystem.open", side_effect=open)
@patch("s3fs.S3FileSystem.ls", side_effect=os.listdir)
@patch("s3fs.S3FileSystem.exists", side_effect=os.path.exists)
def test_clear_cache(
    mock_s3fs_exists, mock_s3fs_ls, mock_s3fs_open, tmpdir, unique_test_id
):
    path_cache_local = tmpdir.mkdir(f"cache-{unique_test_id}")
    path_base_remote = tmpdir.mkdir(f"remote-{unique_test_id}")
    result_of_fn_to_cache = np.random.randint(1, 1000)

    def fn_to_cache():
        return result_of_fn_to_cache

    cm = CacheManager(
        path_cache_local,
        access_key="my-key",
        secret_key="my-secret",
        path_remote_base=path_base_remote,
        endpoint="http://localhost/",
    )

    cache_res = cm.get(fn_to_cache.__name__, fn_to_cache)
    assert cache_res == result_of_fn_to_cache

    cm.clear_s3()

    # Remote dir must be empty, so simply can remove it
    assert len(os.listdir(path_base_remote)) == 0
    assert len(os.listdir(path_cache_local)) > 0
