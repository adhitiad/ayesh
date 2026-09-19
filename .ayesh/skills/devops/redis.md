---
name: redis
description: "Manajemen Redis database/cache. Trigger: /redis"
---

# Redis Database Management

## Koneksi
```bash
redis-cli
redis-cli -h hostname -p 6379
redis-cli -h hostname -p 6379 -a password
redis-cli -n 1
redis-cli ping
redis-cli -c -h hostname -p 6379
```

## Key Operations
```bash
KEYS *                              -- all keys (careful in production)
KEYS user:*                         -- pattern match
SCAN 0 MATCH user:* COUNT 100       -- safe iteration

EXISTS key
TYPE key
TTL key
PTTL key
DEL key
EXPIRE key 3600
PERSIST key
RENAME key newkey
```

## Data Types

### String
```bash
SET key value
SET key value EX 3600
SETNX key value
GET key
MSET key1 val1 key2 val2
MGET key1 key2
INCR counter
INCRBY counter 10
DECR counter
APPEND key " suffix"
STRLEN key
```

### Hash
```bash
HSET user:1 name "John" age 30
HGET user:1 name
HMSET user:1 name "John" age 30
HMGET user:1 name age
HGETALL user:1
HDEL user:1 age
HEXISTS user:1 name
HKEYS user:1
HVALS user:1
HINCRBY user:1 age 1
```

### List
```bash
LPUSH list value
RPUSH list value
LPOP list
RPOP list
LRANGE list 0 -1
LLEN list
LINDEX list 0
LSET list 0 newvalue
LTRIM list 0 99
BLPOP list 10
```

### Set
```bash
SADD set member1 member2
SREM set member1
SMEMBERS set
SISMEMBER set member
SCARD set
SINTER set1 set2
SUNION set1 set2
SDIFF set1 set2
SRANDMEMBER set 3
```

### Sorted Set
```bash
ZADD zset 100 member1 200 member2
ZREM zset member1
ZRANGE zset 0 -1
ZRANGE zset 0 -1 WITHSCORES
ZREVRANGE zset 0 -1
ZRANK zset member
ZSCORE zset member
ZCOUNT zset 100 200
ZINCRBY zset 10 member
```

## Persistence

### RDB
```bash
SAVE
BGSAVE

# redis.conf
save 900 1
save 300 10
save 60 10000
dbfilename dump.rdb
dir /var/lib/redis
```

### AOF
```bash
# redis.conf
appendonly yes
appendfilename "appendonly.aof"
appendfsync everysec
BGREWRITEAOF

auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb
```

## Replication
```bash
REPLICAOF master_host master_port
REPLICAOF NO ONE
INFO replication

# redis.conf
replicaof master_host master_port
masterauth master_password
replica-read-only yes
```

## Cluster
```bash
redis-cli --cluster create \
    node1:6379 node2:6379 node3:6379 \
    node4:6379 node5:6379 node6:6379 \
    --cluster-replicas 1

cluster info
cluster nodes

redis-cli --cluster add-node new_node:6379 existing_node:6379
redis-cli --cluster reshard node:6379
redis-cli --cluster check node:6379
```

## Performance
```bash
INFO
INFO memory
INFO replication
INFO stats
INFO clients

SLOWLOG GET 10
SLOWLOG LEN
SLOWLOG RESET

MEMORY USAGE key
MEMORY DOCTOR

CLIENT LIST
CLIENT KILL ID client_id

redis-cli --bigkeys
redis-cli --memkeys
redis-cli --latency
```

## Common Patterns

### Distributed Lock
```bash
SET lock:resource unique_value NX EX 30
EVAL "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end" 1 lock:resource unique_value
```

### Rate Limiting
```bash
MULTI
ZADD rate_limit:user:1 timestamp timestamp
ZREMRANGEBYSCORE rate_limit:user:1 0 (timestamp-60000)
ZCARD rate_limit:user:1
EXPIRE rate_limit:user:1 60
EXEC
```

### Cache Penetration Protection
```bash
BF.ADD filter key
BF.EXISTS filter key
SET key "" EX 60
```

### Batch Delete
```bash
redis-cli --scan --pattern "prefix:*" | xargs redis-cli DEL
UNLINK key1 key2 key3
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Memory tidak cukup | `INFO memory`, `MEMORY DOCTOR` |
| Koneksi terlalu banyak | `INFO clients`, `CLIENT LIST` |
| Response lambat | `SLOWLOG GET`, cek big keys |
| Master-slave delay | `INFO replication` |
| Cluster error | `CLUSTER INFO`, `CLUSTER NODES` |
