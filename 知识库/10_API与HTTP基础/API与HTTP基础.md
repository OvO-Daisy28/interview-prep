# API 与 HTTP 基础（面试向）

> 定位：把 RAGFlow 涉及的 API、HTTP、RESTful 概念讲清楚，支撑面试时被追问"上传接口是什么""POST 什么意思"等基础问题。
> 阅读顺序：API 是什么 → HTTP 请求方法 → RESTful 约定 → RAGFlow 里的实际接口 → 面试口径

---

## 一、API 是什么

**API（Application Programming Interface，应用程序编程接口）**——程序和程序之间通信的约定。

人用网页交互：打开浏览器 → 点按钮 → 网页发请求给服务器 → 服务器返回页面。
程序用 API 交互：写脚本 → 调 API 接口 → 服务器返回数据（通常是 JSON）→ 脚本处理数据。

**关键区别**：API 不需要人操作浏览器，程序直接通信。RAGFlow 的所有操作（上传、解析、问答、管理知识库）都可以通过 API 完成，不一定要打开网页。

### API 的三要素

| 要素 | 含义 | RAGFlow 例子 |
|---|---|---|
| **URL（路径）** | 接口地址——"去哪找这个服务" | `/api/v1/datasets/{kb_id}/documents` |
| **方法（Method）** | 动作类型——"要干什么" | POST（上传）、GET（查询）、DELETE（删除） |
| **请求体/参数** | 具体数据——"带什么东西去" | 上传时带文件二进制，解析时带 document_ids |

服务器返回的通常是 **JSON 格式的结构化数据**，比如：

```json
{
  "code": 0,
  "message": "success",
  "data": { "id": "doc_abc123", "name": "PTR冷却泵手册.docx", "status": "UNSTART" }
}
```

---

## 二、HTTP 请求方法

HTTP 协议定义了几种请求方法（也叫"动词"），每种代表一种操作语义：

| 方法 | 语义 | 日常类比 | RAGFlow 场景 |
|---|---|---|---|
| **GET** | 获取数据——"给我看看" | 打开网页看列表 | 查文档列表、查知识库配置 |
| **POST** | 提交数据——"我给你东西，你帮我存/处理" | 填表提交 | **上传文档**、**触发解析**、发起问答 |
| **PUT** | 更新（整体替换）——"把旧的换成这个" | 修改个人信息 | 更新知识库配置 |
| **DELETE** | 删除——"删掉这个" | 删文件 | 删文档、删知识库 |
| **PATCH** | 局部更新——"改其中几个字段" | 改昵称 | 更新文档名称 |

### POST 和 GET 的核心区别

| 维度 | GET | POST |
|---|---|---|
| 语义 | 取数据 | 送数据 |
| 请求体 | 一般没有（参数在 URL 里） | **有**（数据放在请求体里） |
| 数据量 | URL 长度有限制（通常 2KB~8KB） | 请求体可以很大（上传文件几百 MB） |
| 幂等性 | 幂等（调一次和调十次结果一样） | 不一定幂等（传十次文档可能建十条记录） |
| 缓存 | 浏览器可能缓存 | 不缓存 |
| 安全性 | 参数在 URL 里可见（别放密码） | 请求体里不可见（相对安全） |

**为什么上传文档用 POST 不用 GET？** 因为上传要把文件二进制数据放在请求体里传给服务器，GET 没有（或不应有）请求体，而且 URL 长度有限制装不下大文件。

### multipart/form-data

上传文件时，请求体格式是 `multipart/form-data`——一种把文件二进制和表单字段混在一起的编码方式：

```
POST /api/v1/datasets/{kb_id}/documents
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary

------WebKitFormBoundary
Content-Disposition: form-data; name="file"; filename="PTR冷却泵手册.docx"
Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document

[文件二进制数据]
------WebKitFormBoundary
Content-Disposition: form-data; name="name"

PTR冷却泵手册
------WebKitFormBoundary--
```

可以理解为：请求体里分成多个"段落"，每段放一个字段或一个文件，用 boundary（分隔线）隔开。

---

## 三、RESTful 约定

RAGFlow 的 API 路径遵循 RESTful 风格——用 URL 路径表示资源，用 HTTP 方法表示操作。

### 资源嵌套

```
/api/v1/datasets                          → 知识库集合
/api/v1/datasets/{kb_id}                  → 某个知识库
/api/v1/datasets/{kb_id}/documents        → 某知识库下的文档集合
/api/v1/datasets/{kb_id}/documents/{doc_id}  → 某个具体文档
/api/v1/datasets/{kb_id}/documents/parse  → 触发解析（动作型接口）
```

