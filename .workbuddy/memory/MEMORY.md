# 项目长期记忆

## 用户学习偏好

- 对概念和方法希望有同类对比着讲：不孤立解释一个名词，要列出同类选项做横向对比表
- 例子：讲 FastAPI 时要对比 Django/Flask/Tornado；讲 BM25 时对比 TF-IDF；讲 HNSW 时对比 IVF/LSH
- 对具体公式和模型对比感兴趣，希望引用官方文档而非二手总结
- 不喜欢抠字眼的防御式清单，偏好"先自己回答→纠正补充→确认写入"的对话式梳理

## 项目实际部署口径

- Embedding 模型：BGE-M3（1024 维，BAAI FlagEmbedding），不是 bge-base-zh-v1.5
- RAGFlow 官方默认配：Qwen3-Embedding-0.6B（LLM-based 架构）
- 教训：实际部署的模型名必须和用户确认后再写文档，不能凭调研推断
