-- Ingest orchestration schema (MySQL 8.0).
--
-- Database choice: MySQL, not PostgreSQL — see 决策 16. The spec only ever
-- asks for "关系型数据库" (p12, p17); it names no product, and neither does any
-- other customer document. PostgreSQL had been inherited through our own docs
-- without a source. 131 already runs MySQL 8.0.39 (utf8mb4_unicode_ci,
-- InnoDB), so we reuse it rather than operating a second engine.
--
-- Isolation: our own database, never inside RAGFlow's `rag_flow` schema, so a
-- mistaken DROP or a RAGFlow migration cannot reach these tables.
--
-- Portability note: kept to standard SQL where possible (no MySQL-only
-- functions in queries) because a 信创 / domestic-database requirement would
-- otherwise force a rewrite rather than a config change.

CREATE DATABASE IF NOT EXISTS gcn_ingest
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE gcn_ingest;

-- 批量作业：一次导入请求
CREATE TABLE IF NOT EXISTS ingest_job (
    id          BIGINT       NOT NULL AUTO_INCREMENT,
    kb_id       VARCHAR(32)  NOT NULL COMMENT 'RAGFlow dataset id',
    options     JSON         NOT NULL COMMENT '{build_graph, parser_config, ...}',
    status      VARCHAR(16)  NOT NULL COMMENT 'pending/running/succeeded/failed/partial/cancelled',
    priority    INT          NOT NULL DEFAULT 0,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                             ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_job_status (status),
    KEY idx_job_kb (kb_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='批量导入作业';

-- 单文档任务：每份文档一个独立状态机，失败互不影响
CREATE TABLE IF NOT EXISTS ingest_task (
    id              BIGINT       NOT NULL AUTO_INCREMENT,
    job_id          BIGINT       NOT NULL,
    doc_name        VARCHAR(255) NOT NULL,
    doc_path_or_url TEXT         NOT NULL COMMENT '文件来源（本地路径或 URL）',
    ragflow_doc_id  VARCHAR(32)  DEFAULT NULL COMMENT '写入后回填的 document id',
    status          VARCHAR(16)  NOT NULL
                                 COMMENT 'pending/running/succeeded/failed/cancelled/paused',
    priority        INT          NOT NULL DEFAULT 0,
    retry_count     INT          NOT NULL DEFAULT 0,
    current_step    VARCHAR(16)  DEFAULT NULL COMMENT 'parse/chunk/embed/index/graph_build',
    error           TEXT         DEFAULT NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                 ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_task_job (job_id),
    KEY idx_task_status (status),
    -- scheduler picks highest priority first, FIFO within a priority
    KEY idx_task_pick (status, priority DESC, id),
    KEY idx_task_ragflow_doc (ragflow_doc_id),
    CONSTRAINT fk_task_job FOREIGN KEY (job_id) REFERENCES ingest_job (id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='单文档摄入任务';

-- 阶段时间线：真实执行阶段，耗时由流水线自己上报
CREATE TABLE IF NOT EXISTS ingest_step (
    id                   BIGINT       NOT NULL AUTO_INCREMENT,
    task_id              BIGINT       NOT NULL,
    step_name            VARCHAR(16)  NOT NULL
                                      COMMENT 'parse/chunk/embed/index/graph_build 等',
    status               VARCHAR(16)  NOT NULL
                                      COMMENT 'pending/queued/running/done/failed/cancelled',
    started_at           DATETIME     DEFAULT NULL,
    finished_at          DATETIME     DEFAULT NULL,
    progress             INT          NOT NULL DEFAULT 0 COMMENT '0-100',
    duration_ms          INT          DEFAULT NULL COMMENT '优先取引擎自报耗时',
    ragflow_progress     FLOAT        DEFAULT NULL COMMENT '驱动 RAGFlow 时的原始进度',
    ragflow_progress_msg TEXT         DEFAULT NULL COMMENT '诊断线索',
    retry_count          INT          NOT NULL DEFAULT 0,
    error                TEXT         DEFAULT NULL,
    created_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    -- one row per (task, stage): ensure_step relies on this to stay idempotent
    UNIQUE KEY uk_step_task_name (task_id, step_name),
    KEY idx_step_task (task_id),
    CONSTRAINT fk_step_task FOREIGN KEY (task_id) REFERENCES ingest_task (id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='任务阶段时间线';