**路径里的 `{xxx}` 是路径参数**——调用时替换成实际值。比如 `{kb_id}` 换成知识库的实际 ID。

### 方法 + 路径 = 操作

| 方法 + 路径 | 语义 |
|---|---|
| `GET /datasets/{kb}/documents` | 列出知识库里所有文档 |
| `POST /datasets/{kb}/documents` | 往知识库上传文档 |
| `GET /datasets/{kb}/documents/{id}` | 查某个文档详情 |
| `DELETE /datasets/{kb}/documents/{id}` | 删某个文档 |
| `POST /datasets/{kb}/documents/parse` | 触发解析（body 里带 document_ids 列表） |

### 动作型接口

RESTful 纯粹风格里，所有操作都是 CRUD（增删改查）。但有些操作不好归类（如"触发解析""取消任务"），RAGFlow 用 `POST /资源/动作` 的路径表示：

```
POST /datasets/{kb}/documents/parse    → 触发解析
POST /datasets/{kb}/documents/cancel  → 取消解析
POST /datasets/{kb}/documents/rerun   → 重新解析
```

---

## 四、RAGFlow 全链路涉及的实际 API

| 环节 | 方法 + 路径 | 做什么 |
|---|---|---|
| 创建知识库 | `POST /api/v1/datasets` | 建库（名字、解析模板、embedding 模型配置） |
| 上传文档 | `POST /api/v1/datasets/{kb}/documents` | 文件落 MinIO + MySQL 建记录（状态=UNSTART） |
| 触发解析 | `POST /api/v1/datasets/{kb}/documents/parse` | 改状态=RUNNING + 写 Redis Stream 队列 |
| 查解析进度 | `GET /api/v1/datasets/{kb}/documents` | 从 MySQL 查进度浮点和状态 |
| 取消解析 | `POST /api/v1/datasets/{kb}/documents/cancel` | 设 canceled 标志（软取消） |
| 发起问答 | `POST /api/v1/chats` 或 `/completion` | 问题向量化 + ES 检索 + LLM 生成 |
| 查知识库文档 | `GET /api/v1/datasets/{kb}/documents` | 分页查文档列表 |

### 上传接口的关键源码

```
POST /api/v1/datasets/{kb}/documents  (multipart)
  → document_api.py:449 upload_document()
  → FileService.upload_document()  file_service.py:542
      ① STORAGE_IMPL.put(kb.id, location, blob)   # MinIO 存文件
      ② DocumentService.insert(doc)               # MySQL 建记录
      ③ 缩略图 thumbnail_{doc_id}.png              # MinIO 存缩略图
```

**上传只做这三件事，不触发解析**。文档状态是 UNSTART（未开始），要再调解析接口才进队列。

### 解析触发接口

```
POST /datasets/{kb}/documents/parse  (body: document_ids)
  → document_api.py:1549 parse_documents()
      ① 清旧数据（task 记录、ES 旧 chunks、进度计数）
      ② DocumentService.run() → 改状态=RUNNING
      ③ queue_tasks() → Redis Stream 写任务消息
```

**上传和解析是两次独立的 API 调用**——可以先批量传 100 份文档（3.2 秒），再选择性触发解析。

---

## 五、面试口径

### "上传的 API 是什么意思？"

> API 就是程序之间通信的约定。上传文档调的是 POST 接口，路径是 `/api/v1/datasets/{kb_id}/documents`，请求体里带文件二进制数据。API Server 收到后做三件事：文件存 MinIO、元数据写 MySQL（状态=未开始）、生成缩略图。上传不触发解析——要再调一次解析接口，任务才进 Redis Stream 队列。

### "POST 是什么？"

> HTTP 协议的请求方法，语义是"提交数据"。和 GET（获取数据）对应。上传文档用 POST 是因为要把文件二进制放在请求体里传给服务器，GET 没有请求体且 URL 长度有限装不下文件。

### "上传和解析为什么是两步？"

> 设计上是解耦的。上传只做落盘+建记录，3.2 秒传 100 份就完了。解析是重活（OCR、向量化），单份几十秒到几分钟，走异步队列。两步独立的好处是可以先批量传完再选择性解析，上传接口不会被解析拖慢。

### "你怎么批量上传的？"

> 写脚本循环调上传接口，每次 POST 一个文件。100 份文档 3.2 秒传完——上传本身很快，慢的是后面的解析。批量上传时注意服务器的并发连接限制和 MinIO 的写入吞吐，不是越多并发越好。

