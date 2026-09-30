"""查 RAGFlow KB 2f84 的文档时间线：run 分布 + 按小时分桶 + 头尾样本。"""
import pymysql

KB = "2f84a97aab4811f1a5be33e6206585a1"
conn = pymysql.connect(host="mysql", port=3306, user="root",
                       password="infini_rag_flow", database="rag_flow",
                       charset="utf8mb4")
cur = conn.cursor()

# 1. run 状态分布
cur.execute("SELECT run, COUNT(*) FROM document WHERE kb_id=%s GROUP BY run", (KB,))
print("run distribution:")
for row in cur.fetchall():
    print(f"  run={row[0]} : {row[1]} docs")

# 2. 按创建时间分桶（每小时）
sql = ("SELECT DATE_FORMAT(FROM_UNIXTIME(create_time/1000), '%%Y-%%m-%%d %%H:00') as hour, "
       "COUNT(*) FROM document WHERE kb_id=%s GROUP BY hour ORDER BY hour")
cur.execute(sql, (KB,))
print("\nby hour (when written):")
for row in cur.fetchall():
    print(f"  {row[0]}  {row[1]} docs")

# 3. 头 5 条
cur.execute(("SELECT name, run, progress, FROM_UNIXTIME(create_time/1000) "
             "FROM document WHERE kb_id=%s ORDER BY create_time LIMIT 5"), (KB,))
print("\nfirst 5 (earliest):")
for row in cur.fetchall():
    print(f"  {row[3]}  run={row[1]} prog={row[2]}  {row[0][:60]}")

# 4. 末 5 条
cur.execute(("SELECT name, run, progress, FROM_UNIXTIME(create_time/1000) "
             "FROM document WHERE kb_id=%s ORDER BY create_time DESC LIMIT 5"), (KB,))
print("\nlast 5 (latest):")
for row in cur.fetchall():
    print(f"  {row[3]}  run={row[1]} prog={row[2]}  {row[0][:60]}")

# 5. progress 分布（验证是否都 progress=1）
cur.execute("SELECT progress, COUNT(*) FROM document WHERE kb_id=%s GROUP BY progress", (KB,))
print("\nprogress distribution:")
for row in cur.fetchall():
    print(f"  progress={row[0]} : {row[1]} docs")

conn.close()
