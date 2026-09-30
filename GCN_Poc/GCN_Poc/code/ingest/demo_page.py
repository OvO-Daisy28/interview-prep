"""Demo page for the PM review: live interface, decisions, and measurements.

Three things need to land in one place, because they answer three different
questions the PM will have:

  1. does it work        — a live console driving the real endpoints
  2. why is it built     — the alternatives we weighed and why this one won
     this way               (a decision the reviewer can disagree with only if
                            they can see the reasoning)
  3. what do we know      — measured numbers, with the caveats attached, so
     about performance      nobody quotes a figure that was taken on an
                            overloaded machine

Served by the same FastAPI app so there is nothing extra to deploy:
    GET /demo  -> this page
Everything on it calls the same /ingest/* endpoints the PM's frontend would.
"""

from __future__ import annotations

DEMO_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>批量导入编排接口 · 进度汇报</title>
<style>
  :root {
    --bg: #0f1115; --panel: #171a21; --line: #262a33; --text: #e6e8eb;
    --muted: #9aa3ad; --accent: #4c8dff; --ok: #35c56a; --warn: #f5a623;
    --err: #ff5f56; --queued: #555c68;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text);
         font: 14px/1.6 -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; }
  header { padding: 20px 28px; border-bottom: 1px solid var(--line);
           display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap; }
  header h1 { margin: 0; font-size: 19px; font-weight: 600; }
  header .sub { color: var(--muted); font-size: 13px; }
  header .live { margin-left: auto; font-size: 12px; color: var(--muted); }
  .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%;
         background: var(--err); margin-right: 6px; vertical-align: middle; }
  .dot.up { background: var(--ok); }
  nav { display: flex; gap: 4px; padding: 0 28px; border-bottom: 1px solid var(--line); }
  nav button { background: none; border: none; color: var(--muted);
               padding: 12px 18px; cursor: pointer; font-size: 14px;
               border-bottom: 2px solid transparent; }
  nav button.on { color: var(--text); border-bottom-color: var(--accent); }
  main { padding: 24px 28px 60px; max-width: 1180px; }
  section { display: none; } section.on { display: block; }
  .panel { background: var(--panel); border: 1px solid var(--line);
           border-radius: 8px; padding: 18px; margin-bottom: 18px; }
  .panel h2 { margin: 0 0 4px; font-size: 15px; font-weight: 600; }
  .panel .hint { color: var(--muted); font-size: 12.5px; margin-bottom: 14px; }
  button.act { background: var(--accent); color: #fff; border: none;
               padding: 8px 16px; border-radius: 5px; cursor: pointer;
               font-size: 13px; }
  button.act:hover { filter: brightness(1.1); }
  button.act:disabled { opacity: .45; cursor: not-allowed; }
  button.mini { background: #232833; color: var(--text); border: 1px solid var(--line);
                padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 12px; }
  button.mini:hover { border-color: var(--accent); }
  input, select { background: #0d1016; color: var(--text); border: 1px solid var(--line);
                  border-radius: 5px; padding: 7px 10px; font-size: 13px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--line);
           vertical-align: middle; }
  th { color: var(--muted); font-weight: 500; font-size: 12px; }
  .tag { display: inline-block; padding: 2px 9px; border-radius: 11px;
         font-size: 11.5px; border: 1px solid; }
  .tag.succeeded { color: var(--ok); border-color: var(--ok); }
  .tag.running   { color: var(--accent); border-color: var(--accent); }
  .tag.pending   { color: var(--muted); border-color: var(--queued); }
  .tag.failed    { color: var(--err); border-color: var(--err); }
  .tag.paused    { color: var(--warn); border-color: var(--warn); }
  .tag.cancelled { color: var(--muted); border-color: var(--queued); }
  .pipe { display: flex; gap: 3px; align-items: center; }
  .stg { flex: 1; height: 5px; border-radius: 3px; background: var(--queued);
         position: relative; }
  .stg.done { background: var(--ok); }
  .stg.running { background: var(--accent); }
  .stg.failed { background: var(--err); }
  .stg span { position: absolute; top: 9px; left: 0; font-size: 10px;
              color: var(--muted); white-space: nowrap; }
  .counts { display: flex; gap: 22px; flex-wrap: wrap; }
  .counts div { text-align: center; }
  .counts b { display: block; font-size: 22px; font-weight: 600; }
  .counts small { color: var(--muted); font-size: 11.5px; }
  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .why { border-left: 3px solid var(--accent); padding-left: 14px; margin: 14px 0; }
  .why h3 { margin: 0 0 6px; font-size: 14px; }
  .why p { margin: 4px 0; color: var(--muted); font-size: 13px; }
  .pick { color: var(--ok); font-weight: 600; }
  .drop { color: var(--muted); text-decoration: line-through; }
  code { background: #0d1016; padding: 1.5px 6px; border-radius: 4px;
         font-size: 12px; color: #b9c6d8; }
  .caveat { background: #2a2016; border-left: 3px solid var(--warn);
            padding: 10px 14px; border-radius: 0 6px 6px 0; font-size: 13px;
            color: #f0d9b5; margin: 12px 0; }
  .num { font-variant-numeric: tabular-nums; }
  .step { display: flex; gap: 14px; margin: 20px 0; }
  .step .idx { flex: none; width: 26px; height: 26px; border-radius: 50%;
               background: var(--accent); color: #fff; font-size: 13px;
               display: flex; align-items: center; justify-content: center; }
  .step h3 { margin: 2px 0 6px; font-size: 14.5px; }
  .step p { margin: 5px 0; color: var(--muted); font-size: 13px; }
  .step ul { margin: 6px 0; padding-left: 18px; color: var(--muted); font-size: 13px; }
  .step li { margin: 5px 0; }
  .step b { color: var(--text); }
  .asterisk { border-left: 2px solid var(--line); padding-left: 10px;
              font-size: 12.5px !important; }
  .drop-zone { border: 1.5px dashed var(--line); border-radius: 8px;
               padding: 26px; text-align: center; cursor: pointer;
               transition: all .15s; }
  .drop-zone:hover, .drop-zone.over { border-color: var(--accent);
                                      background: #141922; }
  .chip { display: inline-block; background: #232833; border: 1px solid var(--line);
          border-radius: 4px; padding: 3px 9px; margin: 3px 4px 0 0; font-size: 12px; }
  .col-key { color: var(--accent); font-weight: 600; }
  .schema-tbl td { font-size: 12.5px; padding: 6px 10px; }
  .api { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px; }
  .api .m { color: var(--accent); }
  .log { background: #0d1016; border-radius: 6px; padding: 10px 12px;
         font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 11.5px;
         color: #93a4b8; max-height: 170px; overflow-y: auto; white-space: pre-wrap; }
</style>
</head>
<body>
<header>
  <h1>批量导入编排接口</h1>
  <span class="sub">中广核采购文件活化项目 · 项目经理第 1 点</span>
  <span class="live"><span class="dot" id="dot"></span><span id="health">检测服务…</span></span>
</header>

<nav>
  <button class="on" data-tab="live">接口实况</button>
  <button data-tab="why">方案与取舍</button>
  <button data-tab="stack">技术栈</button>
  <button data-tab="store">数据存储</button>
  <button data-tab="data">实测数据</button>
  <button data-tab="next">瓶颈与下一步</button>
</nav>

<main>

<!-- ============ 1. 接口实况 ============ -->
<section id="live" class="on">
  <div class="panel">
    <h2>上传文档</h2>
    <p class="hint">
      选择要导入的知识库，然后拖入或选择 Word / PDF / 文本文件。
      接口 <code class="api"><span class="m">POST</span> /ingest/upload</code> 收下文件后立即返回，
      解析由后台进行——这就是"批量不阻塞"。
    </p>

    <div style="display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-bottom:12px;">
      <label>目标知识库
        <select id="kb" style="min-width:280px"><option value="">加载中…</option></select>
      </label>
      <label style="display:flex;align-items:center;gap:6px">
        <input type="checkbox" id="graph"> 同时构建知识图谱
      </label>
    </div>

    <div id="drop" class="drop-zone">
      <div style="font-size:15px">把文件拖到这里，或<b style="color:var(--accent)">点击选择</b></div>
      <div style="color:var(--muted);font-size:12.5px;margin-top:6px">
        支持 .docx / .txt / .md；PDF 与扫描件将转交 MinerU 处理
      </div>
      <input type="file" id="picker" multiple accept=".docx,.txt,.md,.pdf" hidden>
    </div>
    <div id="picked" style="margin-top:10px"></div>

    <div style="display:flex; gap:10px; align-items:center; margin-top:12px; flex-wrap:wrap;">
      <button class="act" id="upload" disabled>上传并开始处理</button>
      <span style="color:var(--muted);font-size:12px">— 或者 —</span>
      <button class="mini" id="sample">用内置样例快速演示（5 份 + 1 份故意失败）</button>
    </div>
    <div class="log" id="log" style="margin-top:12px">就绪。</div>
  </div>

  <div class="panel">
    <h2>队列状态 <code class="api"><span class="m">GET</span> /ingest/queue</code></h2>
    <p class="hint">按状态实时计数。五种状态与项目经理原型里的口径一致。</p>
    <div class="counts" id="counts"></div>
  </div>

  <div class="panel">
    <h2>任务进度与控制</h2>
    <p class="hint">
      进度来自 <code class="api"><span class="m">GET</span> /ingest/jobs/{id}</code>；
      按钮分别调用 <code class="api">pause</code> / <code class="api">resume</code> /
      <code class="api">retry</code> / <code class="api">cancel</code>。
      四个阶段的耗时是我们自己流水线上报的真实值，不是估算。
    </p>
    <table>
      <thead><tr>
        <th style="width:20%">文档</th><th style="width:8%">状态</th>
        <th style="width:10%">开始时刻</th>
        <th style="width:27%">解析 · 切块 · 向量化 · 索引</th>
        <th style="width:11%">耗时</th><th style="width:24%">控制</th>
      </tr></thead>
      <tbody id="rows"><tr><td colspan="6" style="color:var(--muted)">尚无任务，先提交一批。</td></tr></tbody>
    </table>
    <p style="color:var(--muted);font-size:12.5px;margin-top:10px">
      <b>怎么看出是并发的</b>：看「开始时刻」——同一批里前 3 份的开始时刻<b>完全相同</b>，
      说明它们同时在跑（服务器时间，默认并发 3）。
      但它们<b>完成时间会差很远</b>：一份 Word 二十几秒就好了，一份扫描 PDF 要两三分钟。
      所以界面上看起来像"一份接一份"，其实是<b>同时开始、先后结束</b>。
      原理与实测证据见「技术栈 → 批量并发是怎么实现的」。
    </p>
  </div>
</section>

<!-- ============ 2. 方案与取舍 ============ -->
<section id="why">
  <div class="panel">
    <h2>我们是怎么一步步走到当前方案的</h2>
    <p class="hint">方向调整过一次。不是推倒重来，而是被实测数据推着走——过程如下。</p>

    <div class="step">
      <div class="idx">1</div>
      <div>
        <h3>出发点：让 RAGFlow 干活，我们只做编排</h3>
        <p>项目经理提的需求是「批量上传要能记录每阶段时间、随时开始停止重试、能读写队列状态、最后给出接口」。
           最自然的做法是：文档还是交给 RAGFlow 解析，我们在外面排队、轮询进度、包一层接口。
           这样改动最小，也不碰它的内核。</p>
        <p><b>按这个思路做完了第一版</b>：状态机、调度器、REST 接口、118 个测试，全部跑通。</p>
      </div>
    </div>

    <div class="step">
      <div class="idx">2</div>
      <div>
        <h3>接上真实服务器后，发现四个绕不过去的问题</h3>
        <p>这些不是设想出来的，是第一版接到服务器实跑时撞出来的：</p>
        <ul>
          <li><b>进度只能靠猜</b>——RAGFlow 只给一个 0~1 的小数，加一段不断累加的日志文字。
              要知道「现在在解析还是在向量化」，只能用关键词去匹配那段日志。
              为此接连修了 4 个 bug（比如「Embedding chunks」这句话里同时有"chunk"和"embedding"两个词，
              会被误判成切块阶段），改完仍然脆弱——它下次升级换个日志措辞，我们就又错了。</li>
          <li><b>没有暂停</b>——只能整个取消，之前的进度全部作废。而知识图谱构建一次要 20 分钟，
              跑到 90% 被取消等于白干。</li>
          <li><b>没有自动重试</b>——失败就是失败，只能整份重来。</li>
          <li><b>性能不由我们掌握</b>——它默认单个处理进程，我们在外面加再多并发也没用。</li>
        </ul>
      </div>
    </div>

    <div class="step">
      <div class="idx">3</div>
      <div>
        <h3>关键转折：这些能力，其实我们自己做得到</h3>
        <p>问题的根子是：<b>干活的不是我们，所以控制不了</b>。于是重新问了一个问题——
           如果解析、切块、向量化都我们自己做，会怎样？</p>
        <p>担心的是：这样一来 RAGFlow 还认不认这些数据？它的检索、知识图谱还能不能用？
           <b>于是先去查证，而不是直接动手</b>。</p>
      </div>
    </div>

    <div class="step">
      <div class="idx">4</div>
      <div>
        <h3>查证：把 RAGFlow 的数据存放方式摸清楚</h3>
        <p>登录服务器，逐层查它的源码、数据库和索引，确认了五件事：</p>
        <ul>
          <li>原文件存在 MinIO，按知识库分桶，规则很简单</li>
          <li>切块后的内容存在 Elasticsearch，<b>一条记录只有 14 个字段</b>，没有隐藏要求</li>
          <li>向量模型是<b>独立的服务</b>，本来就可以直接调用</li>
          <li>中文分词器是个标准 Python 包，装上就能用</li>
          <li><b>最关键</b>：知识图谱构建只从 Elasticsearch 读数据，<b>不关心这些数据是谁写的</b></li>
        </ul>
        <p>最后一条决定了方案可行——只要我们按同样格式写进去，下游一切照常。</p>
      </div>
    </div>

    <div class="step">
      <div class="idx">5</div>
      <div>
        <h3>先做最小验证，再全面改造</h3>
        <p>没有直接重构，而是先写了一个最小的验证程序：自己解析一份文档、自己切块、
           自己调向量模型、自己写进那三个存储，然后去看 RAGFlow 认不认。</p>
        <p><b>结果全部通过</b>：文档出现在它的列表里、它的检索能命中、
           后来知识图谱也成功建了图。验证通过之后，才把整条流水线改过来。</p>
        <p class="asterisk">过程中还发现一个容易踩的坑：只写文档记录是不够的，
           必须同时写另外两张关联表，否则文档在界面上完全看不见。</p>
      </div>
    </div>

    <div class="step">
      <div class="idx">6</div>
      <div>
        <h3>结果：四个问题一次性解决</h3>
        <p>进度不用猜了（每个阶段由我们自己上报真实耗时）；暂停能做了（自己的循环随时可停）；
           重试能做了；并发和批量大小自己定。<b>而 RAGFlow 的检索和知识图谱照常可用。</b></p>
      </div>
    </div>
  </div>

  <div class="panel">
    <h2>核心取舍：不走 RAGFlow 的解析流程，改为复用它的存储</h2>
    <p class="hint">这是整个方案里影响最大的一次选择，三条路都评估过。</p>

    <div class="why">
      <h3><span class="drop">方案一：调用 RAGFlow 的解析接口</span>（最初实现，已放弃）</h3>
      <p>让 RAGFlow 解析，我们只做排队和轮询。</p>
      <p><b>放弃原因（都是实测撞出来的）</b>：进度只有一个 0~1 的小数加一段累积日志，
         阶段只能靠正则去猜——为此修了 4 个 bug 仍然脆弱；没有暂停能力；没有自动重试；
         性能受制于它的单 worker，我们无从优化。</p>
    </div>

    <div class="why">
      <h3><span class="drop">方案二：改 RAGFlow 源码</span>（评估后不做）</h3>
      <p>直接给它加进度上报、暂停检查点、重试。</p>
      <p><b>不做的原因</b>：改内核要完整追调用链（历史上漏改一处导致 225 条关系丢失），
         而且每次 RAGFlow 升级都要重新合并补丁，长期维护成本高。</p>
    </div>

    <div class="why">
      <h3><span class="pick">方案三：自建流水线 + 复用基础设施</span>（采用）</h3>
      <p>解析、切块、向量化、写入全部自己做，但把产物写进 RAGFlow 认识的地方——
         同一个 MinIO、同一个 Elasticsearch、同一个向量模型。</p>
      <p><b>选它的理由</b>：进度是我们上报的不用猜；暂停是自己的循环随时可停；
         并发和批量大小自己定；RAGFlow 升级不影响我们（只依赖存储格式，不依赖它的代码）；
         而<b>下游一切照常</b>——它的检索、知识图谱都能正常读到我们写的数据。</p>
      <p><b>已实测验证</b>：我们写入的文档出现在 RAGFlow 文档列表；它的检索能命中；
         GraphRAG 对我们写的内容成功建图（36 个实体 / 33 条关系 / 8 篇社区报告），
         知识图谱检索也能用上。</p>
    </div>
  </div>

  <div class="panel">
    <h2>其他几个关键选择</h2>

    <div class="why">
      <h3>暂停：默认「优雅暂停」，另提供「强制停止」</h3>
      <p>优雅暂停等当前阶段跑完再停，不浪费已完成的工作；强制停止立即中断但进度作废。
         默认取前者，与 Airflow、Kubernetes 等业界惯例一致。</p>
    </div>

    <div class="why">
      <h3>数据库：MySQL，不是 PostgreSQL</h3>
      <p>技术规范书只要求「关系型数据库」（第 12、17 页），全文没有指定任何数据库产品。
         早期文档里的 PostgreSQL 没有依据。改用服务器上<b>已经在运行</b>的 MySQL，
         少维护一套数据库，并单独建库与 RAGFlow 隔离。</p>
    </div>

    <div class="why">
      <h3>任务队列：先用 MySQL 表，规模上来后换 Redis</h3>
      <p>需求要的是"可查询、可修改优先级"的队列，而 Redis 的 List/Stream 是消息管道，
         做不了条件查询，旁边仍要挂一张状态表。当前又是单实例，
         Redis 的多机消费优势还兑现不了，所以先用已有的 MySQL。
         <b>代价是只能单实例运行</b>，多机扩展前必须先换。
         详细理由、代价与演进路径见「技术栈」页。</p>
    </div>

    <div class="why">
      <h3>PDF 与扫描件：调用 MinerU 服务</h3>
      <p>Word/Excel 是结构化格式，直接读取，毫秒级完成；PDF 只有字符坐标、扫描件只有像素，
         必须靠版面分析和 OCR，交给服务器上已部署的 MinerU。按需调用，不给简单文档增加成本。</p>
    </div>

    <div class="why">
      <h3>本接口不做的事</h3>
      <p>用大模型抽取参数、复合参数拆分、信息块建立、PBS 关联、AI 审核界面——
         这些属于「内容解析子系统」，是另一块独立建设的内容，不在本接口范围内。</p>
    </div>
  </div>
</section>

<!-- ============ 技术栈 ============ -->
<section id="stack">
  <div class="panel">
    <h2>用了哪些技术，为什么这么选</h2>
    <p class="hint">原则：优先复用服务器上已经在跑的东西，少引入一套需要维护的新组件。</p>
    <table>
      <thead><tr><th style="width:16%">环节</th><th style="width:22%">用什么</th><th>为什么是它</th></tr></thead>
      <tbody>
        <tr><td>接口服务</td><td>Python + FastAPI</td>
            <td>自带交互式接口文档，前端对接方便；与 MinerU 服务同技术栈</td></tr>
        <tr><td>任务状态</td><td><b>MySQL</b></td>
            <td>规范书只要求「关系型数据库」，未指定产品。服务器上已经在跑 MySQL，复用它少维护一套；单独建库与 RAGFlow 隔离</td></tr>
        <tr><td>原文件存储</td><td>MinIO（复用）</td>
            <td>RAGFlow 就用它，写进同一个地方，下游才能读到</td></tr>
        <tr><td>内容与向量</td><td>Elasticsearch（复用）</td>
            <td>同上。这是知识图谱和检索的数据来源</td></tr>
        <tr><td>向量模型</td><td>bge-base（复用）</td>
            <td>本来就是独立服务，直接调用即可，向量与 RAGFlow 完全一致</td></tr>
        <tr><td>中文分词</td><td>RAGFlow 同款分词器</td>
            <td>标准 Python 包，装上即用。用同一个才能保证检索效果一致</td></tr>
        <tr><td>Word/Excel 解析</td><td>自己解析</td>
            <td>这类文件本身就是结构化的，直接读取，毫秒级完成，不需要模型</td></tr>
        <tr><td>PDF / 扫描件</td><td>MinerU（复用）</td>
            <td>PDF 只有字符坐标、扫描件只有图像，必须靠版面分析和文字识别。服务器已部署，按需调用</td></tr>
      </tbody>
    </table>
    <p style="color:var(--muted);font-size:13px;margin-top:14px">
      <b>整体思路</b>：新增的只有「编排服务」这一层和一个 MySQL 库，
      其余全部复用现有组件——既不重复建设，也保证与 RAGFlow 的数据互通。
    </p>
  </div>

  <div class="panel">
    <h2>批量并发是怎么实现的</h2>
    <p class="hint">
      常被问的一句是"背后是 Redis 队列吗"——不是。当前是
      <b>MySQL 一张任务表 + 一个后台线程池</b>。链路、理由和代价都在下面。
    </p>

    <div class="step">
      <div class="idx">1</div>
      <div>
        <h3>接口收下文件就返回，不等解析</h3>
        <p><code class="api"><span class="m">POST</span> /ingest/upload</code> 做三件事：
           把文件存下来、在 <code>ingest_task</code> 表里为<b>每一份文档插一行「排队」</b>、
           返回作业号。一次传 10 份，接口也是百毫秒级返回——
           这就是页面上"接口 XXms 返回，后台处理中"那行日志的含义。</p>
      </div>
    </div>

    <div class="step">
      <div class="idx">2</div>
      <div>
        <h3>后台常驻 worker 扫表取活</h3>
        <p>服务里有一个一直在跑的线程，<b>每 2 秒查一次表</b>：还有哪些是「排队」状态？
           取出来时按<b>优先级高的先做，同优先级先提交的先做</b>。
           提交接口还会额外"踢一脚"叫醒它，所以实际上通常是立刻开始，不用真等 2 秒。</p>
      </div>
    </div>

    <div class="step">
      <div class="idx">3</div>
      <div>
        <h3>线程池同时跑 3 份</h3>
        <p>取出的任务丢进线程池，<b>同时最多跑 3 份</b>（可配置，实测在这台机器上 3 是最优值）。
           每一份在自己的线程里独立走完解析 → 切块 → 向量化 → 索引四步。</p>
        <p>为什么限制在 3 而不是全放开：见「实测数据」——并发提到 6 时下游的
           Elasticsearch 和向量服务开始互相争抢，反而比不并发还慢 58%。</p>
      </div>
    </div>

    <div class="step">
      <div class="idx">4</div>
      <div>
        <h3>每份独立记账，一份失败不牵连其余</h3>
        <p>每个线程各自捕获异常。一份文档失败，只把它那一行标成「失败」并记下原因，
           <b>其余的照常跑完</b>。页面上"5 份正常 + 1 份故意失败"的样例演示的就是这一条。</p>
      </div>
    </div>

    <div class="step">
      <div class="idx">5</div>
      <div>
        <h3>状态实时写回同一张表</h3>
        <p>每个阶段开始和结束时都写回数据库。前端轮询的
           <code class="api"><span class="m">GET</span> /ingest/queue</code> 和
           <code class="api"><span class="m">GET</span> /ingest/jobs/{id}</code> 读的就是这张表。
           <b>"能读取和修改队列状态"因此是天然支持的</b>——队列本来就是一张表，
           可以按知识库查、按状态查、直接改优先级。</p>
      </div>
    </div>

    <div class="caveat">
      <b>为什么上传两份文件时"看起来像串行"</b>：因为并发是真的，但两份的快慢能差 6 倍。
      实测同一批的两份文件<b>同一秒开始</b>（02:22:17），
      Word 那份 25.9 秒就结束了，扫描 PDF 那份跑到 166.9 秒。
      界面上先看到一份完成、另一份还在转，很自然会以为是排队一份一份来的。
      <b>看「开始时刻」列可以直接确认</b>——两行的开始时刻是一样的。完整数据见「实测数据」页。
    </div>
  </div>

  <div class="panel">
    <h2>队列为什么用 MySQL 表，而不是 Redis</h2>
    <p class="hint">
      业界做队列确实多用 Redis / RabbitMQ。这里选了数据库表，是有具体理由的；
      但它的代价也真实存在，一并说清楚。
    </p>

    <div class="why">
      <h3>选 MySQL 表的三条理由</h3>
      <p><b>一、需求要的是"可查询可修改的队列"，不是"消息管道"。</b>
         项目经理第 1 点明确要求能读取和修改队列状态——
         比如"把所有失败的任务查出来重排优先级"。Redis 的 List / Stream 本质是消息通道，
         做不了这种条件查询和随机修改，最终仍要在旁边挂一张表存状态，
         变成<b>两处存储要保持一致</b>。</p>
      <p><b>二、阶段耗时本来就是要长期留存的业务数据。</b>
         每份文档四个阶段的开始时间、结束时间、耗时、重试次数、失败原因，
         是要能事后查账的，本来就该放关系库。既然表已经存在，
         再单独引入一个队列反而多一层同步。</p>
      <p><b>三、当前是单实例，Redis 的价值还没到兑现的时候。</b>
         Redis 的核心优势是让<b>多台机器同时安全地消费同一个队列</b>。
         目前只有一个服务进程，这个优势用不上，而 MySQL 已经在这台机器上跑着，
         少运维一个组件。</p>
    </div>

    <div class="why" style="border-left-color:var(--warn)">
      <h3>代价（如实说明，不回避）</h3>
      <p><b>空转轮询</b>：没有任务时也每 2 秒查一次表。单条查询很轻，
         但确实是无用功；Redis 的阻塞读能做到"有活才醒"。</p>
      <p><b>最长 2 秒的取任务延迟</b>：提交接口会主动叫醒 worker，
         所以实际通常立刻开始；但如果只靠轮询，最坏要等 2 秒。</p>
      <p><b>只能单实例运行</b>：目前"谁来取这个任务"没有跨进程的抢锁保护，
         同时起两个服务进程会重复处理同一份文档。
         <b>这是当前方案最实在的限制</b>——要横向扩机器，必须先解决这一步。</p>
    </div>

    <div class="why" style="border-left-color:var(--ok)">
      <h3>后续演进：会换成 Redis，但不是"替换掉 MySQL"</h3>
      <p>规模到千份级、或者需要<b>多机同时消费</b>时，队列会换成 Redis（或 RabbitMQ）。
         但 MySQL 不会被替掉——通行做法是<b>队列归队列、账本归账本</b>：
         Redis 负责"下一个该谁干、多机之间不重不漏"，
         MySQL 继续存阶段耗时、重试次数、失败原因这些要查账的数据。</p>
      <p><b>为什么现在不做</b>：不为还没到来的规模提前付运维成本。
         真正的判断依据是百份、千份级压测的结果，那正是下一步要做的事。</p>
      <p><b>换的时候要改多少</b>：取任务这件事只集中在调度器一个类里——
         <b>接口、状态机、表结构都不用动</b>。这是当初把三层拆开的目的之一。</p>
    </div>
  </div>

  <div class="panel">
    <h2>具体用了 RAGFlow 的什么，没用什么</h2>
    <p class="hint">边界必须清楚：我们复用它的<b>数据与模型</b>，不走它的<b>处理流程</b>。</p>

    <table>
      <thead><tr><th style="width:26%">RAGFlow 的东西</th><th style="width:14%">用不用</th><th>说明</th></tr></thead>
      <tbody>
        <tr><td>MinIO 对象存储</td><td style="color:var(--ok)">用</td>
            <td>原文件写进它的桶，按知识库分目录，与它自己上传的文件放在一起</td></tr>
        <tr><td>Elasticsearch 索引</td><td style="color:var(--ok)">用</td>
            <td>切块内容和向量写进它的索引，字段格式完全一致——这是它的检索和知识图谱的数据来源</td></tr>
        <tr><td>向量模型服务</td><td style="color:var(--ok)">用</td>
            <td>本来就是独立部署的服务，直接调用，生成的向量与它完全一致</td></tr>
        <tr><td>中文分词器</td><td style="color:var(--ok)">用</td>
            <td>用同一个才能保证检索时的匹配效果一致</td></tr>
        <tr><td>文档元数据表</td><td style="color:var(--ok)">用</td>
            <td>写入文档记录，这样在 RAGFlow 界面里能看到我们导入的文档</td></tr>
        <tr><td>知识图谱构建</td><td style="color:var(--ok)">用</td>
            <td>通过它的接口触发，它从 Elasticsearch 读我们写的内容建图</td></tr>
        <tr><td style="color:var(--muted)">文档解析流程</td><td style="color:var(--muted)">不用</td>
            <td style="color:var(--muted)">改由我们自己做，原因见"方案与取舍"</td></tr>
        <tr><td style="color:var(--muted)">任务队列与调度</td><td style="color:var(--muted)">不用</td>
            <td style="color:var(--muted)">它的队列不对外开放，无法读写状态，我们自建</td></tr>
        <tr><td style="color:var(--muted)">它的任务状态表</td><td style="color:var(--muted)">不写</td>
            <td style="color:var(--muted)">那是它内部处理进程的字段，双方同时写会冲突</td></tr>
      </tbody>
    </table>

    <p style="color:var(--muted);font-size:13px;margin-top:14px">
      <b>一句话</b>：把 RAGFlow 当作<b>存储和模型的提供方</b>，而不是<b>流程的执行方</b>。
      这样既保证数据互通、下游功能可用，又让处理过程完全在我们掌控之中。
    </p>
  </div>

  <div class="panel">
    <h2>做过哪些实际测试</h2>
    <p class="hint">不同层次回答不同问题，越靠下越接近真实环境。</p>
    <table>
      <thead><tr><th style="width:20%">层次</th><th style="width:12%">数量</th><th>验证什么</th></tr></thead>
      <tbody>
        <tr><td>单元与集成</td><td class="num">203</td>
            <td>状态流转、暂停真的中断、恢复不重复上传、混合文件类型分派、大文档、乱码输入</td></tr>
        <tr><td><b>契约测试</b></td><td class="num">13</td>
            <td><b>在真实服务器上</b>验证我们写的数据 RAGFlow 认不认：文档可见、检索命中、格式无偏差</td></tr>
        <tr><td>数据库测试</td><td class="num">15</td>
            <td>连真实 MySQL：中文、并发、重启后状态不丢</td></tr>
        <tr><td>批量真机</td><td class="num">—</td>
            <td>服务器上真跑批量：全部成功、一份失败其余不受影响、失败可重试</td></tr>
        <tr><td>知识图谱验证</td><td class="num">—</td>
            <td>对我们写入的内容成功建图，四个环节逐层检查</td></tr>
        <tr><td>性能压测</td><td class="num">—</td>
            <td>不同并发下的吞吐与各阶段耗时（见「实测数据」）</td></tr>
      </tbody>
    </table>
    <p style="color:var(--muted);font-size:13px;margin-top:14px">
      其中<b>契约测试</b>最值得说明：它专门盯「RAGFlow 升级后是否还认我们的数据格式」。
      如果哪天它改了格式，我们的文档会从检索里悄悄消失，而其他测试全部照常通过——
      只有这一层能提前发现。
    </p>
  </div>
</section>

<!-- ============ 数据存储 ============ -->
<section id="store">
  <div class="panel">
    <h2>任务状态存在哪里</h2>
    <p class="hint">存在 MySQL 中，独立的 <code>gcn_ingest</code> 库，与 RAGFlow 自己的库完全隔离。</p>

    <div class="why">
      <h3>为什么必须落库，而不是放在内存里</h3>
      <p>放内存的话，服务一重启，正在处理的批次、已完成的记录、各阶段耗时就全部消失，
         导入到哪一步了无从查起。落库之后，<b>重启前后状态完全一致</b>——这一点已实测验证：
         杀掉服务再启动，作业的状态和四个阶段的耗时逐字段读回，没有任何丢失。</p>
    </div>

    <div class="why">
      <h3>为什么单独建库，不放进 RAGFlow 的库</h3>
      <p>两套数据各自演进：它升级迁移表结构时不会碰到我们的表，我们清理数据时也不会误伤它。
         同时避免表名冲突。</p>
    </div>
  </div>

  <div class="panel">
    <h2>三张表的职责</h2>
    <p class="hint">按"一次导入 → 每份文档 → 每个阶段"三层组织，逐层展开。</p>

    <table>
      <thead><tr><th style="width:18%">表</th><th style="width:22%">一行代表</th><th>为什么这样分</th></tr></thead>
      <tbody>
        <tr>
          <td><code>ingest_job</code></td>
          <td>一次批量导入</td>
          <td>记录这批文档送往哪个知识库、什么选项、整体状态</td>
        </tr>
        <tr>
          <td><code>ingest_task</code></td>
          <td>其中一份文档</td>
          <td><b>每份文档一个独立状态机</b>——这是"一份失败不影响其余"的实现基础。
              重试次数、当前阶段、失败原因都记在这一层</td>
        </tr>
        <tr>
          <td><code>ingest_step</code></td>
          <td>一份文档的一个阶段</td>
          <td>解析 / 切块 / 向量化 / 索引各一行，记开始时间、结束时间、耗时。
              项目经理要的"每个阶段的时间记录"就在这里</td>
        </tr>
      </tbody>
    </table>

    <p style="color:var(--muted);font-size:13px;margin-top:14px">
      三张表用外键串起来，删除一次导入会自动清理其下所有文档和阶段记录，不留孤儿数据。
      <code>ingest_step</code> 上有唯一约束（同一文档同一阶段只能有一行），
      保证并发处理时不会重复写入。
    </p>
  </div>

  <div class="panel">
    <h2>实际表结构 <span style="font-weight:400;color:var(--muted);font-size:12.5px">
      — 直接读自运行中的数据库，不是文档里抄的</span></h2>
    <p class="hint">接口 <code class="api"><span class="m">GET</span> /ingest/schema</code>，
       从 information_schema 实时查询，保证与真实结构一致。</p>
    <div id="schema">加载中…</div>
  </div>

  <div class="panel">
    <h2>文档状态如何流转</h2>
    <p class="hint">五种状态与项目经理原型中的口径一致，也与 RAGFlow 自身的状态定义对齐。</p>
    <div style="font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12.5px;
                background:#0d1016;padding:16px;border-radius:6px;color:#9fb3c8;line-height:2">
      排队 ──▶ 进行中 ──▶ <span style="color:#35c56a">完成</span><br>
      &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│<br>
      &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;├──▶ <span style="color:#ff5f56">失败</span> ──[重试]──▶ 排队<br>
      &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;├──▶ <span style="color:#f5a623">已暂停</span> ──[恢复]──▶ 进行中<br>
      &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└──▶ <span style="color:#9aa3ad">已停止</span>（终态，不可恢复）
    </div>
    <p style="color:var(--muted);font-size:13px;margin-top:12px">
      状态流转有严格校验：不允许跳跃（比如"排队"不能直接变"完成"），
      终态不允许再变更。这些规则有 37 个测试逐条覆盖。
    </p>
  </div>
</section>

<!-- ============ 3. 实测数据 ============ -->
<section id="data">
  <div class="panel">
    <h2>测试环境：131 服务器的真实情况</h2>
    <p class="hint">所有性能数字都出自这台机器。换环境结论可能不同，因此先说清楚它是什么样。</p>

    <div class="grid2">
      <div>
        <h3 style="font-size:14px;margin:0 0 8px">硬件配置</h3>
        <table>
          <tbody>
            <tr><td style="width:38%">CPU</td><td>64 核 Intel Xeon 6981E-C</td></tr>
            <tr><td>内存</td><td>246 GB</td></tr>
            <tr><td>磁盘</td><td>984 GB，已用 75%（余 236 GB）</td></tr>
            <tr><td><b>GPU</b></td><td style="color:var(--warn)"><b>无</b></td></tr>
          </tbody>
        </table>
      </div>
      <div>
        <h3 style="font-size:14px;margin:0 0 8px">这台机器不是我们独占的</h3>
        <table>
          <tbody>
            <tr><td style="width:52%">同时运行的容器</td><td><b>34 个</b></td></tr>
            <tr><td>其中包括</td><td>RAGFlow、OpenSPG（4个）、<br>DB-GPT、MinerU、WeKnora 等</td></tr>
            <tr><td>Elasticsearch 内存</td>
                <td style="color:var(--warn)"><b>5.97 / 7.52 GB（已用 79%）</b></td></tr>
            <tr><td>向量模型</td><td style="color:var(--warn)">CPU 推理，与他人共享</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="caveat">
      <b>这些限制直接决定了测试结果</b>：
      <br>· <b>无 GPU</b> —— 向量化和 PDF 版面识别都靠 CPU，比有卡环境慢一个量级；
      <br>· <b>Elasticsearch 内存已用近八成</b> —— 这正是索引写入成为瓶颈的物理原因，也是并发加不上去的根源；
      <br>· <b>34 个服务混跑</b> —— 别人的任务会直接影响我们的测试结果。曾出现向量服务被占满
      64 核、负载持续 22 的情况，那段时间我们的导入全部超时。
      <br><br>
      <b>因此</b>：下面的数字是"在这台共享的、无 GPU 的机器上"的表现，
      是当前条件下的真实基线，<b>不代表专用环境下的能力上限</b>。
    </div>
  </div>

  <div class="panel">
    <h2>并发的直接证据：同一批里的 Word 与扫描 PDF</h2>
    <p class="hint">
      2026-08-21 在 131 上真跑的一批，两份文件一次提交。数据直接读自数据库，未做修饰。
    </p>
    <table>
      <thead><tr>
        <th style="width:16%">阶段</th>
        <th style="width:20%">Word 文档 .docx</th>
        <th style="width:20%">扫描件 .pdf</th>
        <th>说明</th>
      </tr></thead>
      <tbody>
        <tr style="background:#12291b">
          <td><b>开始时刻</b></td>
          <td class="num"><b>02:22:17</b></td><td class="num"><b>02:22:17</b></td>
          <td style="color:var(--ok)"><b>同一秒开始 —— 这就是并发，不是排队</b></td></tr>
        <tr><td>解析</td><td class="num">0.18s（194 段）</td>
            <td class="num" style="color:var(--warn)">96.8s（626 段）</td>
            <td>Word 是结构化格式直接读；PDF 只有像素，要走 MinerU 版面识别 + 文字识别，
                而且是 CPU 推理。<b>差了 530 倍</b></td></tr>
        <tr><td>切块</td><td class="num">0.03s（90 块）</td><td class="num">0.02s（252 块）</td>
            <td>纯文本处理，可忽略不计</td></tr>
        <tr><td>向量化</td><td class="num">16.5s（90 块）</td>
            <td class="num" style="color:var(--warn)">68.8s（252 块）</td>
            <td>块数多 2.8 倍，耗时多 4.2 倍——向量服务是共享的 CPU 推理，
                两份同时在算，互相排队</td></tr>
        <tr><td>索引</td><td class="num">9.1s（90 块）</td><td class="num">1.3s（252 块）</td>
            <td style="color:var(--warn)">块更少反而慢 7 倍 —— 这正是"索引偶发长尾"那个待查问题的一次现场</td></tr>
        <tr style="border-top:2px solid var(--line)">
          <td><b>单份合计</b></td><td class="num"><b>25.9s</b></td>
          <td class="num"><b>166.9s</b></td>
          <td><b>快慢相差 6.4 倍</b>——这就是"看起来像串行"的全部原因</td></tr>
      </tbody>
    </table>

    <div class="grid2" style="margin-top:16px">
      <div>
        <h3 style="font-size:14px;margin:0 0 6px">并发实际省了多少</h3>
        <p style="color:var(--muted);font-size:13px">
          这批的总耗时是 <b style="color:var(--text)">167 秒</b>（02:22:17 → 02:25:04），
          等于最慢那一份的耗时。如果一份一份来，需要 25.9 + 166.9 =
          <b style="color:var(--text)">193 秒</b>。
        </p>
        <p style="font-size:13px"><b>省下 26 秒（13%）</b></p>
      </div>
      <div>
        <h3 style="font-size:14px;margin:0 0 6px">为什么只省了 13%</h3>
        <p style="color:var(--muted);font-size:13px">
          并发的收益<b style="color:var(--text)">受限于最慢的那一份</b>：
          只有两份、且其中一份占了绝大部分时间时，并行的空间本来就小。
          文档数量越多、单份耗时越接近，并发的收益越明显。
        </p>
      </div>
    </div>

    <div class="caveat">
      <b>这组数据说明的另一件事</b>：耗时的大头不在我们的编排逻辑上，
      而在<b>两个 CPU 推理环节</b>——PDF 的版面识别（96.8s）和向量化（68.8s），
      两者加起来占了 99%。<b>要让导入更快，方向是给这两个环节配 GPU 或独立部署，
      而不是继续加并发。</b>
    </div>
  </div>

  <div class="panel">
    <h2>性能：在当前这台机器上，并发不是越高越好</h2>
    <p class="hint">10 份文档，选在机器相对空闲时（负载 1.33）实测，避开他人任务干扰。</p>
    <table>
      <thead><tr><th>并发数</th><th>总耗时</th><th>吞吐</th><th>索引阶段 p50</th><th>结论</th></tr></thead>
      <tbody>
        <tr><td class="num">1</td><td class="num">19.7s</td><td class="num">0.51 份/秒</td>
            <td class="num">59ms</td><td style="color:var(--muted)">基准</td></tr>
        <tr style="background:#12291b"><td class="num"><b>3</b></td><td class="num"><b>17.1s</b></td>
            <td class="num"><b>0.58 份/秒</b></td><td class="num"><b>71ms</b></td>
            <td style="color:var(--ok)">最优，当前默认值</td></tr>
        <tr><td class="num">6</td><td class="num">31.1s</td><td class="num">0.32 份/秒</td>
            <td class="num" style="color:var(--err)">27488ms</td>
            <td style="color:var(--err)">比并发 1 还慢 58%</td></tr>
      </tbody>
    </table>
    <p style="color:var(--muted); font-size:13px; margin-top:12px">
      并发提到 6 时，索引阶段耗时暴涨 387 倍——下游的 Elasticsearch、数据库、向量服务
      开始互相争抢，排队的代价超过了并行的收益。<b>在当前这台机器上，盲目加并发会让系统更慢。</b>
      <br><br>
      <b>为什么是 3 而不是别的数</b>：受限于 Elasticsearch 只分到 7.5GB 内存（已用 79%）、
      向量服务是共享的 CPU 推理。<b>这个最优值属于这台机器</b>——
      换成有 GPU、Elasticsearch 内存充足的专用环境，最优并发会明显更高，需要重新标定。
    </p>
    <div class="caveat">
      <b>数据口径说明</b>：更早一批数据是在服务器负载 22（32 核）时测的，当时得出
      「并发无效」的结论是错的，已作废。所有性能数字都必须标注测量时的机器负载，
      否则不可比。
    </div>
  </div>

  <div class="panel">
    <h2>找到并解决的两个性能问题</h2>
    <div class="grid2">
      <div>
        <h3 style="font-size:14px;margin:0 0 6px">写入等待索引刷新</h3>
        <p style="color:var(--muted);font-size:13px">
          每次写入都同步等待 Elasticsearch 刷新索引，无论写 1 条还是 50 条都固定约 900ms，
          占了总耗时的四分之三。批量导入并不需要「写完立刻能搜到」。
        </p>
        <p style="font-size:13px"><b>719ms → 14ms，快 50 倍</b></p>
      </div>
      <div>
        <h3 style="font-size:14px;margin:0 0 6px">首份文档承担全部启动开销</h3>
        <p style="color:var(--muted);font-size:13px">
          初始化连接和模型注册表要 33 秒，原本由第一份文档承担，导致它比后续文档慢 345 倍。
          改为服务启动时预热。
        </p>
        <p style="font-size:13px"><b>首份 14.7s → 与其余一致的 60~80ms</b></p>
      </div>
    </div>
  </div>

  <div class="panel">
    <h2>质量保障</h2>
    <div class="counts" style="margin-bottom:14px">
      <div><b>203</b><small>单元与集成测试</small></div>
      <div><b>13</b><small>契约测试（真实服务器）</small></div>
      <div><b>15</b><small>数据库测试（真实 MySQL）</small></div>
    </div>
    <p style="color:var(--muted);font-size:13px">
      其中「契约测试」专门盯一件事：我们写入的数据格式与 RAGFlow 的理解是否仍然一致。
      若它升级后改了格式，我们的文档会从它的检索里悄悄消失，而普通测试全部照常通过——
      只有这层能发现。
    </p>
    <div class="caveat">
      <b>尚未验证的部分</b>：目前压测到 10 份文档规模，100 份以上未做；
      需求背景提到的 30 万份规模不能由当前数据外推。
      另有一个待查问题：索引阶段偶发长尾（十份里约有一份耗时 14 秒），已排除启动开销，
      原因待定位。
    </div>
  </div>
</section>

<!-- ============ 瓶颈与下一步 ============ -->
<section id="next">
  <div class="panel">
    <h2>当前进展：一句话结论</h2>
    <p style="font-size:14px;line-height:1.9">
      项目经理提的第 1 点（批量上传、阶段计时、随时暂停停止重试、读写队列状态、提供接口）
      <b style="color:var(--ok)">功能已全部实现并在服务器上跑通</b>，
      <b>8 个接口可用</b>，状态落库、重启不丢，231 项测试通过。<br>
      <span style="color:var(--warn)">目前验证到 10 份文档规模</span>，
      更大规模需要继续压测，不能由当前数据外推。
    </p>
  </div>

  <div class="panel">
    <h2>当前瓶颈</h2>
    <p class="hint">按对交付的影响排序，都是实测发现的，不是推测。</p>

    <div class="step">
      <div class="idx" style="background:var(--warn)">1</div>
      <div>
        <h3>索引写入偶发变慢（十份里约有一份）</h3>
        <p>正常情况写入只要 70 毫秒，但每十份左右会出现一份要 14 秒，相差两百倍。
           服务启动预热已经排除，说明另有原因。</p>
        <p><b>影响</b>：单份感知不明显，但规模上去后会拉低整体吞吐。</p>
        <p><b>下一步怎么查</b>：三个方向逐一排除——数据库连接争抢、
           Elasticsearch 批量写入的内部重试、对象存储的写入抖动。</p>
      </div>
    </div>

    <div class="step">
      <div class="idx" style="background:var(--warn)">2</div>
      <div>
        <h3>并发数需要按环境标定，不能照搬</h3>
        <p>实测并发 3 最快，并发 6 反而比不并发还慢 58%——下游服务开始互相争抢。
           当前默认值 3 恰好合适，<b>但这是这台机器、这种文档大小下的结论</b>。</p>
        <p><b>影响</b>：换服务器或文档明显变大后，默认值可能不再合适。</p>
        <p><b>下一步怎么做</b>：把并发数做成可配置（已支持），
           上线前在目标环境跑一次阶梯测试确定取值。</p>
      </div>
    </div>

    <div class="step">
      <div class="idx" style="background:var(--warn)">3</div>
      <div>
        <h3>向量化依赖共享服务，且该服务在 CPU 上运行</h3>
        <p>向量模型是这台机器上共用的服务，此前曾出现它被其他任务占满 64 核、
           连续多天负载 22 的情况，那期间我们的导入全部超时。</p>
        <p><b>影响</b>：不是我们能控制的环节，但直接决定导入速度。</p>
        <p><b>下一步怎么做</b>：短期加重试与降级提示；
           长期看，若要支撑大规模导入，向量服务需独立部署或改用 GPU。</p>
      </div>
    </div>

    <div class="step">
      <div class="idx" style="background:var(--warn)">4</div>
      <div>
        <h3>队列在 MySQL 表里，目前只能单实例运行</h3>
        <p>后台 worker 每 2 秒扫一次任务表取活。这套做法让"读写队列状态"变得很自然，
           但<b>没有跨进程的抢锁保护</b>——同时起两个服务进程，会有两边抢同一份文档处理的风险。</p>
        <p><b>影响</b>：单机吞吐没问题，但<b>不能靠加机器来扩容</b>。
           当前规模（十份级）完全够用，千份级要多机并行时会挡路。</p>
        <p><b>下一步怎么做</b>：换 Redis（或 RabbitMQ）做队列，MySQL 继续留作阶段耗时与
           状态的账本——队列归队列、账本归账本。改动集中在调度器一层，
           接口和表结构不动。理由与代价详见「技术栈」页。</p>
      </div>
    </div>

    <div class="step">
      <div class="idx" style="background:var(--err)">5</div>
      <div>
        <h3>根本约束：131 是一台共享的开发机，不是生产环境</h3>
        <p>这台机器上同时跑着 <b>34 个容器</b>——RAGFlow、OpenSPG 四件套、DB-GPT、
           MinerU、WeKnora 等。资源分配的结果是：</p>
        <ul>
          <li><b>Elasticsearch 只分到 7.5GB 内存，已用 79%</b> —— 索引写入慢的物理原因</li>
          <li><b>整机没有 GPU</b> —— 向量化和 PDF 版面识别只能靠 CPU</li>
          <li><b>磁盘已用 75%</b>（余 236GB）—— 大规模导入前需要先评估容量</li>
          <li><b>他人的任务会干扰我们</b> —— 测试必须挑机器空闲时做，否则数据不可信</li>
        </ul>
        <p><b>这意味着</b>：当前所有性能数字都是"在受限的共享环境下"取得的，
           是可靠的下限参考，但<b>不代表系统能力的上限</b>。
           要给出生产环境的容量承诺，需要在目标硬件上重新测量。</p>
      </div>
    </div>
  </div>

  <div class="panel">
    <h2>规模上去之后，瓶颈会出现在哪</h2>
    <p class="hint">按需求背景提到的规模推演，标注哪些是已知、哪些需要验证。</p>

    <table>
      <thead><tr>
        <th style="width:14%">规模</th><th style="width:26%">预计瓶颈</th>
        <th style="width:16%">把握程度</th><th>应对方向</th>
      </tr></thead>
      <tbody>
        <tr>
          <td><b>百份级</b></td>
          <td>索引写入的偶发长尾被放大</td>
          <td style="color:var(--ok)">较有把握</td>
          <td>先定位长尾原因；批量写入可进一步合并</td>
        </tr>
        <tr>
          <td><b>千份级</b></td>
          <td>向量化服务成为主要排队点</td>
          <td style="color:var(--warn)">需验证</td>
          <td>向量服务扩容或换 GPU；导入分时段错峰</td>
        </tr>
        <tr>
          <td><b>万份级</b></td>
          <td>知识图谱构建成本急剧上升</td>
          <td style="color:var(--err)">未验证</td>
          <td>按设备或系统分域建图，不追求全局一张大图；
              图谱构建与文档导入解耦，分批进行</td>
        </tr>
        <tr>
          <td><b>三十万份</b></td>
          <td>存储容量、索引规模、图谱规模三者叠加</td>
          <td style="color:var(--err)">不能外推</td>
          <td>需要专项容量评估，涉及硬件规划，
              不是应用层优化能解决的</td>
        </tr>
      </tbody>
    </table>

    <p style="color:var(--muted);font-size:13px;margin-top:14px">
      <b>需要说明的前提</b>：上述推演都建立在"当前 131 这台共享机器"的资源条件下。
      如果生产环境配备 GPU、Elasticsearch 有独立且充足的内存、向量服务不与他人共享，
      各级瓶颈出现的时间点会明显推后，最优并发数也会更高。
      <b>硬件条件是这里最大的变量</b>。
    </p>
    <table style="display:none">
      <tbody>
      </tbody>
    </table>

    <div class="caveat">
      <b>诚实说明</b>：目前只压测到 10 份文档。上表中"千份级"以上都是基于已知机制的推演，
      不是实测结论。要给出可承诺的容量数字，必须按 100 → 1000 → 10000 逐级实测，
      每一级都可能暴露上一级看不到的问题。
    </div>
  </div>

  <div class="panel">
    <h2>下一步计划</h2>
    <table>
      <thead><tr><th style="width:10%">优先级</th><th style="width:30%">事项</th><th>为什么</th></tr></thead>
      <tbody>
        <tr><td style="color:var(--err)">高</td><td>定位索引写入长尾</td>
            <td>规模化前必须查清，否则百份级会被放大</td></tr>
        <tr><td style="color:var(--err)">高</td><td>百份级压测</td>
            <td>当前只到 10 份，需要下一个量级的真实数据支撑容量判断</td></tr>
        <tr><td style="color:var(--warn)">中</td><td>PDF 与扫描件端到端验证</td>
            <td>MinerU 已接通并验证可用，但尚未用真实的核电扫描件跑过</td></tr>
        <tr><td style="color:var(--warn)">中</td><td>知识图谱构建纳入批量流程</td>
            <td>目前建图需单独触发，应作为导入选项自动衔接</td></tr>
        <tr><td style="color:var(--warn)">中</td><td>队列换 Redis，支持多机消费</td>
            <td>当前 MySQL 表 + 轮询只能单实例跑，挡住横向扩容。
                触发条件是千份级压测暴露单机吞吐不足；MySQL 保留作阶段耗时账本</td></tr>
        <tr><td style="color:var(--muted)">低</td><td>失败自动重试策略</td>
            <td>现在失败需人工点重试，可加"自动重试若干次后转人工"</td></tr>
        <tr><td style="color:var(--muted)">低</td><td>接口鉴权</td>
            <td>当前内网无鉴权，对外提供前需补充</td></tr>
      </tbody>
    </table>
  </div>
</section>

</main>

<script>
const $ = s => document.querySelector(s);
let jobIds = [], timer = null;

document.querySelectorAll('nav button').forEach(b => b.onclick = () => {
  document.querySelectorAll('nav button').forEach(x => x.classList.remove('on'));
  document.querySelectorAll('section').forEach(x => x.classList.remove('on'));
  b.classList.add('on');
  $('#' + b.dataset.tab).classList.add('on');
});

function log(msg) {
  const el = $('#log');
  el.textContent = new Date().toLocaleTimeString() + '  ' + msg + '\\n' + el.textContent;
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(path + ' -> HTTP ' + r.status);
  return r.json();
}

async function health() {
  try {
    await api('/ingest/queue');
    $('#dot').className = 'dot up';
    $('#health').textContent = '服务正常 · ' + location.host;
  } catch {
    $('#dot').className = 'dot';
    $('#health').textContent = '服务不可达';
  }
}

// ---- 知识库下拉 ----
async function loadDatasets() {
  const sel = $('#kb');
  try {
    const d = await api('/ingest/datasets');
    if (!d.datasets || !d.datasets.length) {
      sel.innerHTML = '<option value="">（未取到知识库列表，可手工填写 ID）</option>';
      return;
    }
    sel.innerHTML = d.datasets.map(k =>
      `<option value="${k.id}">${k.name} — ${k.doc_num || 0} 份文档</option>`).join('');
  } catch {
    sel.innerHTML = '<option value="">（列表接口不可用）</option>';
  }
}

// ---- 真实文件上传 ----
let chosen = [];
const drop = $('#drop'), picker = $('#picker');

drop.onclick = () => picker.click();
drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
drop.ondragleave = () => drop.classList.remove('over');
drop.ondrop = e => {
  e.preventDefault(); drop.classList.remove('over');
  addFiles(e.dataTransfer.files);
};
picker.onchange = () => addFiles(picker.files);

function addFiles(list) {
  chosen = chosen.concat(Array.from(list));
  $('#picked').innerHTML = chosen.map((f, i) =>
    `<span class="chip">${f.name} · ${(f.size / 1024).toFixed(0)}KB
      <a href="#" onclick="dropFile(${i});return false" style="color:var(--muted)">×</a></span>`
  ).join('');
  $('#upload').disabled = chosen.length === 0;
}

function dropFile(i) {
  chosen.splice(i, 1);
  addFiles([]);
}

$('#upload').onclick = async () => {
  const kb = $('#kb').value.trim();
  if (!kb) { log('请先选择知识库'); return; }
  $('#upload').disabled = true;
  const fd = new FormData();
  fd.append('kb_id', kb);
  fd.append('build_graph', $('#graph').checked ? 'true' : 'false');
  chosen.forEach(f => fd.append('files', f, f.name));
  try {
    const t0 = performance.now();
    const res = await api('/ingest/upload', { method: 'POST', body: fd });
    const ms = (performance.now() - t0).toFixed(0);
    jobIds.push(res.job_id);
    log(`已上传 ${res.accepted} 份 → 作业 #${res.job_id}，接口 ${ms}ms 返回，后台处理中`);
    chosen = []; addFiles([]);
    refresh();
  } catch (e) {
    log('上传失败：' + e.message);
  } finally {
    $('#upload').disabled = chosen.length === 0;
  }
};

// ---- 内置样例（快速演示批量与失败隔离，无需准备文件）----
$('#sample').onclick = async () => {
  const kb = $('#kb').value.trim();
  if (!kb) { log('请先选择知识库'); return; }
  try {
    const files = [];
    for (let i = 0; i < 5; i++) {
      files.push({ name: `样例_${i}.txt`, path_or_url: `__demo__:${i}` });
    }
    files.push({ name: '损坏样例.zip', path_or_url: '__demo_bad__' });
    const t0 = performance.now();
    const res = await api('/ingest/jobs', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kb_id: kb, files, options: {}, priority: 0 })
    });
    const ms = (performance.now() - t0).toFixed(0);
    jobIds.push(res.job_id);
    log(`样例作业 #${res.job_id}：5 份正常 + 1 份故意失败 — 接口 ${ms}ms 返回`);
    refresh();
  } catch (e) { log('提交失败：' + e.message); }
};

// ---- 表结构 ----
async function loadSchema() {
  try {
    const d = await api('/ingest/schema');
    if (d.backend !== 'MySQL') {
      $('#schema').innerHTML = `<p style="color:var(--warn)">${d.note || d.backend}</p>`;
      return;
    }
    $('#schema').innerHTML = d.tables.map(t => {
      if (t.error) return `<p style="color:var(--err)">${t.table}: ${t.error}</p>`;
      const rows = t.columns.map(c => `<tr>
        <td class="${c.key === 'PRI' ? 'col-key' : ''}">${c.name}${c.key === 'PRI' ? ' 🔑' : ''}</td>
        <td style="color:var(--muted)">${c.type}</td>
        <td style="color:var(--muted)">${c.comment || ''}</td></tr>`).join('');
      return `<div style="margin-bottom:18px">
        <h3 style="font-size:13.5px;margin:0 0 8px">
          <code>${t.table}</code>
          <span style="font-weight:400;color:var(--muted)">· 当前 ${t.rows} 行 · ${t.columns.length} 个字段</span>
        </h3>
        <table class="schema-tbl">
          <thead><tr><th style="width:26%">字段</th><th style="width:24%">类型</th><th>说明</th></tr></thead>
          <tbody>${rows}</tbody></table></div>`;
    }).join('');
  } catch (e) {
    $('#schema').innerHTML = `<p style="color:var(--err)">读取失败：${e.message}</p>`;
  }
}

const STATUS_CN = { pending:'排队', running:'进行中', succeeded:'完成',
                    failed:'失败', cancelled:'已停止', paused:'已暂停' };
const STAGES = ['parse', 'chunk', 'embed', 'index'];
const STAGE_CN = { parse:'解析', chunk:'切块', embed:'向量化', index:'索引' };

// 毫秒读起来费劲：超过一秒就换成秒，PDF 动辄十万毫秒。
function fmtMs(ms) {
  return ms >= 1000 ? (ms / 1000).toFixed(1) + 's' : ms + 'ms';
}

async function refresh() {
  try {
    const q = await api('/ingest/queue');
    $('#counts').innerHTML = Object.entries(q.counts).map(([k, v]) =>
      `<div><b>${v}</b><small>${STATUS_CN[k] || k}</small></div>`).join('');
  } catch {}

  const rows = [];
  for (const id of jobIds.slice(-4)) {
    let job;
    try { job = await api('/ingest/jobs/' + id); } catch { continue; }
    for (const t of job.tasks) {
      const total = t.stages.reduce((s, x) => s + (x.duration_ms || 0), 0);
      const pipe = STAGES.map(name => {
        const st = t.stages.find(x => x.step_name === name);
        const cls = st ? (st.status === 'done' ? 'done'
                        : st.status === 'running' ? 'running'
                        : st.status === 'failed' ? 'failed' : '') : '';
        const ms = st && st.duration_ms != null ? fmtMs(st.duration_ms) : '';
        return `<div class="stg ${cls}" title="${STAGE_CN[name]} ${ms}"></div>`;
      }).join('');
      const done = ['succeeded', 'cancelled'].includes(t.status);
      // 开始时刻 = 最早一个阶段的开始时间。同批任务时刻相同即为并发在跑。
      const starts = t.stages.map(x => x.started_at).filter(Boolean).sort();
      const startTxt = starts.length ? starts[0].slice(11, 19) : '—';
      rows.push(`<tr>
        <td title="${t.doc_name}">${t.doc_name.slice(0, 26)}</td>
        <td><span class="tag ${t.status}">${STATUS_CN[t.status] || t.status}</span></td>
        <td class="num" title="${starts[0] || ''}">${startTxt}</td>
        <td><div class="pipe">${pipe}</div></td>
        <td class="num">${total ? fmtMs(total) : '—'}</td>
        <td>
          ${t.status === 'running' ? `<button class="mini" onclick="ctl(${t.task_id},'pause')">暂停</button>` : ''}
          ${t.status === 'paused' ? `<button class="mini" onclick="ctl(${t.task_id},'resume')">恢复</button>` : ''}
          ${t.status === 'failed' ? `<button class="mini" onclick="ctl(${t.task_id},'retry')">重试</button>` : ''}
          ${done ? '' : `<button class="mini" onclick="ctl(${t.task_id},'cancel')">取消</button>`}
          ${t.error ? `<span style="color:var(--err);font-size:11px" title="${t.error}">失败原因 ⓘ</span>` : ''}
        </td></tr>`);
    }
  }
  $('#rows').innerHTML = rows.length ? rows.join('')
    : '<tr><td colspan="6" style="color:var(--muted)">尚无任务，先提交一批。</td></tr>';
}

async function ctl(taskId, action) {
  try {
    await api(`/ingest/tasks/${taskId}/${action}`, { method: 'POST' });
    log(`任务 ${taskId} → ${action}`);
    refresh();
  } catch (e) { log(`任务 ${taskId} ${action} 失败：${e.message}`); }
}

health();
loadDatasets();
loadSchema();
refresh();
timer = setInterval(() => { health(); refresh(); }, 2000);
</script>
</body>
</html>
"""
