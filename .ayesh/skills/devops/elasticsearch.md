---
name: elasticsearch
description: "Manajemen Elasticsearch cluster & search. Trigger: /elasticsearch"
---

# Elasticsearch Cluster Management

## Cluster Status
```bash
curl -X GET "localhost:9200/_cluster/health?pretty"
curl -X GET "localhost:9200/_cluster/state?pretty"
curl -X GET "localhost:9200/_cluster/stats?pretty"
curl -X GET "localhost:9200/_nodes?pretty"
curl -X GET "localhost:9200/_nodes/stats?pretty"
curl -X GET "localhost:9200/_cat/shards?v"
curl -X GET "localhost:9200/_cat/allocation?v"
```

## Cat API
```bash
curl -X GET "localhost:9200/_cat/health?v"
curl -X GET "localhost:9200/_cat/nodes?v"
curl -X GET "localhost:9200/_cat/indices?v"
curl -X GET "localhost:9200/_cat/shards?v"
curl -X GET "localhost:9200/_cat/segments?v"
curl -X GET "localhost:9200/_cat/count?v"
curl -X GET "localhost:9200/_cat/recovery?v"
curl -X GET "localhost:9200/_cat/thread_pool?v"
```

## Index Management
```bash
# Create
curl -X PUT "localhost:9200/my_index" -H 'Content-Type: application/json' -d'
{
  "settings": { "number_of_shards": 3, "number_of_replicas": 1 },
  "mappings": {
    "properties": {
      "title": { "type": "text" },
      "content": { "type": "text" },
      "timestamp": { "type": "date" },
      "status": { "type": "keyword" }
    }
  }
}'

# Delete
curl -X DELETE "localhost:9200/my_index"

# View
curl -X GET "localhost:9200/my_index?pretty"
curl -X GET "localhost:9200/my_index/_mapping?pretty"
curl -X GET "localhost:9200/my_index/_settings?pretty"

# Alias
curl -X POST "localhost:9200/_aliases" -H 'Content-Type: application/json' -d'
{
  "actions": [
    { "add": { "index": "my_index_v2", "alias": "my_index" } },
    { "remove": { "index": "my_index_v1", "alias": "my_index" } }
  ]
}'

# Settings
curl -X PUT "localhost:9200/my_index/_settings" -H 'Content-Type: application/json' -d'
{ "index": { "number_of_replicas": 2 } }'

curl -X POST "localhost:9200/my_index/_close"
curl -X POST "localhost:9200/my_index/_open"
curl -X POST "localhost:9200/my_index/_refresh"
curl -X POST "localhost:9200/my_index/_forcemerge?max_num_segments=1"
```

## Document CRUD
```bash
# Create
curl -X POST "localhost:9200/my_index/_doc" -H 'Content-Type: application/json' -d'
{ "title": "Hello World", "content": "Test", "timestamp": "2024-01-15T10:00:00" }'

curl -X PUT "localhost:9200/my_index/_doc/1" -H 'Content-Type: application/json' -d'
{ "title": "Document 1" }'

# Read
curl -X GET "localhost:9200/my_index/_doc/1?pretty"

# Update
curl -X POST "localhost:9200/my_index/_update/1" -H 'Content-Type: application/json' -d'
{ "doc": { "title": "Updated Title" } }'

# Delete
curl -X DELETE "localhost:9200/my_index/_doc/1"

# Bulk
curl -X POST "localhost:9200/_bulk" -H 'Content-Type: application/json' -d'
{"index":{"_index":"my_index","_id":"1"}}
{"title":"Doc 1"}
{"index":{"_index":"my_index","_id":"2"}}
{"title":"Doc 2"}'
```

## Query DSL
```bash
# Match all
curl -X GET "localhost:9200/my_index/_search?pretty" -H 'Content-Type: application/json' -d'
{ "query": { "match_all": {} } }'

# Full text
curl -X GET "localhost:9200/my_index/_search?pretty" -H 'Content-Type: application/json' -d'
{ "query": { "match": { "content": "search text" } } }'

# Term
curl -X GET "localhost:9200/my_index/_search?pretty" -H 'Content-Type: application/json' -d'
{ "query": { "term": { "status": "published" } } }'

# Range
curl -X GET "localhost:9200/my_index/_search?pretty" -H 'Content-Type: application/json' -d'
{ "query": { "range": { "timestamp": { "gte": "2024-01-01", "lte": "2024-01-31" } } } }'

# Bool
curl -X GET "localhost:9200/my_index/_search?pretty" -H 'Content-Type: application/json' -d'
{
  "query": {
    "bool": {
      "must": [{ "match": { "title": "elasticsearch" } }],
      "filter": [{ "term": { "status": "published" } }],
      "should": [{ "match": { "content": "tutorial" } }],
      "must_not": [{ "term": { "status": "draft" } }]
    }
  }
}'

# Aggregation
curl -X GET "localhost:9200/my_index/_search?pretty" -H 'Content-Type: application/json' -d'
{
  "size": 0,
  "aggs": {
    "status_count": { "terms": { "field": "status" } },
    "avg_score": { "avg": { "field": "score" } }
  }
}'
```

## Snapshot & Restore
```bash
curl -X PUT "localhost:9200/_snapshot/my_backup" -H 'Content-Type: application/json' -d'
{ "type": "fs", "settings": { "location": "/backup/elasticsearch" } }'

curl -X PUT "localhost:9200/_snapshot/my_backup/snapshot_1?wait_for_completion=true"
curl -X GET "localhost:9200/_snapshot/my_backup/_all?pretty"
curl -X POST "localhost:9200/_snapshot/my_backup/snapshot_1/_restore"
curl -X DELETE "localhost:9200/_snapshot/my_backup/snapshot_1"
```

## Reindex
```bash
curl -X POST "localhost:9200/_reindex" -H 'Content-Type: application/json' -d'
{ "source": { "index": "old_index" }, "dest": { "index": "new_index" } }'
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Cluster RED | `_cluster/health`, `_cat/shards` |
| Shard tidak allocated | `_cluster/allocation/explain` |
| Query lambat | `_nodes/hot_threads`, Profile API |
| Disk penuh | `_cat/allocation`, bersihkan index lama |
| Memory tidak cukup | `_nodes/stats`, adjust JVM |
