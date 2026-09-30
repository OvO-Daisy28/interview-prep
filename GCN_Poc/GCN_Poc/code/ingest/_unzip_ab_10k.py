"""解压 1 万份 docx 到容器目录。"""
import zipfile
import os

zip_path = "/tmp/_abtest_docs_10k.zip"
out_dir = "/ragflow/ingest/_abtest_docs_10k"

os.makedirs(out_dir, exist_ok=True)
with zipfile.ZipFile(zip_path) as z:
    z.extractall(out_dir)
print("extracted:", len(os.listdir(out_dir)))
