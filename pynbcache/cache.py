import hashlib
import json
import marshal
import os
import shutil
import time

import pandas as pd

from pynbcache.persistence import CacheManager
from pynbcache.persistence import CacheNotFound
from pynbcache.persistence import CodeChanged
from pynbcache.persistence import ParametersChanged


__PYNBCACHE_DEFAULT_PATH_BASE = "cache/"
__PYNBCACHE_DEFAULT_S3_ACCESS_KEY = None
__PYNBCACHE_DEFAULT_S3_SECRET_KEY = None
__PYNBCACHE_DEFAULT_S3_BASE = None
__PYNBCACHE_DEFAULT_S3_ENDPOINT = None


def configure(
    s3_access_key: str = None,
    s3_secret_key: str = None,
    s3_base: str = None,
    s3_endpoint: str = None,
):
    global __PYNBCACHE_DEFAULT_S3_ACCESS_KEY
    global __PYNBCACHE_DEFAULT_S3_SECRET_KEY
    global __PYNBCACHE_DEFAULT_S3_BASE
    global __PYNBCACHE_DEFAULT_S3_ENDPOINT
    __PYNBCACHE_DEFAULT_S3_ACCESS_KEY = s3_access_key
    __PYNBCACHE_DEFAULT_S3_SECRET_KEY = s3_secret_key
    __PYNBCACHE_DEFAULT_S3_BASE = s3_base
    __PYNBCACHE_DEFAULT_S3_ENDPOINT = s3_endpoint


def cache(key: str, *args, **kwargs):
    path_base_cache = (
        str(kwargs["base"]) if "base" in kwargs else __PYNBCACHE_DEFAULT_PATH_BASE
    )
    s3fs_access_key = (
        str(kwargs["s3_access_key"])
        if "s3_access_key" in kwargs
        else __PYNBCACHE_DEFAULT_S3_ACCESS_KEY
    )
    s3fs_secret_key = (
        str(kwargs["s3_secret_key"])
        if "s3_secret_key" in kwargs
        else __PYNBCACHE_DEFAULT_S3_SECRET_KEY
    )
    s3fs_base = (
        str(kwargs["s3_base"]) if "s3_base" in kwargs else __PYNBCACHE_DEFAULT_S3_BASE
    )
    s3fs_endpoint = (
        str(kwargs["s3_endpoint"])
        if "s3_endpoint" in kwargs
        else __PYNBCACHE_DEFAULT_S3_ENDPOINT
    )

    def cache_decorator(func):
        cm = CacheManager(
            path_base=path_base_cache,
            access_key=s3fs_access_key,
            secret_key=s3fs_secret_key,
            path_remote_base=s3fs_base,
            endpoint=s3fs_endpoint,
        )

        def wrapper(*args, **kwargs):
            force_calc = bool(kwargs["force_calc"]) if "force_calc" in kwargs else False
            clear_cache = (
                bool(kwargs["clear_cache"]) if "clear_cache" in kwargs else False
            )

            if force_calc:
                res = func(*args, **kwargs)
                cm.store(res, key, func, args, kwargs)
            else:
                try:
                    res = cm.hit(key, func, args, kwargs)
                except (CacheNotFound, CodeChanged, ParametersChanged):
                    res = func(*args, **kwargs)
                    cm.store(res, key, func, args, kwargs)

            if clear_cache:
                cm.clear(key)
            return res

        wrapper._cachemanager = cm
        return wrapper

    return cache_decorator


def get_cachemanager_for(func) -> CacheManager:
    if not hasattr(func, "_cachemanager"):
        raise ValueError(
            f"Function {func} was not decorated by cache() to obtain its cachemanager."
        )
    return func._cachemanager


def calculate_or_cache(
    fn_calculate,
    force_calc=False,
    clear_cache=False,
    path_base_cache="~/.cache/analysisnotebook/",
):
    assert callable(fn_calculate)
    name_calculation = fn_calculate.__name__
    name_cache_meta = "cache-meta.json"
    bytes_calculation = marshal.dumps(fn_calculate.__code__)
    m = hashlib.sha256()
    m.update(bytes_calculation)
    code_calculation = m.hexdigest()

    res = None

    path_base_cache = os.path.join(
        os.path.expanduser(path_base_cache), name_calculation
    )
    path_meta = os.path.join(path_base_cache, name_cache_meta)
    if not os.path.exists(path_base_cache):
        os.makedirs(path_base_cache)
    elif not force_calc and os.path.exists(path_meta):
        meta_full = None
        with open(path_meta) as handle_meta:
            meta_full = json.load(handle_meta)

        meta = None
        if "caches" in meta_full:
            for cache in meta_full["caches"]:
                if cache["code_calculation"] == code_calculation:
                    meta = cache

        if meta is not None and "format" in meta and "keys" in meta:
            print(f"Cache hit for {name_calculation}")
            path_hd5 = os.path.join(path_base_cache, meta["path"])
            if meta["format"] == "single":
                res = pd.read_hdf(path_hd5, key=meta["keys"])
            elif meta["format"] == "list":
                res = [pd.read_hdf(path_hd5, key=k) for k in meta["keys"]]
            elif meta["format"] == "dict":
                res = {
                    meta["keys"][k_hash]: pd.read_hdf(path_hd5, key=k_hash)
                    for k_hash in meta["keys"]
                }

    if clear_cache:
        shutil.rmtree(path_base_cache)

    if res is None:
        # (Re-)calculate result
        time_calc_start = time.time()
        res = fn_calculate()
        time_calc_end = time.time()

        if clear_cache:
            return res

        format_res = (
            "single"
            if isinstance(res, pd.DataFrame)
            else "list"
            if type(res) == list
            else "dict"
            if type(res) == dict
            else "unknown"
        )

        # "main" if format_res == "single" else [i for i in enumerate(res)] if format_res == "list" else [k for k in res.keys()] if format_res == "dict" else None
        name_hd5 = "result_cache.hd5"
        path_hd5 = os.path.join(path_base_cache, name_hd5)
        res_keys = None
        if format_res == "single":
            res_keys = "main"
            res.to_hdf(path_hd5, key=res_keys)
        elif format_res == "list":
            res_keys = [i for i in enumerate(res)]
            for k, df in zip(res_keys, res):
                df.to_hdf(path_hd5, key=k)
        elif format_res == "dict":
            res_keys = {
                "key" + hashlib.sha256(str.encode(k)).hexdigest(): k for k in res.keys()
            }
            for k_hash in res_keys:
                k = res_keys[k_hash]
                res[k].to_hdf(path_hd5, key=k_hash)

        # Store cache
        meta_info = {
            "version": 1.0,
            "code_calculation": code_calculation,
            "timings": {
                "cache_creation": time.time(),
                "calc_start": time_calc_start,
                "calc_end": time_calc_end,
            },
            "format": format_res,
            "path": name_hd5,
            "keys": res_keys,
        }

        meta = {}
        if os.path.exists(path_meta):
            with open(path_meta) as handle_meta:
                meta = json.load(handle_meta)
        if "caches" not in meta:
            meta["caches"] = []
        meta["caches"].append(meta_info)
        with open(path_meta, "w+") as handle_write_meta:
            json.dump(meta, handle_write_meta)

    return res
