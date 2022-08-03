from __future__ import annotations

import glob
import hashlib
import marshal
import os
import pickle
import time
import uuid
import warnings

import pandas as pd
import s3fs


PICKLE_BYTES_MAX = 2**31 - 1
PICKLE_PROTOCOL = 5


def pickle_write(data, path_file, pickle_bytes_max: int = PICKLE_BYTES_MAX):
    bytes_data = pickle.dumps(data, protocol=PICKLE_PROTOCOL)
    with open(path_file, "wb") as handle_file:
        for idx in range(0, len(bytes_data), pickle_bytes_max):
            handle_file.write(bytes_data[idx : idx + pickle_bytes_max])


def pickle_load(path_file, pickle_bytes_max: int = PICKLE_BYTES_MAX):
    try:
        with open(path_file, "rb") as h:
            return pickle.load(h)
    except Exception:  # noqa, pylint: disable=broad-except
        bytes_in = bytearray(0)
        input_size = os.path.getsize(path_file)
        with open(path_file, "rb") as handle:
            for _ in range(0, input_size, pickle_bytes_max):
                bytes_in += handle.read(pickle_bytes_max)
        return pickle.loads(bytes_in)


class CacheNotFound(RuntimeError):
    pass


class CodeChanged(RuntimeError):
    pass


class ParametersChanged(RuntimeError):
    pass


