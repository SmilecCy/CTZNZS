# 项目架构文档

| 项 | 内容 |
|---|---|
| 文档版本 | v3.0（融合版） |
| 文档状态 | 已评审，可开发 |
| 更新日期 | 2026-09-29 |
| 基础架构 | 分层架构 + FastAPI + React + Streamlit |
| 当前阶段 | M0~M5 已交付（内部工具链路完整），M6+ 建设中（司法考试·React 前端） |

---

## 〇、项目演进路线

本系统分两个阶段建设，当前处于第二阶段中期。

### 阶段一：单体 Streamlit 内部工具（M0~M5，已交付）

```
app.py（Streamlit 入口，进程内调用）
  └── app/
      ├── frontend/     # 6 个标签页：资料管理 / 预热与题库更新 / 练习模式 / 错题集 / 记忆闪卡 / 系统自检
      ├── ai/           # LLM 客户端 · 出题引擎 · 判分 · 章节匹配 · 分类器 · 搜索
      ├── pipeline/     # 文档解析 · 结构化切分 · 向量索引 · 编排调度
      ├── database/     # MySQL 连接池 · Redis · 缓存 · 各域 DAO
      ├── auth/         # JWT · bcrypt · 用户管理
      └── prompts/      # 提示词库（与代码分离，按版本管理）
```

- **数据库**：SQLite → MySQL 8.0（v4.0 迁移完成）
- **向量库**：ChromaDB → FAISS
- **课程**：侵权责任法 / 习概 → 商法（司法考试方向）
- **前端**：纯 Streamlit，6 个标签页，管理员/学生共用

### 阶段二：分层架构生产系统（M6+，建设中）

```
React + TypeScript + Ant Design（web/）    ← 学生正式前端
Streamlit（app.py）                         ← 管理员内部工具
        │
FastAPI（api/main.py）                      ← 统一接口层
        │
app/ai/ app/pipeline/ app/database/        ← 业务层（复用阶段一）
        │
MySQL 8.0 + Redis 7 + FAISS + 文件系统      ← 基础设施
```

- **新增**：React 学生端（三栏练习页）、聊天出题（Function Calling）、教材/附属资料双链路
- **复用**：阶段一的全部业务层代码（出题引擎、判分、资料处理、题库管理等）
- **Streamlit 降级**：从"唯一前端"变为"管理员内部工具"

---

## 一、项目概述

### 1.1 项目定位

面向司法考试考生的智能出题与练习系统。核心设计是**题库优先、LLM 兜底**：日常出题直接命中本地题库，不调用大模型，成本可控、结果可复现、来源可追溯。

系统同时服务于两类用户：
- **学生**：通过 React 前端进行对话式出题、练习、错题管理
- **管理员**：通过 Streamlit 内部工具进行课程/章节/资料/题库管理

### 1.2 核心价值

| 价值 | 说明 |
|---|---|
| 题库优先 | 命中题库不调 LLM，成本降 ≥ 50% |
| 对话式出题 | 学生说"第一章 商法概述，10道选择题"即可出题 |
| 语义切片 | 附属资料按语义切分，不切断知识点 |
| 章节归属 | 每个 chunk 明确归属章节，检索不串题 |
| 教材唯一 | 每课程一份教材，转 MD 抽章节 |
| 预热填补 | 首次使用一键填满题库，后续出题 0 成本 |
| 配额可控 | 每章节选择题 ≤ 50，简答题 ≤ 10 |
| 来源可追溯 | 每道题标注入库来源（📚题库 / 🤖新生成），所有 LLM 调用入审计日志 |

### 1.3 非目标（本期不做）

- 不做"一键换一批"强制生成
- 不做跨会话长期记忆
- 不做教材入向量库（教材仅用于抽章节 + 按章节读文本）
- 不做软删除（删题即硬删）

---

## 二、用户角色与权限

| 角色 | 权限 |
|---|---|
| 学生 | 聊天出题、作答、错题、收藏、笔记、删除题库题目 |
| 管理员 | 课程/章节/资料/题库管理、预热与题库更新、系统自检 |

### 权限矩阵

| 功能 | 学生 | 管理员 |
|---|---|---|
| 聊天出题 | ✅ | ❌ |
| 作答/判分 | ✅ | ❌ |
| 查看错题 | ✅ | ❌ |
| 删除题库题目 | ✅ | ✅ |
| 上传教材 | ❌ | ✅ |
| 上传附属资料 | ❌ | ✅ |
| 抽章节/分类确认 | ❌ | ✅ |
| 题库浏览/废弃 | ❌ | ✅ |
| 预热与题库更新 | ❌ | ✅ |
| 系统自检 | ❌ | ✅ |

---

## 三、系统架构

### 3.1 分层架构

