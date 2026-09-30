# 131 RAGFlow 服务器代码归档

归档时间：2026-08-04  
运行环境：`infiniflow/ragflow:v0.26.1`  
目的：保存 GCN_Poc GraphRAG 修复前后源码、统一 diff、运行元数据和校验哈希。

## 目录

```text
before/   修复前容器源码快照
           task_executor.py 中原 API Key 已脱敏为 <REDACTED>
after/    2026-08-04 从当前运行容器下载的五个源码文件
diffs/    before -> after 的统一 diff
metadata/ 容器镜像、启动时间、Python 版本和 SHA-256
```

归档文件：

1. `community_report_prompt.py`：删除具体领域示例，防止社区报告复制 Unity March 等文本。
2. `community_reports_extractor.py`：向社区报告结果补充 level 和 community_id。
3. `index.py`：社区报告使用稳定身份生成 ID，并增加碰撞失败保护。
4. `task_executor.py`：移除硬编码 API Key 和模型名，按知识库配置加载模型。
5. `dialog_service.py`：KG retrieval 复用当前 Chat 的 `chat_mdl`。

## 完整性

`metadata/runtime.txt` 保存 131 当前运行容器五个文件的 SHA-256。  
`metadata/local_after_sha256.txt` 保存本地 `after/` 五个文件的 SHA-256。  
2026-08-04 核对时两组哈希逐项一致。

## 安全处理

修复前 `task_executor.py` 曾包含硬编码 API Key。新本地归档已将该值替换为 `<REDACTED>`，因此该文件哈希不会与服务器原始修复前备份一致。未脱敏原始备份仅保留在受控服务器目录：

```text
/u01/isi/zwt/ragflow/GCN_Poc_backup_20260804_152042
```

本归档未复制完整 `docker inspect`，避免把容器环境变量或其他凭据带到本地。

## 恢复边界

当前修复已在 131 运行容器中实测通过，但尚未构建自定义固定镜像。不要直接把 `before/` 或 `after/` 整目录覆盖到其他 RAGFlow 版本；必须基于相同 v0.26.1 基线逐个审查并应用 `diffs/`。

回滚前必须：

1. 确认目标仍是 RAGFlow v0.26.1 和同一代码基线。
2. 备份目标容器当前文件并记录 SHA-256。
3. 逐个检查 diff，尤其是宿主源码与容器源码的历史漂移。
4. 应用后执行 `py_compile`，再验收任务、图主体、社区落库、KG retrieval 和 Chat。
5. 不在有运行中 GraphRAG 任务时覆盖源码。

## 生产化下一步

将五处修改合入受控 RAGFlow 源码分支，补回归测试并构建带唯一 tag/digest 的自定义镜像。只有完成镜像构建和重启回归，才能称为“服务器代码已产品化固化”；当前状态是“运行时修复已验证且已归档”。
