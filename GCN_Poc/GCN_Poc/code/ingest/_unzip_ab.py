import zipfile
import os

os.makedirs("/ragflow/ingest/_abtest_docs", exist_ok=True)
with zipfile.ZipFile("/tmp/_abtest_docs.zip") as z:
    z.extractall("/ragflow/ingest/_abtest_docs")
print("extracted:", len(os.listdir("/ragflow/ingest/_abtest_docs")))