---

## 来源

- RAGFlow 源码：`api/document_api.py`（路由定义）、`rag/svr/file_service.py`（上传实现）
- HTTP 协议：RFC 7231（HTTP/1.1 语义）
- RESTful API 设计：REST 论文（Fielding, 2000）

---

## 六、FastAPI（RAGFlow 的 API Server 框架）

### FastAPI 是什么

FastAPI 是一个用 Python 写 Web API 的高性能框架。RAGFlow 的 API Server 就是用 FastAPI 写的——所有 `POST /api/v1/...` 接口都是 FastAPI 路由。

### Python Web 框架横向对比

| 框架 | 定位 | 特点 | 代表用户 | 类比 |
|---|---|---|---|---|
| **Django** | 全栈大而全 | 自带 ORM、Admin、模板引擎、认证，什么都有 | Instagram、Pinterest | "全家桶"——精装修拎包入住 |
| **Flask** | 微框架 | 只给路由和请求处理，其他全靠插件自己拼 | Netflix 部分服务 | "毛坯房"——给你墙和门，装修自己搞 |
| **FastAPI** | 高性能 API 专用 | 异步、类型提示自动校验+生成文档、性能接近 Go/Node | RAGFlow、Uber 部分服务 | "精装公寓"——专做 API 做到极致 |
| **Tornado** | 异步老牌 | 早期异步方案，协程模型 | 早期知乎、Quora | "老式精装"——当年先进，现在被 FastAPI 盖过 |

### 关键区别维度

| 维度 | Django | Flask | FastAPI | Tornado |
|---|---|---|---|---|
| 定位 | 全栈（前端+后端+数据库） | 微框架（只管路由） | **API 专用** | 异步 Web |
| 异步支持 | 3.0+ 部分支持 | 需插件 | **原生 async/await** | 原生协程 |
| 性能 | 最慢（框架重） | 中等 | **最快（接近 Go/Node）** | 快 |
| 类型提示 | ❌ | ❌ | **✅ 自动校验+生成文档** | ❌ |
| 自动 API 文档 | 需插件 | 需插件 | **✅ 内置 Swagger** | ❌ |
| 学习曲线 | 高（东西多） | 低 | **低** | 中 |
| 适合场景 | 全功能网站 | 简单 API/原型 | **高性能 API 服务** | 长连接/WebSocket |

### FastAPI 为什么适合 RAGFlow

1. **API 专用**：RAGFlow 前端是单独的 React，后端只需要 API Server——FastAPI 专做这个
2. **异步**：问答接口要等 LLM 生成（几十秒），异步可以让一个进程同时处理多个请求，不会一个请求卡死整个服务
3. **类型提示自动校验**：请求参数类型、必填校验自动完成，减少手写验证代码
4. **自动 Swagger 文档**：RAGFlow 的 API 文档页面就是 FastAPI 自动生成的

### FastAPI vs Flask 代码对比

```python
# FastAPI——类型校验自动、异步、自动出文档
from fastapi import FastAPI, UploadFile
app = FastAPI()

@app.post("/api/v1/datasets/{kb_id}/documents")
async def upload_document(kb_id: str, file: UploadFile):
    # kb_id 自动从路径提取，file 自动从请求体提取
    # 类型不对自动返回 422 错误
    content = await file.read()
    return {"code": 0, "data": {"id": "doc_abc", "name": file.filename}}
```

```python
# Flask——手动取参数、手动校验、同步阻塞
from flask import Flask, request
app = Flask(__name__)

@app.route("/api/v1/datasets/<kb_id>/documents", methods=["POST"])
def upload_document(kb_id):
    file = request.files.get("file")   # 手动取，没有校验
    if not file:
        return {"error": "no file"}, 400   # 手动错误处理
    content = file.read()   # 同步阻塞，大文件卡住
    return {"code": 0, "data": {"id": "doc_abc"}}
```

FastAPI 少写验证代码、自动出文档、异步不阻塞、性能更好——RAGFlow 选它不意外。

### 面试口径

> RAGFlow 的 API Server 用的是 FastAPI，一个 Python 的高性能 Web API 框架。选它因为三个原因：API 专用（不需要 Django 那种全栈东西）、原生异步（LLM 生成几十秒不会卡死其他请求）、类型提示自动校验+生成 Swagger 文档。对比 Flask，FastAPI 少写验证代码、性能更好（接近 Go/Node），但只做 API 不做全栈网站——RAGFlow 前端是独立的 React，后端只需要 API，正好合适。
