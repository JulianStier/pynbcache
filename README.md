# pynbcache [![PyPI version](https://badge.fury.io/py/pynbcache.svg)](https://badge.fury.io/py/pynbcache) [![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://GitHub.com/Naereen/StrapDown.js/graphs/commit-activity) [![Python 3.8](https://img.shields.io/badge/python-3.8-blue.svg)](https://www.python.org/downloads/release/python-380/) [![Python 3.9](https://img.shields.io/badge/python-3.9-blue.svg)](https://www.python.org/downloads/release/python-390/) [![Python 3.10](https://img.shields.io/badge/python-3.10-blue.svg)](https://www.python.org/downloads/release/python-3100/) ![Tests](https://github.com/JulianStier/pynbcache/workflows/Tests/badge.svg)
A simple caching mechanism for computations in jupyter notebooks.
The cache is stored locally in disk such that you have some overhead in writing it.
Otherwise, better use lru_cache!
This solution is intended for cases where you might expect cells to crash etc.

The main idea is to have your jupyter notebook "analysis.ipynb" shared alongside with cache information, e.g. in a separate directory or via an s3fs share.
Cache information is not intended to be pushed into git, but can still be shared e.g. via a storage interface or if you want to send it via mail etc.
This way you can pre-compute results for presentations.

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
Define your cache base directory:

```python
import numpy as np
from pynbcache import cache

@cache(key="another_computation", base="my_cache/")
def another_computation(param1: int = 100):
    return {ix: np.random.randn(np.random.randint(10, 20)) for ix in range(param1)}

another_computation()
another_computation()
```
With S3FS support:
```python
import numpy as np
from pynbcache import cache

@cache(key="another_computation", s3_access_key="my-access-key", s3_secret_key="my-secret-key", s3_base="/bucket/cache/")
def another_computation(param1: int = 100):
    return {ix: np.random.randn(np.random.randint(10, 20)) for ix in range(param1)}

another_computation()  # executed first time
another_computation()  # should be coming from cache
# Will sync cache to remote s3fs
```

# MinIO Policies
I am using a custom MinIO instance and for a prefixed bucket the pynbcache mechanism uses following policy to store data into */homes/stier/cache/ci-tests/*:
```yaml
{
 "Version": "2012-10-17",
 "Statement": [
  {
   "Effect": "Allow",
   "Action": [
    "s3:ListBucket"
   ],
   "Resource": [
    "arn:aws:s3:::homes"
   ],
   "Condition": {
    "StringLike": {
     "s3:prefix": [
      "",
      "stier/cache/ci-tests/*"
     ]
    }
   }
  },
  {
   "Effect": "Allow",
   "Action": [
    "s3:*"
   ],
   "Resource": [
    "arn:aws:s3:::homes/stier/cache/ci-tests/*"
   ]
  }
 ]
}
```