```
┌──────────────────────────────────────────────────────────────────┐
│  表现层（双前端）                                                  │
│  ├── Streamlit（app.py）                                          │
│  │     └── 6 个标签页：资料管理 · 预热与题库更新 · 练习模式        │
│  │                     · 错题集 · 记忆闪卡 · 系统自检              │
│  │     └── 角色：管理员内部工具                                    │
│  │                                                                │
│  └── React + TypeScript + Ant Design（web/）                      │
│        └── 4 个学生页：登录 · 练习 · 错题集 · 学习统计            │
│        └── 9 个后台页：Dashboard · 课程 · 章节 · 资料 · 题库 · 自检│
│        └── 通信：HTTP / REST / JWT                                │
└───────────────────────────┬──────────────────────────────────────┘
                            │
            ┌───────────────┴───────────────┐
            │                               │
     进程内调用（Streamlit）          HTTP / REST / JWT（React）
            │                               │
┌───────────▼───────────────────────────────┴──────────────────────┐
│  接口层（FastAPI）                                                 │
│  ├── /api/auth/*       认证（注册·登录·登出·当前用户）             │
│  ├── /api/user/*       学生接口（课程·章节匹配·出题·作答·错题·统计）│
│  └── /api/admin/*      后台接口（课程·章节·资料·题库·预热·自检）  │
│                                                                │
│  api/                                                           │
│  ├── main.py             FastAPI 应用入口                        │
│  ├── deps.py             依赖注入（get_db / get_current_user）    │
│  ├── schemas.py          请求/响应模型                            │
│  └── routers/                                                    │
│      ├── auth.py         认证路由                                 │
│      ├── user.py         学生端路由                               │
│      └── admin.py        后台管理路由                             │
└───────────────────────────┬──────────────────────────────────────┘
                            │ 进程内调用
┌───────────────────────────▼──────────────────────────────────────┐
│  业务层                                                           │
│                                                                  │
│  app/ai/                  AI 域                                   │
│  ├── llm_client.py        OpenAI 兼容客户端 + JSON 抽取 + 审计    │
│  ├── generator.py         出题引擎主流程（题库优先 + LLM 兜底）    │
│  ├── grader.py            简答题自动评分（LLM 判定 + 人工可覆盖）  │
│  ├── chapter_matcher.py   章节匹配（自然语言 → chapter_id）        │
│  ├── chapter_extractor.py 从教材 MD 抽取章节标题                   │
│  ├── chunk_classifier.py  chunk → 章节分类                        │
│  ├── material_classifier.py 资料类型识别                           │
│  ├── search_tool.py       博查 API 网络搜索（留接口）              │
│  └── embedder.py          BGE-small-zh 向量化（惰性单例）          │
│                                                                  │
│  app/pipeline/            资料处理域                               │
│  ├── doc_parser.py        格式识别 / 文本抽取 / 清洗               │
│  ├── chunker.py           结构化切分 + 元数据 + 页码归属           │
│  ├── indexer.py           FAISS 写入 / 检索 / 统计 / 去重         │
│  ├── orchestrator.py      编排：解析→切分→索引→登记               │
│  ├── parse_worker.py      异步解析线程池                           │
│  └── material_merge.py    资料合并                                 │
│                                                                  │
│  app/database/            数据访问域                               │
│  ├── connection.py        MySQL 连接池（PyMySQL + DBUtils）       │
│  ├── redis.py             Redis 客户端                            │
│  ├── cache.py             缓存原语                                 │
│  ├── courses.py           课程 CRUD                               │
│  ├── chapters.py          章节 CRUD                               │
│  ├── knowledge_points.py  知识点管理                               │
│  ├── materials.py         资料管理                                 │
│  ├── questions.py         题库读写（查库·加权抽取·去重入库·反馈）  │
│  ├── answers.py           作答流水                                 │
│  ├── wrong_book.py        错题集（收录·去重·分类·复习记录）        │
│  ├── favorites.py         题目收藏                                 │
│  ├── notes.py             题目笔记                                 │
│  ├── stats.py             学习统计                                 │
│  └── parse_tasks.py       解析任务管理                             │
│                                                                  │
│  app/auth/                认证域                                   │
│  ├── auth_service.py      JWT 签发/验证                           │
│  └── user_service.py      用户注册/登录（bcrypt）                  │
│                                                                  │
│  app/prompts/             提示词库（与代码分离，按版本管理）        │
│  ├── loader.py            提示词加载器                             │
│  ├── m0_all_ocr_clean_v0.1.txt              OCR 清洗              │
│  ├── m0_all_classify_material_v0.1.txt      资料类型识别           │
│  ├── m0_all_classify_to_chapters_v0.1.txt   chunk 章节分类         │
│  ├── m0_all_extract_chapters_v0.1.txt       教材章节抽取           │
│  ├── m2_all_choice_v0.1.txt                 选择题生成             │
│  ├── m2_tort_short_answer_v0.1.txt          简答题生成（模板 A）   │
│  ├── m2_xigai_short_answer_v0.1.txt         简答题生成（模板 B）   │
│  ├── m2_all_search_and_generate_v0.1.txt    搜索+生成              │
│  ├── m2_all_short_answer_grade_v0.1.txt     简答题判分             │
│  ├── m2_all_extract_questions_v0.1.txt      资料习题抽取           │
│  └── m3_all_chapter_reply_v0.1.txt          聊天回复               │
│                                                                  │
│  app/frontend/            Streamlit 前端层                        │
│  ├── state.py             会话状态集中管理 + 课程切换隔离          │
│  ├── sidebar.py           侧边栏：知识点 / 难度 / 索引状态         │
│  ├── onboarding.py        首次启动引导                             │
│  ├── styles.py            题目主体字号（改字号只改这里）           │
│  ├── tab_materials.py     ① 资料管理                              │
│  ├── tab_warmup.py        ② 预热与题库更新（5 个板块）             │
│  ├── tab_practice.py      ③ 练习模式                              │
│  ├── tab_wrongbook.py     ④ 错题集                                │
│  ├── tab_memory.py        ⑤ 记忆闪卡                              │
│  └── tab_selftest.py      ⑥ 系统自检                              │
│                                                                  │
│  app/config.py            全局配置（单一事实来源）                  │
└───────────────────────────┬──────────────────────────────────────┘
                            │ 抽象数据访问
┌───────────────────────────▼──────────────────────────────────────┐
│  数据访问层                                                        │
│  ├── app/database/connection.py   MySQL 连接池                    │
│  ├── app/database/redis.py        Redis 客户端                    │
│  ├── app/database/cache.py        缓存原语                         │
│  ├── app/pipeline/indexer.py      FAISS 向量库                    │
│  └── app/ai/embedder.py           向量化模型（BGE-small-zh）      │
└───────────────────────────┬──────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┬──────────────┐
        ▼                   ▼                   ▼              ▼
     MySQL 8.0              Redis 7             FAISS         文件系统
   （持久存储）            （缓存）           （向量库）   （data/uploads/
                                                          data/markdown/）
```

### 3.2 分层铁律

| 规则 | 说明 |
|---|---|
| 上层调下层，不反向 | `api/` 调 `app/`，反之不行 |
| 业务层不感知传输 | `app/` 不出现 HTTP、Request、JWT |
| 业务层不感知数据库 | 只调抽象函数，不写 SQL 方言 |
| 提示词与代码分离 | 提示词在 `app/prompts/*.txt`，按版本号管理 |
| 前端不直连数据库 | React 只与 FastAPI 通信；Streamlit 只调业务层 |
| 课程/章节不硬编码 | 一律来自 MySQL `courses` / `knowledge_points` 表 |
| 配置单一事实来源 | `app/config.py` 是唯一真相源 |

