# RAGFlow v0.26.1 运行时修复归档

归档日期：2026-08-04。目标环境为 131 服务器的 `infiniflow/ragflow:v0.26.1`。

## 目录职责

- `container/`：五个关键文件的修复前脱敏版本、运行中修复后版本、统一 diff、容器元数据和 SHA-256。它是本次真实运行终态的审计 SSOT。
- `host/`：当时同步到宿主源码树的三处 GraphRAG 文件前后版本和 diff，用于识别宿主与容器历史漂移。

宿主归档只包含 `community_report_prompt.py`、`community_reports_extractor.py` 和 `index.py`。`task_executor.py`、`dialog_service.py` 的完整修复前后版本在 `container/` 中；没有证据表明当时已将这两处完整同步到宿主源码树，因此不伪造宿主副本。

## 完整性结论

迁移前已将旧 `outputs/repair_2026-08-04/server_code_archive/` 与 `container/` 逐文件比较：18/18 文件存在且 SHA-256 全部一致。修复后五个 `container/after/` 文件的哈希与 131 当时运行容器逐项一致，见 `container/metadata/runtime.txt`。迁移后仅做位置规整：`container/diffs/` 文件头改为当前 `container/before|after` 路径，`container/metadata/local_after_sha256.txt` 改用 `after/...` 相对路径；补丁正文和五个源码文件未变。

## 使用边界

这些文件证明“运行时修复已验证并归档”，不证明自定义镜像已经构建。应用补丁前必须确认目标仍为相同 v0.26.1 基线，逐文件审查 diff、备份目标文件并在无运行中 GraphRAG 任务时操作。生产化仍需合入受控源码分支、补回归测试、构建唯一 tag/digest 的固定镜像并执行重启回归。