class CacheManager(object):
    def __init__(
        self,
        path_base,
        context: str = None,
        access_key: str = None,
        secret_key: str = None,
        path_remote_base: str = None,
        endpoint: str = None,
    ):
        self._path_base = os.path.expanduser(path_base)
        self._name_cache_meta = "cachemeta-0.1.0.hd5"
        self._key_cachemanager = "cachemanager"
        self._context = context if context is not None else "default"

        self._s3_access_key = access_key
        self._s3_secret_key = secret_key
        self._s3_base = (
            path_remote_base if path_remote_base is not None else "/homes/stier/cache/"
        )
        self._s3_endpoint = (
            endpoint if endpoint is not None else "https://share.pads.fim.uni-passau.de"
        )

        self._initialize_s3fs()

    def clear(self, key: str) -> CacheManager:
        self._ensure_base_path()

        cache_meta = self._load_meta()
        path_meta = os.path.join(self._path_base, self._name_cache_meta)
        ixs_hit = cache_meta["key"] == key
        cache_meta.drop(cache_meta[ixs_hit].index)
        cache_meta.to_hdf(path_meta, key=self._key_cachemanager)

        files = glob.glob(self._path_base + os.path.sep + f"cache-{key}-*.pickle")
        for path_file in files:
            try:
                os.remove(path_file)
            except FileNotFoundError:
                print(f"Error while deleting cache file <{path_file}>")

        return self

    def init_clean_meta(self) -> CacheManager:
        self._ensure_base_path()
        path_meta = os.path.join(self._path_base, self._name_cache_meta)
        meta = pd.DataFrame.from_dict(
            {
                "key": [],
                "context": [],
                "time_create_cache": [],
                "used_hash": [],
                "hash_code": [],
                "hash_args": [],
                "hash_kwargs": [],
                "file_cache": [],
            }
        )
        meta.to_hdf(path_meta, key=self._key_cachemanager)

        return self

    def get_results(self, key: str) -> list:
        cache_meta = self._load_meta()

        files_cache = cache_meta[cache_meta["key"] == key].sort_values(
            "time_create_cache", ascending=False
        )["file_cache"]
        return [
            pickle_load(os.path.join(self._path_base, file_cache))
            for file_cache in files_cache
        ]

    def get_hashes(self, key: str) -> pd.DataFrame:
        cache_meta = self._load_meta()

        return cache_meta[cache_meta["key"] == key].sort_values(
            "time_create_cache", ascending=False
        )[["hash_code", "hash_args", "hash_kwargs"]]

    def clear_local(self) -> CacheManager:
        self._ensure_base_path()
        files = glob.glob(self._path_base + os.path.sep + f"cache-{self._context}*")
        for path_file in files:
            try:
                os.remove(path_file)
            except FileNotFoundError:
                print(f"Error while deleting cache file <{path_file}>")

        if len(os.listdir(self._path_base)) == 0:
            os.removedirs(self._path_base)

        return self

    def clear_all(self) -> CacheManager:
        self.clear_local()
        self.clear_s3()
        return self

    def _add_meta(self, key, hash_code, hash_args, hash_kwargs, name_cache):
        meta = pd.DataFrame.from_dict(
            {
                "key": [key],
                "context": [self._context],
                "time_create_cache": [time.time()],
                "used_hash": ["sha256"],
                "hash_code": [hash_code],
                "hash_args": [hash_args],
                "hash_kwargs": [hash_kwargs],
                "file_cache": [name_cache],
            }
        )
        all_meta = self._load_meta()
        new_meta = pd.concat([all_meta, meta], ignore_index=True)
        path_meta = os.path.join(self._path_base, self._name_cache_meta)
        new_meta.to_hdf(path_meta, key=self._key_cachemanager)

    def contains(self, key: str) -> bool:
        cache_meta = self._load_meta()
        return any(cache_meta["key"] == key)

    def get(
        self,
        key: str,
        func: callable,
        args: list = None,
        kwargs: dict = None,
        force_calc: bool = False,
    ):
        if force_calc:
            res = func(
                *(args if args is not None else []),
                **(kwargs if kwargs is not None else {}),
            )
            return self.store(res, key, func, args, kwargs)

        try:
            return self.hit(key, func, args, kwargs)
        except (CacheNotFound, CodeChanged, ParametersChanged):
            res = func(
                *(args if args is not None else []),
                **(kwargs if kwargs is not None else {}),
            )
            return self.store(res, key, func, args, kwargs)

    def hit(self, key: str, func: callable, args: list = None, kwargs: dict = None):
        cache_meta = self._load_meta()

        if not any(cache_meta["key"] == key):
            raise CacheNotFound(f"No cache exists for key <{key}>.")

        hash_code_req = hashlib.sha256(marshal.dumps(func.__code__)).hexdigest()
        if not any(
            (cache_meta["key"] == key) & (cache_meta["hash_code"] == hash_code_req)
        ):
            raise CodeChanged(
                f"Code signature for function <{func.__name__}> and key <{key}> changed."
            )

        hash_args_req = hashlib.sha256(marshal.dumps(args)).hexdigest()
        hash_kwargs_req = hashlib.sha256(marshal.dumps(kwargs)).hexdigest()
        ixs_hit = (
            (cache_meta["key"] == key)
            & (cache_meta["hash_code"] == hash_code_req)
            & (cache_meta["hash_args"] == hash_args_req)
            & (cache_meta["hash_kwargs"] == hash_kwargs_req)
        )
        if not any(ixs_hit):
            raise ParametersChanged(
                f"Parameters for calling <{func.__name__}> with key <{key}> changed."
            )

        file_cache = (
            cache_meta[ixs_hit]
            .sort_values("time_create_cache", ascending=False)["file_cache"]
            .values[0]
        )
        path_cache = os.path.join(self._path_base, file_cache)
        return pickle_load(path_cache)

    def hashes(self, func: callable, args: list = None, kwargs: dict = None):
        hash_code = hashlib.sha256(marshal.dumps(func.__code__)).hexdigest()
        hash_args = hashlib.sha256(marshal.dumps(args)).hexdigest()
        hash_kwargs = hashlib.sha256(marshal.dumps(kwargs)).hexdigest()
        return hash_code, hash_args, hash_kwargs

    def store(
        self, result, key: str, func: callable, args: list = None, kwargs: dict = None
    ):
        name_cache = f"cache-{self._context}-{key}-{str(uuid.uuid4())}.pickle"
        hash_code, hash_args, hash_kwargs = self.hashes(func, args, kwargs)

        path_cache = os.path.join(self._path_base, name_cache)
        assert not os.path.exists(
            path_cache
        ), "Cache file to store result in already exists"
        pickle_write(result, path_cache)
        assert os.path.exists(path_cache), "Could not write cache file"

        self._add_meta(key, hash_code, hash_args, hash_kwargs, name_cache)

        return result

    def sync_s3(self):
        if self._s3_access_key is not None and os.path.exists(self._path_base):
            try:
                self._sync_to(self._path_base, self._s3fs, self._s3_base)

                try:
                    self._sync_from(self._s3fs, self._s3_base, self._path_base)
                except PermissionError as e:
                    warnings.warn(
                        f"You seem to have not access to the defined s3 <{self._s3_endpoint}>: {str(e)}"
                    )
                except OSError as e:
                    warnings.warn(
                        f"Connection issues with <{self._s3_endpoint}> when syncing cache from S3: {str(e)}"
                    )
            except PermissionError as e:
                warnings.warn(
                    f"You seem to have not access to sync to the defined s3 <{self._s3_endpoint}>: {str(e)}"
                )
            except OSError as e:
                warnings.warn(
                    f"Connection issues with <{self._s3_endpoint}> when syncing cache to S3: {str(e)}"
                )

    def clear_s3(self):
        if self._s3_access_key is not None:
            assert (
                self._s3_base is not None
                and self._s3_base != ""
                and os.path.abspath(self._s3_base) != "/"
            )

        for path_remote_file in self._s3fs.ls(self._s3_base):
            if f"cache-{self._context}" not in path_remote_file:
                continue
            self._s3fs.delete(path_remote_file)

    def _ensure_base_path(self):
        if not os.path.exists(self._path_base):
            try:
                os.makedirs(self._path_base)
            except Exception:
                warnings.warn(
                    f"Could not create base path '{self._path_base}' for cache manager."
                )

    def _load_meta(self) -> pd.DataFrame:
        self._ensure_base_path()
        path_meta = os.path.join(self._path_base, self._name_cache_meta)
        if not os.path.exists(path_meta):
            self.init_clean_meta()
        return pd.read_hdf(path_meta, key=self._key_cachemanager)

    def __del__(self):
        self.sync_s3()

    def _initialize_s3fs(self):
        self._s3fs = None
        if self._s3_access_key is not None:
            self._ensure_base_path()

            self._s3fs = s3fs.S3FileSystem(
                key=self._s3_access_key,
                secret=self._s3_secret_key,
                use_ssl=True,
                client_kwargs={
                    "endpoint_url": self._s3_endpoint,
                },
            )

            try:
                self._sync_from(self._s3fs, self._s3_base, self._path_base)
            except OSError as e:
                warnings.warn(
                    f"Connection issues with <{self._s3_endpoint}> when trying to sync cache data from S3: {str(e)}"
                )

    def _sync_to(self, path_base, s3fs: s3fs.S3FileSystem, path_remote_base):
        assert s3fs is not None

        if not os.path.isdir(path_base):
            raise ValueError(f"Path {path_base} not found.")

        files = glob.glob(path_base + os.path.sep + f"cache-{self._context}*.pickle")
        for path_local in files:
            if not os.path.isfile(path_local):
                continue

            path_remote = os.path.join(
                path_remote_base, path_local.replace(path_base, "")
            )
            if s3fs.exists(path_remote):
                continue

            s3fs.upload(path_local, path_remote)

        path_local_meta = os.path.join(path_base, self._name_cache_meta)
        if not os.path.exists(path_local_meta):
            return

        path_remote_meta = os.path.join(path_remote_base, self._name_cache_meta)
        if s3fs.exists(path_remote_meta):
            path_tmp = f".meta-{str(uuid.uuid4())}.hd5"
            assert not os.path.exists(path_tmp)
            s3fs.download(path_remote_meta, path_tmp)
            meta_remote = pd.read_hdf(path_tmp, key=self._key_cachemanager)
            meta_local = self._load_meta()
            # meta_new = pd.concat([meta_local, meta_remote])
            meta_new = pd.concat(
                [meta_local, meta_remote], ignore_index=True
            ).drop_duplicates(
                subset=[
                    "key",
                    "time_create_cache",
                    "hash_code",
                    "hash_args",
                    "hash_kwargs",
                ]
            )
            meta_new.to_hdf(path_tmp, key=self._key_cachemanager)
            s3fs.upload(path_tmp, path_remote_meta)
            os.remove(path_tmp)
        else:
            s3fs.upload(path_local_meta, path_remote_meta)

    def _sync_from(self, s3fs: s3fs.S3FileSystem, path_remote_base, path_base):
        assert s3fs is not None

        if not os.path.isdir(path_base):
            raise ValueError(f"Path {path_base} not found.")

        for name_remote_file in s3fs.ls(path_remote_base):
            if not name_remote_file.startswith(
                "cache-"
            ) or not name_remote_file.endswith(".pickle"):
                continue

            path_local = os.path.join(path_base, name_remote_file)
            if os.path.exists(path_local):
                continue

            path_remote = os.path.join(path_remote_base, name_remote_file)
            s3fs.download(path_remote, path_local)

        path_remote_meta = os.path.join(path_remote_base, self._name_cache_meta)
        if not s3fs.exists(path_remote_meta):
            return

        path_tmp = f".meta-{str(uuid.uuid4())}.hd5"
        assert not os.path.exists(path_tmp)
        s3fs.download(path_remote_meta, path_tmp)
        meta_remote = pd.read_hdf(path_remote_meta, key=self._key_cachemanager)
        meta_local = self._load_meta()
        # meta_new = pd.concat([meta_local, meta_remote])
        meta_new = pd.concat(
            [meta_local, meta_remote], ignore_index=True
        ).drop_duplicates(
            subset=["key", "time_create_cache", "hash_code", "hash_args", "hash_kwargs"]
        )
        os.remove(path_tmp)

        path_local_meta = os.path.join(path_base, self._name_cache_meta)
        meta_new.to_hdf(path_local_meta, key=self._key_cachemanager)