### 3.3 目录结构

```
.
├── app.py                      # Streamlit 入口：streamlit run app.py
├── requirements.txt
├── .env / .env.example.env     # 环境变量（LLM 密钥等，不入版本控制）
├── api/                        # FastAPI 接口层
│   ├── main.py                 #   应用入口 + 启动/关闭事件
│   ├── deps.py                 #   依赖注入
│   ├── schemas.py              #   Pydantic 模型
│   └── routers/
│       ├── __init__.py
│       ├── auth.py             #   认证路由
│       ├── user.py             #   学生端路由
│       └── admin.py            #   后台管理路由
├── app/                        # 业务层
│   ├── config.py               #   全局配置（单一事实来源）
│   ├── ai/                     #   AI 域
│   ├── pipeline/               #   资料处理域
│   ├── database/               #   数据访问域
│   ├── auth/                   #   认证域
│   ├── frontend/               #   Streamlit 前端层
│   └── prompts/                #   提示词库
├── data/                       # 本地数据（自动创建，不入版本控制）
│   ├── uploads/                #   原始 PDF / DOCX
│   ├── markdown/               #   教材 PDF → MD 落盘
│   │   ├── 1/                  #     按 course_id 分目录
│   │   └── 2/
│   └── vector/                 #   FAISS 索引持久化
├── scripts/
│   ├── check_env.py            #   环境自检（只用标准库，装依赖前就能跑）
│   ├── download_model.py       #   向量模型本地下载
│   ├── init_mysql.py           #   数据库初始化
│   ├── run_api.py              #   FastAPI 启动脚本
│   └── verify_*.py             #   各阶段验证脚本
├── migrations/                 # 数据库迁移脚本
├── tests/                      # 测试（分四层：单元 / 服务 / 端到端 / 界面）
└── models/                     # 本地模型文件（bge-small-zh-v1.5）
```

---

## 四、核心概念模型

### 4.1 层级结构

```
课程（Course）
  ├── 教材（1 份，textbook）
  │     └── 章节（Chapter / Knowledge Point）
  │           └── 知识点（Knowledge Point）
  │
  └── 附属资料（N 份，supplement）
        └── 讲义 / 真题 / 习题集
              └── chunk（按章节分类，入向量库）
```

### 4.2 关系图

```
                    ┌──────────────┐
                    │   courses    │
                    │   课程        │
                    └───────┬──────┘
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
       ┌──────────┐                ┌──────────┐
       │ 教材      │                │ 附属资料  │
       │ materials│                │ materials│
       │ (1份)     │                │ (N份)    │
       └─────┬─────┘                └─────┬────┘
             │                            │
             ▼                            ▼
      PDF→MD 落盘                  语义切片
      data/markdown/                chunk
             │                            │
             ▼                            ▼
      LLM 抽章节                   LLM 分类到章节
             │                            │
             ▼                            ▼
      ┌──────────────┐            ┌──────────────┐
      │knowledge_points│          │chunk_chapter_map│
      │  章节目录      │          │  chunk-章节映射  │
      └───────┬───────┘          └───────┬────────┘
              │                          │
              │                          ▼
              │                   向量化 → FAISS
              │                          │
              └──────────┬───────────────┘
                         ▼
                 ┌──────────────┐
                 │ question_bank│
                 │   题库        │
                 └───────┬──────┘
                         │
           ┌─────────────┼─────────────┐
           ▼             ▼             ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ 错题集    │  │ 作答记录  │  │ 收藏笔记  │
    │ wrong_   │  │ answer_  │  │ favorite │
    │ questions│  │ records  │  │ notes    │
    └──────────┘  └──────────┘  └──────────┘
                         │
                         ▼
                 ┌──────────────┐
                 │   users      │
                 │   学生        │
                 └──────────────┘
```

---

## 五、核心流程

### 5.1 资料处理链路（M0）

#### 通用处理链路（阶段一已实现，阶段二升级）

```
上传文件
   ↓
格式识别      扩展名 + magic number 双重嗅探（扩展名不可信时以文件头为准）
   ↓
文本抽取      PDF→PyMuPDF ｜ PDF无文本层→自动转 OCR ｜ DOCX→段落+表格转 Markdown
              ｜ 图片→PaddleOCR ｜ TXT→UTF-8/GBK 自动尝试
   ↓
清洗          合并中文硬折行、修复英文断字、去页眉页脚样板行、压缩空行
   ↓
结构化切分    优先按标题层级（第X章 / 一、/ （一）/ 1. / Markdown #）
              同一标题内按语义切分，chunk_size=500 字，overlap=50 字
              每个 chunk 带元数据 {source_file, page, section_title, course}
   ↓
向量化        bge-small-zh-v1.5（归一化，余弦距离）
   ↓
索引          FAISS 持久化，带 chapter_id 元数据
```

**页码归属**：切分器返回每个片段的字符起始偏移，系统据此反查该字符原属第几页，因此「章节跨页」也不会串页——这是保证出题结果可追溯到具体页码的关键。

#### 链路A：教材（唯一，转MD，抽章节）

```
上传教材 PDF
   ↓
检查唯一性（每课程 1 份）
   ↓
PDF 解析 → 转 MD
   ↓
落盘 data/markdown/{course_id}/{material_id}.md
   ↓
LLM 从 MD 抽章节标题（一二级）
   ↓
建章节树（knowledge_points: chapter）
   ↓
人工确认 → 正式入库
   ↓
【不切 chunk】【不入向量库】
```

**产物**：`data/markdown/` 下的 MD 文件 + `knowledge_points` 里的章节树

**用途**：章节匹配/选择、附属资料分类挂靠点、出题时按章节读教材文本

#### 链路B：附属资料（N份，语义切片，入向量库）

```
上传附属资料 PDF
   ↓
检查该课程有没有章节（没有则提示先传教材）
   ↓
PDF 解析 → 文字抽取
   ↓
语义切片（结构优先 + LLM 兜底，保证不切断语义）
   ↓
每个 chunk 送 LLM → 识别属于哪个章节
   ↓
人工确认/修正分类结果
   ↓
写入 chunk_chapter_map
   ↓
向量化 → 入 FAISS（带 chapter_id 元数据）
   ↓
【不转MD】
```

