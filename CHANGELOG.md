# Changelog for pynbcache

## 0.1
- added a decorator @cache to store results locally
- added support for s3fs when using @cache to share larger computation caches when sharing notebooks
- clearing remote and local cache via clear_local() and clear_s3()
- os and permission error handling for s3fs
- changed default path to non-visible folder "cache"
- added an optional context string for cache management
