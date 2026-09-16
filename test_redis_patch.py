import redis
_orig=redis.from_url
def p(url,**kw):
    kw.setdefault('protocol',2)
    return _orig(url,**kw)
redis.from_url=p
print(redis.from_url('redis://localhost:6379/0').ping())