**产物**：`chunk_chapter_map` 里的 chunk-章节映射 + FAISS 向量索引

**用途**：出题时按章节检索 chunk，给 LLM 做 RAG

### 5.2 出题流程（题库优先 + LLM 兜底）

#### 阶段一：Streamlit 练习模式出题（已交付）

```
用户请求出题（课程 + 知识点 + 题型 + 难度 + 数量）
   ↓
第一步  查本地题库（status='active'）
        命中充足 → 按 quality_score 加权抽取 → usage_count++ → 返回（无 LLM 调用）
   ↓ 未命中
第二步  检索向量库取上下文（top_k=5）
        命中 0 条        → 抛「资料不足，请上传相关材料」，拒绝出题
        最高相似度 < 0.6 → 记录「本应触发网络搜索」（当前该能力未接入）
   ↓
第三步  调用 LLM 生成 → 解析校验 → 题干 embedding 去重（阈值 0.9）
        重复 → 丢弃重生成（最多 2 轮）
        非重复 → 直接入库（无人工审核），写 prompt_version / model_version / source_ref
   ↓
返回 {questions, source_summary: {from_bank, from_llm}, warnings}
```

**调用方不感知来源**：无论命中哪条路径，返回的题目结构完全一致，只有 `from` 字段标明「📚 题库」还是「🤖 新生成」。

**三道容错防线**（模型输出不可信，必须逐层兜住）：
1. `extract_json` 依次尝试围栏、纯文本、括号截取三种方式抠 JSON；
2. `normalize_question` 校验字段合法性，难度/标签/来源缺失时回落到调用方参数；
3. 单题不合格**只跳过该题**，同一批里的其他题照常入库——一道坏题不该连坐四道好题。

**成本审计**：每次 LLM 调用（含失败）都写入 `llm_call_log` 表，记录 purpose / tokens / 耗时 / 成败，可用 `llm_call_stats()` 汇总核对。

#### 阶段二：React 聊天出题（建设中）

```
学生输入："第一章 商法概述，10道选择题"
   ↓
POST /api/user/chat
   ├── Function Calling：LLM 解析意图
   │     ├── match_chapter(keyword) → chapter_id
   │     └── generate_questions(chapter_id, type, count) → questions[]
   ↓
① 查题库：该章节下该题型的题
   ↓
   ├─ 题库 >= 需求 → 抽需求数量返回（0成本）
   │
   └─ 题库 < 需求 → 算缺口
                  ↓
              ② 检查配额：已有 + 缺口 <= 上限？
                  ├─ 是 → 继续
                  └─ 否 → 截断到上限，提示用户
                  ↓
              ③ 检索附属资料：FAISS 按 chapter_id 找 chunk
                  ↓
              ④ 读教材：按 chapter_id 从教材 MD 取该章节文本
                  ↓
              ⑤ LLM 出题：资料 chunk + 教材文本 → 题目
                  ↓
              ⑥ 去重 → 硬写入 question_bank
                  ↓
              ⑦ 返回（题库 + 新生成）
```

**响应示例**：

```json
{
  "reply": "好的，第一章 商法概述，为你准备了10道选择题",
  "chapter_id": 1,
  "chapter_name": "第一章 商法概述",
  "questions": [...],
  "source_stats": { "from_bank": 7, "from_llm": 3 },
  "quota": { "choice_used": 47, "choice_limit": 50, "short_used": 8, "short_limit": 10 }
}
```

### 5.3 预热与题库更新流程（M2.5，已交付）

预热是"首次使用核心流程"：把题库从空填到目标覆盖度，之后日常出题才能稳定命中本地库。三个约束优先于一切——**可控、可续传、可审计**。

```
步骤 1  资料状态检查
        索引 chunk 为 0 → 拒绝并引导去上传资料
        未配置 LLM     → 拒绝并给出环境变量示例
   ↓
步骤 2  范围与目标题量
        选知识点（默认全选）+ 设每知识点目标题量（默认 简答 3 + 选择 5）
   ↓
步骤 3  预估消耗确认
        算出缺口、格子数（= LLM 调用次数）、按题型/知识点的分布，用户确认后才开跑
   ↓
步骤 4  分批生成
        每个「知识点 × 题型 × 难度」格子跑一次，跑完立刻落盘
        进度条真的在动 / 点暂停真的能停 / 关掉页面回来能接着跑
   ↓
步骤 5  预热报告
        生成数量、耗时、LLM 调用次数、token 成本、未完成格子的失败原因
```

**执行粒度为什么是"格子"**：Streamlit 每次交互都会重跑整个脚本。按格子推进才能在两次 rerun 之间安全地把进度写进数据库——也才能做到"点一下暂停就真的停住"。在一个循环里跑完整轮虽然代码更短，但进度条是假的、暂停按钮也是假的。

**预热必须绕过"题库优先"**（`force_generate=True`）：预热的目标是补齐缺口，若先查库，在 `count=缺口` 时会把库内已有的题又返回一遍，缺口永远填不满。

**未完成的任务会跨会话保留**：下次打开应用时，若检测到该课程有 `running`/`paused` 的任务，会在页面顶部提示"继续这轮预热"，不会让你从头再来。

#### 「预热与题库更新」标签页的五个板块

| 板块 | 干什么 |
|---|---|
| 预热向导 | 五步把题库从空填满，支持暂停与续传 |
| 题库浏览 | 六个维度筛选；表格里勾选后批量废弃 / 恢复；导出 CSV；单题重新生成 |
| 统计看板 | 总量分布、命中率趋势、LLM 成本趋势、质量分分布、知识点×题型覆盖度热力图 |
| 更新题库 | 四种范围补题：按知识点 / 按题型 / 按难度 / 全量刷新 |
| 资料出题 | 选一份资料，**自动判断**：里面有现成习题就抽进题库，没有才让模型生成 |

#### 「资料出题」流程

```
第一步  关键词扫一遍，找出哪些段落像含习题   —— 纯字符串匹配，不调模型，免费
第二步  有 → 只对这些段落调模型抽取（原文有答案就带上，没有就打标记）
        没有 → 让模型就着这份资料生成新题
第三步  抽到/生成的题直接入库
```

**这个流程的每一步都在省 token**：

