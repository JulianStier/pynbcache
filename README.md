# pynbcache [![PyPI version](https://badge.fury.io/py/pynbcache.svg)](https://badge.fury.io/py/pynbcache) [![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://GitHub.com/Naereen/StrapDown.js/graphs/commit-activity) [![Python 3.8](https://img.shields.io/badge/python-3.8-blue.svg)](https://www.python.org/downloads/release/python-380/) [![Python 3.9](https://img.shields.io/badge/python-3.9-blue.svg)](https://www.python.org/downloads/release/python-390/) [![Python 3.10](https://img.shields.io/badge/python-3.10-blue.svg)](https://www.python.org/downloads/release/python-3100/) ![Tests](https://github.com/JulianStier/pynbcache/workflows/Tests/badge.svg)
A simple caching mechanism for computations in jupyter notebooks.
The cache is stored locally in disk such that you have some overhead in writing it.
Otherwise, better use lru_cache!
This solution is intended for cases where you might expect cells to crash etc.


# Install
- ``pip install pynbcache``
- conda:
```yaml
dependencies:
- pip
- pip:
  - pynbcache
```
- ``poetry install pynbcache``


# Usage
```python
import numpy as np
from pynbcache import cache

@cache(key="complex_computation")
def complex_computation(param1: int = 100):
    return {ix: np.random.randn(np.random.randint(10, 20)) for ix in range(param1)}

complex_computation()  # executed first time
complex_computation()  # should be coming from cache
```
With S3FS support:
```python
import numpy as np
from innvariant.tools import cache

@cache(key="another_computation", s3_access_key="my-access-key", s3_secret_key="my-secret-key", s3_base="/bucket/cache/")
def another_computation(param1: int = 100):
    return {ix: np.random.randn(np.random.randint(10, 20)) for ix in range(param1)}

another_computation()  # executed first time
another_computation()  # should be coming from cache
# Will sync cache to remote s3fs
```
