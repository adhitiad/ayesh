---
name: mongodb
description: "Manajemen MongoDB NoSQL database. Trigger: /mongodb"
---

# MongoDB Database Management

## Koneksi
```bash
mongosh
mongosh --port 27017
mongosh "mongodb://hostname:27017"
mongosh "mongodb://user:password@hostname:27017/database"
mongosh "mongodb://host1:27017,host2:27017,host3:27017/database?replicaSet=rs0"
mongosh script.js
mongosh --eval "db.collection.find()"
```

## Database Operations
```javascript
show dbs
use mydb
db.dropDatabase()
db.stats()

show collections
db.createCollection("users")
db.users.drop()
db.users.stats()
```

## CRUD
```javascript
// Insert
db.users.insertOne({ name: "John", age: 30 })
db.users.insertMany([{ name: "Jane" }, { name: "Bob" }])

// Query
db.users.find()
db.users.find({ age: { $gt: 25 } })
db.users.findOne({ name: "John" })
db.users.find().limit(10).skip(20).sort({ age: -1 })

// Update
db.users.updateOne({ name: "John" }, { $set: { age: 31 } })
db.users.updateMany({ age: { $lt: 18 } }, { $set: { status: "minor" } })

// Delete
db.users.deleteOne({ name: "John" })
db.users.deleteMany({ status: "inactive" })
```

## Index Management
```javascript
db.users.getIndexes()
db.users.createIndex({ email: 1 })
db.users.createIndex({ name: 1, age: -1 })
db.users.createIndex({ email: 1 }, { unique: true })
db.users.createIndex({ location: "2dsphere" })
db.users.createIndex({ content: "text" })
db.users.createIndex({ field: 1 }, { background: true })
db.users.dropIndex("email_1")
db.users.dropIndexes()
db.users.find({ email: "test@example.com" }).explain("executionStats")
```

## Aggregation
```javascript
db.orders.aggregate([
    { $match: { status: "completed" } },
    { $group: { _id: "$customer", total: { $sum: "$amount" } } },
    { $sort: { total: -1 } },
    { $limit: 10 }
])

// Operators: $match, $group, $sort, $limit, $skip, $project, $unwind, $lookup

db.orders.aggregate([
    { $lookup: { from: "users", localField: "userId", foreignField: "_id", as: "user" } }
])
```

## Backup & Restore
```bash
mongodump --db mydb --out /backup/
mongodump --uri="mongodb://user:pass@host:27017/mydb" --out /backup/
mongodump --db mydb --collection users --out /backup/
mongodump --db mydb --gzip --archive=/backup/mydb.gz

mongorestore --db mydb /backup/mydb/
mongorestore --uri="mongodb://user:pass@host:27017" /backup/
mongorestore --gzip --archive=/backup/mydb.gz

mongoexport --db mydb --collection users --out users.json
mongoimport --db mydb --collection users --file users.json
```

## Replica Set
```javascript
rs.status()
rs.conf()
rs.initiate({ _id: "rs0", members: [{ _id: 0, host: "mongo1:27017" }, { _id: 1, host: "mongo2:27017" }, { _id: 2, host: "mongo3:27017" }] })
rs.add("mongo4:27017")
rs.addArb("arbiter:27017")
rs.remove("mongo4:27017")
rs.stepDown()
```

## Performance
```javascript
db.serverStatus()
db.currentOp()
db.currentOp({ "active": true, "secs_running": { "$gt": 5 } })
db.killOp(opid)
db.setProfilingLevel(1, { slowms: 100 })
db.system.profile.find().sort({ ts: -1 }).limit(10)
db.serverStatus().connections
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Query lambat | `explain()`, cek index |
| Koneksi terlalu banyak | `db.serverStatus().connections` |
| Memory tidak cukup | Cek WiredTiger cache |
| Replica sync delay | `rs.status()`, cek oplog |
| Disk penuh | `db.stats()`, compact |