- **免费的先做**。关键词预筛不调模型，先筛掉九成无关段落，再对剩下的调模型。
- **算完账再花钱**。界面上有一块「本次预计调用」——在花任何钱之前，把"要扫多少段、要调几次模型"摆出来给你看。
- **单次抽多少段有上限**（默认 20）。不加限制的话，一份资料可能几十段都命中关键词，一次点下去就是几十次调用。
- **抽过的段落会被记住**（`extract_log` 表），重跑不重复付费。
- **缓存可以推翻**。界面上有「清除抽取记录」，还会**和题库对账**：记录说抽到过 3 道、库里却只剩 1 道，就判定记录失效并明确提示。
- **要的题多了会分批**。一次让模型出 20 道，它会漏题、选项对不齐；所以超过 5 道就拆成几次调。

**抽取有一条硬底线：只许摘录，不许自己补答案。** 模型编一个"看起来合理"的答案是很容易的，而错答案会被当成标准答案去判分——危害远大于"这道题没有答案"。原文没给答案的题**不丢弃**，而是打上 `needs_answer` 标记：它们仍然可用（补个答案就能练），但**不会**冒充完整题目去参与判分。

### 5.4 错题链路（M3，已交付）

```
练习模式答错 / 点 📥 手动加入
   ↓
错题集收录（按 课程 + 题库 id 去重）
   同一道题答错多次 → 只保留一条，累加「错次」并保存最近一次作答
   标成「已掌握」之后又答错 → 状态自动打回「待复习」
   ↓
复习记录     每次复习记录时间戳与结果（正确/错误/跳过）
   ↓
批量标记     支持一键标记一组错题为「已掌握」
   ↓
同类题练习   基于错题知识点检索题库中同知识点题目
```

### 5.5 记忆闪卡链路（M4，已交付）

```
SM-2 调度算法
   ↓
三级缩略闪卡   记住 / 模糊 / 忘记 三按钮
   ↓
知识图谱      Plotly 可视化，节点关联题目
   ↓
知识点掌握度   基于错题 + 闪卡数据计算
```

### 5.6 删题流程（级联硬删）

```
学生选中题目 → 点删除
   ↓
弹窗强确认："该题的错题/流水/收藏/笔记将一并删除，不可恢复"
   ↓
确认
   ↓
级联硬删：
   - question_bank
   - wrong_questions
   - answer_records
   - question_favorites
   - question_notes
   ↓
该章节题量 -1，配额释放
   ↓
统计重新计算
```

**连带影响（已接受）**：学习统计的"总答题数""正确率趋势"会因删题而减少；知识点掌握度会重新计算；错题集数量下降。

### 5.7 用户练习流程（React 三栏，建设中）

```
学生进入 /practice
   ↓
左栏：聊天框（空）
中栏：空状态"请在左侧告诉我想练什么"
右栏：空状态
   ↓
学生输入："第一章 商法概述，10道选择题"
   ↓
POST /api/user/chat
   ├─ 意图解析：章节=第一章，题型=选择题，数量=10
   ├─ 调 chapter_matcher 匹配章节
   ├─ 调 generator 出题（题库优先）
   └─ 返回：{ reply, chapter_id, questions[], source_stats, quota }
   ↓
左栏：显示模型回复
中栏：渲染 10 道题
右栏：显示"第一章 商法概述 | 10题 | 0/10 | 选择47/50"
   ↓
学生作答 → 判分 → 错题集
```

---

## 六、功能需求（阶段二）

### CR-101：练习页三栏重构

**优先级**：P0

**页面路由**：`/practice`

**布局**：

| 栏位 | 内容 |
|---|---|
| 左栏 | 聊天框，对话式出题 |
| 中栏 | 题目渲染（选择题/简答题） |
| 右栏 | 章节、题量、进度、配额 |

**验收标准**：
- [ ] 输入"第一章 商法概述，10道选择题"，中栏能出题
- [ ] 输入"来5道简答题"能正确识别题型
- [ ] 输入模糊章节能匹配到正确章节
- [ ] 右栏进度随作答实时更新
- [ ] 右栏显示配额
- [ ] 出题失败时有友好提示

### CR-102：接入聊天模型

**优先级**：P0

**功能描述**：接入支持多轮对话的 LLM（DeepSeek，OpenAI 兼容协议）；维护会话上下文（本次练习会话内）；技术方案为 Function Calling。

**工具定义**：
- `match_chapter(keyword)` → 返回 `chapter_id`
- `generate_questions(chapter_id, type, count)` → 返回题目

**代码影响**：新增 `app/ai/chat_agent.py` + `app/prompts/m3_chat_agent_v0.1.txt`；`app/ai/llm_client.py` 支持 tools 参数。

**验收标准**：
- [ ] 支持多轮对话（如"再来5道"能理解上下文）
- [ ] 工具调用失败有兜底回复
- [ ] LLM 调用有日志（复用 `llm_call_log`）

### CR-103：资料上传双入口

**优先级**：P0

**页面路由**：`/admin/materials`

**入口一：教材上传（唯一）**：每门课程只能有 1 份教材，上传前校验该课程是否已有教材。

**入口二：附属资料上传（N 份）**：可多份，上传后走"按章节分类"流程。

**接口影响**：`POST /api/admin/materials/upload` 增加 `entry_type`（textbook/supplement）；新增 `GET /api/admin/materials/textbook/exists`。

**数据影响**：`materials.textbook_course_id` 生成列，唯一索引 `UNIQUE(textbook_course_id)`。

**验收标准**：
- [ ] 课程已有教材时，再上传教材被拦截
- [ ] 附属资料可上传多份
- [ ] 两个入口的列表互不干扰

### CR-104：教材 PDF→MD

**优先级**：P0

**功能描述**：仅教材在解析后转 MD；存储路径 `data/markdown/{course_id}/{material_id}.md`；用于 LLM 抽章节 + 出题时按章节读文本；不用于 RAG，不入向量库。

**代码影响**：`app/pipeline/doc_parser.py` 教材解析后调 `md_writer`；新增 `app/pipeline/md_writer.py`；`materials` 表加 `markdown_path`。

**验收标准**：
- [ ] 教材上传后，`data/markdown/` 下能找到 MD
- [ ] 附属资料上传后，不产生 MD 文件
- [ ] MD 内容保留一二级标题

### CR-105：附属资料语义切片 + LLM 分类

**优先级**：P0

**切片参数**：

| 参数 | 建议值 |
|---|---|
| 单 chunk 最大 | 512~800 token |
| 单 chunk 最小 | 100 token |
| overlap | 50~100 token |
| 切分边界 | 段落 > 句号 |

**LLM 分类输出**：

```json
{
  "chapter_id": 1,
  "confidence": 0.85,
  "reason": "内容涉及商法基本概念"
}
```

**输出处理**：confidence >= 0.8 自动归类待确认；confidence < 0.8 标记待确认；chapter_id = null 归入"未分类"。

**代码影响**：`app/pipeline/chunker.py` 改为语义切片；`app/ai/chunk_classifier.py` 优化为批量分类；`app/pipeline/indexer.py` FAISS 元数据加 `chapter_id`；新增 `app/prompts/m0_all_semantic_chunk_v0.1.txt`。

**验收标准**：
- [ ] 切片后每个 chunk 语义完整
- [ ] 每个 chunk 有明确章节归属或标记"未分类"
- [ ] 分类置信度低的能人工修正
- [ ] FAISS 检索时能按 chapter_id 过滤

### CR-106：出题策略与配额规则

**优先级**：P0

**题库优先策略**：

| 来源 | 成本 | 优先级 |
|---|---|---|
| 题库命中 | 0 | 1 |
| 向量检索 | 几乎为0 | 2 |
| LLM 生成 | 有 token 成本 | 3 |

**配额规则**：

| 题型 | 每章节上限 |
|---|---|
| 选择题 | 50 道 |
| 简答题 | 10 道 |

**省钱措施**：题库优先、缺口补齐、去重、上限控制、缓存。

**验收标准**：
- [ ] 题库有题时，不调 LLM
- [ ] 题库不足时，只生成缺口数量
- [ ] 达到 50/10 上限时，不再生成
- [ ] 用户删题后，上限释放
- [ ] 生成题目自动入库
- [ ] 返回结果标明来源

### CR-107：学生删题（级联硬删）

**优先级**：P0

**功能描述**：学生可删除题库中的题目；删除方式为硬删除；级联删除四张关联表。

**前端提示**："删除后，该题的错题记录、作答历史、收藏、笔记将一并删除，且不可恢复。是否确认？"

**验收标准**：
- [ ] 删除前有强确认弹窗
- [ ] 删除后四张关联表记录一并消失
- [ ] 该章节题量 -1，配额释放
- [ ] 统计重新计算

---

## 七、接口层清单

### 认证接口 `/api/auth/*`

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/register` | 学生注册 |
| POST | `/login` | 登录 |
| POST | `/logout` | 登出 |
| GET | `/me` | 当前用户 |

### 用户接口 `/api/user/*`

| 方法 | 路径 | 作用 | 状态 |
|---|---|---|---|
| GET | `/courses` | 课程列表 | 已有 |
| GET | `/courses/{id}/chapters` | 章节树 | 已有 |
| POST | `/chapter/match` | 章节匹配 | 已有 |
| POST | `/chat` | 聊天出题（Function Calling） | **新增** |
| POST | `/questions` | 出题（兼容旧调用） | 已有 |
| DELETE | `/questions/{id}` | 删题（级联硬删） | **新增** |
| GET | `/questions/quota` | 查该章节配额 | **新增** |
| POST | `/answers` | 作答 | 已有 |
| POST | `/answers/resolve` | 按勾选重算 | 已有 |
| GET | `/wrong-questions` | 错题集 | 已有 |
| PATCH | `/wrong-questions/{id}` | 标记掌握 | 已有 |
| POST | `/wrong-questions/{id}/review` | 记录复习 | 已有 |
| DELETE | `/wrong-questions/{id}` | 删除错题 | 已有 |
| POST | `/favorites/{qid}` | 收藏题目 | 已有 |
| DELETE | `/favorites/{qid}` | 取消收藏 | 已有 |
| GET | `/favorites` | 收藏列表 | 已有 |
| POST | `/notes/{qid}` | 保存笔记 | 已有 |
| GET | `/notes/{qid}` | 拉笔记 | 已有 |
| GET | `/stats/overview` | 学习统计总览 | 已有 |
| GET | `/stats/trend` | 正确率趋势 | 已有 |
| GET | `/stats/knowledge-points` | 知识点掌握度 | 已有 |

### 后台接口 `/api/admin/*`

**首页**：

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/dashboard` | 首页数据 |

**课程管理**：

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/courses` | 课程列表 |
| POST | `/courses` | 建课程 |
| PATCH | `/courses/{id}` | 改课程 |
| DELETE | `/courses/{id}` | 停用 |
| POST | `/courses/{id}/restore` | 启用 |
| DELETE | `/courses/{id}/hard` | 彻底删除 |
| POST | `/courses/merge` | 合并课程 |

**章节管理**：

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/courses/{id}/chapters` | 章节树 |
| POST | `/chapters` | 建章节 |
| PATCH | `/chapters/{id}` | 改章节 |
| DELETE | `/chapters/{id}` | 删章节 |
| GET | `/chapters/{id}/questions` | 该章节的题量 |
| DELETE | `/chapters/{id}/questions` | 清空该章节题库 |

**资料管理**：

| 方法 | 路径 | 作用 | 状态 |
|---|---|---|---|
| POST | `/materials/upload` | 上传（区分 textbook/supplement） | 已有 |
| GET | `/materials/tasks` | 任务列表 | 已有 |
| GET | `/materials/tasks/{id}` | 任务详情 | 已有 |
| POST | `/materials/tasks/{id}/retry` | 重试 | 已有 |
| GET | `/materials` | 资料列表 | 已有 |
| GET | `/materials/textbook` | 当前课程的教材 | 已有 |
| GET | `/materials/textbook/exists` | 校验教材是否存在 | **新增** |
| POST | `/materials/{id}/extract-chapters` | 抽章节（教材专用） | 已有 |
| POST | `/materials/{id}/classify-to-chapters` | 分类到章节（附属专用） | 已有 |
| GET | `/materials/{id}/chunk-classification` | 分类结果 | 已有 |
| PATCH | `/chunks/{chunk_id}/chapter` | 手动改 chunk 归属 | 已有 |
| DELETE | `/materials/{id}` | 删除资料 | 已有 |

**题库管理**：

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/question-bank` | 题库浏览 |
| DELETE | `/question-bank/{id}` | 废弃题目 |
| POST | `/question-bank/{id}/restore` | 恢复题目 |
| GET | `/question-bank/stats` | 题库统计 |

**系统**：

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/selftest` | 系统自检 |

---

## 八、数据模型

### 8.1 表清单（22 张）

#### 课程域（5 张）

| 表 | 用途 | 状态 |
|---|---|---|
| `courses` | 课程主表 | 已有 |
| `knowledge_points` | 章节 + 知识点 | 已有（加 `node_type`/`summary`） |
| `material_course_map` | 资料-课程关联 | 已有 |
| `course_merge_log` | 课程合并日志 | 已有 |
| `chapter_request_log` | 章节请求日志 | **新增** |

#### 资料域（3 张）

| 表 | 用途 | 状态 |
|---|---|---|
| `materials` | 资料（含教材/附属） | 已有（加 `upload_type`/`chapter_classified`/`markdown_path`/`textbook_course_id`） |
| `chunk_chapter_map` | chunk-章节关联 | **新增** |
| `question_bank` | 题库 | 已有（加 `source`） |

#### 学习域（7 张）

| 表 | 用途 | 状态 |
|---|---|---|
| `wrong_questions` | 错题集 | 已有 |
| `answer_records` | 作答流水 | 已有 |
| `question_favorites` | 题目收藏 | 已有 |
| `question_notes` | 题目笔记 | 已有 |
| `papers` | 试卷 | 已有（未启用） |
| `paper_questions` | 试卷-题目 | 已有（未启用） |
| `scores` | 成绩 | 已有（未启用） |

#### 任务域（1 张）

| 表 | 用途 | 状态 |
|---|---|---|
| `parse_tasks` | 解析任务 | 已有 |

#### 日志域（4 张）

| 表 | 用途 | 状态 |
|---|---|---|
| `llm_call_log` | LLM 审计（purpose / tokens / 耗时 / 成败） | 已有 |
| `search_call_log` | 搜索审计 | 已有 |
| `serving_log` | 出题埋点（记录 from_bank / from_llm） | 已有 |
| `extract_log` | 抽取记录 | 已有 |

#### 账号域（2 张）

| 表 | 用途 | 状态 |
|---|---|---|
| `users` | 学生 | 已有 |
| `admin_users` | 管理员 | 已有 |

### 8.2 本次变更字段

| 表 | 字段 | 说明 |
|---|---|---|
| `materials` | `markdown_path` | 教材 MD 路径（仅教材有值） |
| `materials` | `textbook_course_id` | 生成列，保证教材唯一 |
| `question_bank` | `source` | `bank` / `llm` |
| `chunk_chapter_map` | `chunk_text` | chunk 原文 |
| `chunk_chapter_map` | `chunk_index` | 同资料内序号 |

### 8.3 外键调整

四张关联表需支持级联删除：`wrong_questions`、`answer_records`、`question_favorites`、`question_notes`。如当前为 `ON DELETE RESTRICT`，需改为 `CASCADE`，或在业务层显式删除。

### 8.4 命中率是真实量出来的

`serving_log` 表在每次向用户发题时记一行，写下这一单有多少道来自题库、多少道来自模型。只统计真实出题——预热与批量更新必然 `from_bank=0`，混进来会把曲线压成一条直线，指标就废了。

---

## 九、前端架构

### 9.1 双前端策略

| 前端 | 用途 | 通信方式 | 状态 |
|---|---|---|---|
| Streamlit（`app.py`） | 管理员内部工具（6 个标签页） | 进程内调用业务层 | 已交付 |
| React + TS + Ant Design（`web/`） | 学生正式前端 + 后台管理 | HTTP / REST / JWT | 建设中 |

**Streamlit 标签页**（已交付）：

| 标签页 | 渲染模块 | 功能 |
|---|---|---|
| 资料管理 | `tab_materials.py` | 上传、解析、查看索引状态 |
| 预热与题库更新 | `tab_warmup.py` | 5 个板块：向导·浏览·看板·更新·资料出题 |
| 练习模式 | `tab_practice.py` | 按知识点/难度出题，作答判分 |
| 错题集 | `tab_wrongbook.py` | 列表·分组·批量标记·重做模式 |
| 记忆闪卡 | `tab_memory.py` | SM-2 调度·三级闪卡·知识图谱 |
| 系统自检 | `tab_selftest.py` | 验收标准·提示词审计·成本审计 |

### 9.2 React 页面结构

**用户端（4 个页面）**：

| 页面 | 路由 | 说明 |
|---|---|---|
| 登录/注册 | `/login` | 学生入口 |
| 练习 | `/practice` | 三栏：聊天 + 题目 + 进度 |
| 错题集 | `/wrong-book` | 错题管理 |
| 学习统计 | `/stats` | 数据可视化 |

**后台端（9 个页面）**：

| 页面 | 路由 | 说明 |
|---|---|---|
| 管理员登录 | `/admin/login` | 独立入口 |
| Dashboard | `/admin/dashboard` | 数据总览 |
| 课程管理 | `/admin/courses` | 增删改、启停、合并 |
| 章节管理 | `/admin/chapters` | 章节树编辑 |
| 资料上传 | `/admin/materials` | 教材 + 附属资料（双 Tab） |
| 资料分类 | `/admin/classify` | LLM 识别 + 确认 |
| chunk 分类确认 | `/admin/chunk-classify` | 附属资料按章节归类 |
| 题库浏览 | `/admin/question-bank` | 筛选、废弃、恢复 |
| 系统自检 | `/admin/selftest` | 数据库 + 成本 |

### 9.3 练习页三栏交互

```
学生进入 /practice
   ↓
┌─────────────────────────────────────────────┐
│ 左栏：聊天框   中栏：空   右栏：空           │
│  "请告诉我章节"                             │
└─────────────────────────────────────────────┘
   ↓
学生输入"第一章 商法概述，10道选择题"
   ↓
左栏显示：
  🤖 "好的，第一章 商法概述"
     "为你准备了10道选择题"
   ↓
中栏出题（10 道）
右栏显示：章节 | 10题 | 0/10 | 选择47/50
   ↓
学生作答 → 判分 → 反馈 → 错题集
```

---

## 十、技术栈

| 层 | 技术 |
|---|---|
| 后端框架 | FastAPI + Uvicorn |
| 内部前端 | Streamlit（`app.py`） |
| 正式前端 | React 18 + TypeScript + Ant Design 5 + Vite |
| 状态管理 | Zustand |
| HTTP 客户端 | Axios |
| 认证 | JWT（python-jose）+ bcrypt（passlib） |
| 数据库 | MySQL 8.0（PyMySQL + DBUtils） |
| 缓存 | Redis 7 |
| 向量库 | FAISS（从 ChromaDB 迁移） |
| 向量模型 | BAAI/bge-small-zh-v1.5（本地离线，惰性加载） |
| LLM | DeepSeek（OpenAI 兼容协议） |
| 搜索引擎 | 博查（Bocha API） |
| 文档解析 | PyMuPDF / python-docx / PaddleOCR |
| 部署 | Docker Compose（MySQL + Redis 容器化） |

### 向量模型本地化

模型默认从 HuggingFace 下载，国内网络可能不通。推荐一次性下到本地：

```bash
python scripts/download_model.py
```

下载完成后应用自动优先使用本地模型（`models/bge-small-zh-v1.5/`）。若脚本所有来源都不通，改用浏览器手动从 `hf-mirror.com` 下载。

---

## 十一、非功能需求

| 项 | 要求 |
|---|---|
| 性能 | 聊天出题响应 ≤ 5s（题库命中 ≤ 1s） |
| 并发 | 支持 100 学生同时在线 |
| 成本 | LLM 调用量下降 ≥ 50%（题库优先 + 预热填补） |
| 数据一致性 | 删题级联必须原子性（事务） |
| 兼容性 | React 前端为主，Streamlit 保留为管理员工具 |
| 安全 | JWT 认证，学生只能删自己的可见题 |
| 可追溯 | 所有 LLM 调用有日志（`llm_call_log`） |
| 可恢复 | 单题"重新生成"失败自动恢复原题，不会丢题 |

---

## 十二、排期与里程碑

| 周次 | 任务 | 交付物 |
|---|---|---|
| 已完成 | M0~M5（阶段一全部） | Streamlit 全功能内部工具 |
| 第 1 周 | CR-103 + CR-104 | 上传双入口 + 教材 MD |
| 第 2 周 | CR-105 | 语义切片 + LLM 分类 |
| 第 3 周 | CR-102 + CR-106 | 聊天模型 + 出题策略 |
| 第 4 周 | CR-101 + CR-107 | 三栏前端 + 删题 |
| 第 5 周 | 联调 + 测试 + 上线 | 生产可用 |

---

## 十三、风险与依赖

| 风险 | 影响 | 应对 |
|---|---|---|
| 语义切片 LLM 慢 | 资料处理时间长 | 批量 + 异步 + 进度提示 |
| 级联硬删误操作 | 数据丢失 | 强确认弹窗 + 日志 |
| 配额规则理解偏差 | 体验不一致 | 右栏实时显示配额 |
| 教材 MD 质量差 | 抽章节不准 | 人工确认环节 |
| FAISS 元数据过滤性能 | 检索变慢 | 数据量小，先检索后过滤 |
| 四张关联表外键非 CASCADE | 删题失败 | 改外键或业务层显式删 |
| 向量模型下载失败 | 无法建索引 | `scripts/download_model.py` 多源下载 + 手动兜底 |
| 预热中断后重跑浪费 token | 成本上升 | 格子级持久化 + 续传 + extract_log 去重 |

---

## 十四、验收清单（总）

**阶段一（已验收）**：

- [x] M0：资料上传 → 格式识别 → 文本抽取 → 清洗 → 结构化切分 → 向量化 → 索引
- [x] M2：题库优先出题（命中题库 0 成本，未命中 LLM 兜底），三道容错防线
- [x] M2.5：预热向导 + 题库浏览 + 统计看板 + 更新题库 + 资料出题
- [x] M3：错题集（收录·去重·分类·复习记录·批量标记·同类题练习）
- [x] M4：记忆闪卡（SM-2 调度·三级缩略·知识图谱）
- [x] M5：系统自检 + 端到端测试 + 提示词审计 + 成本审计

**阶段二（待验收）**：

- [ ] 学生可用自然语言出题
- [ ] 题库优先，LLM 仅补缺口
- [ ] 每章节选择题 ≤ 50，简答题 ≤ 10
- [ ] 学生可硬删题库题，级联删关联记录
- [ ] 教材唯一，转 MD，抽章节
- [ ] 附属资料语义切片 + LLM 分类
- [ ] 附属资料入 FAISS，带 chapter_id
- [ ] 三栏练习页信息完整
- [ ] 上传双入口分离
- [ ] 所有接口有日志
- [ ] 删题有强确认弹窗
- [ ] 配额在右栏实时显示

---

## 十五、附录

### 15.1 术语表

| 术语 | 说明 |
|---|---|
| 教材 | 每课程唯一，PDF 转 MD，抽章节 |
| 附属资料 | 可多份，语义切片，入向量库 |
| chunk | 附属资料切片后的最小检索单元 |
| 预热 | 首次使用一键填满题库的操作 |
| 配额 | 每章节题量上限（选择 50 / 简答 10） |
| 级联硬删 | 删主记录时物理删除关联记录 |
| Function Calling | LLM 调用工具的技术方案 |
| 格子 | "知识点 × 题型 × 难度"的交叉组合，预热执行的最小粒度 |
| 语义切片 | 按自然段落/标题/句号切分，保证不切断知识点 |

### 15.2 待确认项

| # | 事项 | 建议 |
|---|---|---|
| 1 | 四张关联表外键当前是 CASCADE 还是 RESTRICT | 改为 CASCADE |
| 2 | 语义切片 LLM 是"判断切分点"还是"直接输出 chunk" | 判断切分点 |
| 3 | 未分类 chunk 是否入向量库 | 入，检索时默认过滤 |

---

*文档结束*