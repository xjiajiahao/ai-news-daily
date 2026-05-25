# ai-news-daily

`ai-news-daily` 是一个面向 Codex 的 skill，用于收集每日 AI 技术与产品动态，聚合 GitHub Trending 与指定微信公众号文章列表，生成偏技术、产品、开源生态取向的日报，并在用户明确要求时把生成的 Markdown 简报发送到指定邮箱或微信公众号草稿箱。

仓库当前包含六部分能力：

- `SKILL.md`：定义 skill 的触发条件、工作流和输出要求
- `scripts/fetch_wechat_articles.py`：拉取配置公众号最新文章列表，供日报生成阶段使用
- `scripts/fetch_github_trending.py`：抓取并分析 GitHub Trending，筛出 AI 相关开源项目
- `scripts/markdown_utils.py`：复用 Markdown 标题提取、HTML 渲染与公众号 HTML 转换逻辑
- `scripts/send_markdown_email.py`：把生成好的 Markdown 简报作为邮件正文和附件发送
- `scripts/send_markdown_wechat.py`：把生成好的 Markdown 简报转换成公众号图文草稿，并可选提交发布

## 适用场景

适合以下需求：

- 生成“今天 AI 有什么新东西”的简报
- 汇总近 24 小时 AI 技术、模型、产品、Agent、开源项目动态
- 为每日晨报、群内播报、内部情报汇总准备结构化素材
- 把已经生成的 AI 简报发到指定邮箱
- 把已经生成的 AI 简报发到微信公众号草稿箱

默认数据源：

- GitHub Trending：`https://github.com/trending`
- 微信公众号：配置见 `references/source_accounts.json`

当前预置公众号包括：

- 机器之心
- 量子位
- 新智元
- MiniMax 稀宇科技
- 智谱
- 通义实验室
- 月之暗面 Kimi
- DeepSeek
- AGI Hunt
- 赛博禅心

## 仓库结构

```text
.
├── README.md
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── mptext-api.md
│   ├── smtp-env.md
│   ├── source_accounts.json
│   └── wechat-official-account-env.md
├── asset/
│   └── ai-news-daily.png
└── scripts/
    ├── fetch_github_trending.py
    ├── fetch_wechat_articles.py
    ├── markdown_utils.py
    ├── send_markdown_email.py
    └── send_markdown_wechat.py
```

## 运行要求

- Python 3.9+
- 可访问 `https://down.mptext.top`
- 有效的 mptext API Key
- 如需发送邮件，还需要可用的 SMTP 配置
- 如需推送到微信公众号，还需要可用的公众号开发配置

推荐通过环境变量提供密钥：

```bash
export MPTEXT_API_KEY="your-api-key"
```

可选环境变量：

- `MPTEXT_API_KEY`：mptext 接口密钥
- `MPTEXT_BASE_URL`：覆盖默认接口地址，默认值为 `https://down.mptext.top`

发送邮件时额外需要：

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- 可选：`SMTP_FROM_NAME`
- 可选：`SMTP_SECURITY`

具体示例见 `references/smtp-env.md`。

发送到微信公众号时额外需要：

- `WECHAT_APP_ID`
- `WECHAT_APP_SECRET`
- 可选：`WECHAT_AUTHOR`
- 可选：`WECHAT_DEFAULT_DIGEST`
- 可选：`WECHAT_CONTENT_SOURCE_URL`
- 可选：`WECHAT_DEFAULT_THUMB_MEDIA_ID`

具体示例见 `references/wechat-official-account-env.md`。

## 快速开始

### 1. 拉取最近 1 天的公众号文章

```bash
python3 scripts/fetch_wechat_articles.py \
  --limit 15 \
  --days 1 \
  --json-output /tmp/ai-news-wechat.json
```

这会：

- 读取 `references/source_accounts.json` 中的账号配置
- 解析公众号账号信息
- 拉取每个账号的文章列表
- 过滤最近 1 天内容
- 同时打印 JSON 到标准输出，并写入 `/tmp/ai-news-wechat.json`

### 2. 只抓取指定公众号

```bash
python3 scripts/fetch_wechat_articles.py \
  --account "机器之心" \
  --account "量子位" \
  --limit 10 \
  --days 2
```

### 3. 输出紧凑 JSON

```bash
python3 scripts/fetch_wechat_articles.py --compact
```

### 4. 拉取并分析 GitHub Trending

```bash
python3 scripts/fetch_github_trending.py \
  --since daily \
  --limit 15 \
  --json-output /tmp/ai-news-trending.json
```

这会：

- 抓取 GitHub Trending Daily 页面
- 解析仓库名、描述、语言、累计 Star、当日新增 Star
- 用内置关键词给仓库做 AI 相关性打分
- 默认只输出 AI 相关项目

如果要同时保留全部 Trending 项目用于人工筛选：

```bash
python3 scripts/fetch_github_trending.py \
  --since daily \
  --all \
  --json-output /tmp/github-trending.json
```

如果 GitHub 页面结构变化，需要保留原始 HTML 便于排查：

```bash
python3 scripts/fetch_github_trending.py \
  --since daily \
  --all \
  --html-output /tmp/github-trending.html \
  --json-output /tmp/github-trending.json
```

### 5. 发送已生成的简报邮件

```bash
python3 scripts/send_markdown_email.py /absolute/path/to/ai-news-daily-YYYY-MM-DD.md recipient1@example.com recipient2@example.com --cc manager@example.com
```

如果要先验证标题提取、HTML 渲染和 SMTP 配置，可以先执行：

```bash
python3 scripts/send_markdown_email.py /absolute/path/to/ai-news-daily-YYYY-MM-DD.md recipient1@example.com recipient2@example.com --cc manager@example.com --dry-run
```

邮件发送行为：

- 默认从 Markdown 第一行标题提取邮件主题
- 同时发送纯文本正文和 HTML 正文
- 原始 Markdown 文件会作为附件一并发送
- `SMTP_SECURITY=auto` 时，会按端口自动推断 `ssl`、`starttls` 或 `plain`

### 6. 创建微信公众号草稿

```bash
python3 scripts/send_markdown_wechat.py /absolute/path/to/ai-news-daily-YYYY-MM-DD.md
```

如果封面图还没上传成 `media_id`，可以直接传本地文件或远程图片地址：

```bash
python3 scripts/send_markdown_wechat.py /absolute/path/to/ai-news-daily-YYYY-MM-DD.md \
  --thumb-image /absolute/path/to/cover.png
```

如果要先验证标题、摘要、HTML 与接口请求体：

```bash
python3 scripts/send_markdown_wechat.py /absolute/path/to/ai-news-daily-YYYY-MM-DD.md --dry-run
```

如果要把生成的请求体落盘，便于排查或人工检查：

```bash
python3 scripts/send_markdown_wechat.py /absolute/path/to/ai-news-daily-YYYY-MM-DD.md \
  --dry-run \
  --payload-output /tmp/ai-news-wechat-payload.json
```

如果用户明确要求直接发布，再显式提交发布任务：

```bash
python3 scripts/send_markdown_wechat.py /absolute/path/to/ai-news-daily-YYYY-MM-DD.md --publish
```

公众号发送行为：

- 默认只创建草稿，不会自动发布
- 草稿必须有封面；可通过 `WECHAT_DEFAULT_THUMB_MEDIA_ID`、`--thumb-media-id` 或 `--thumb-image` 提供
- `--thumb-image` 支持本地文件路径和远程图片 URL
- Markdown 中的图片默认会上传到微信正文图片接口后替换链接
- 如果不希望自动重写正文图片，可传 `--skip-image-upload`
- `--open-comment` 可开启评论，`--fans-only-comment` 需要和 `--open-comment` 一起使用

## 脚本参数

`scripts/fetch_wechat_articles.py` 支持以下主要参数：

- `--api-key`：显式传入 mptext API Key
- `--base-url`：指定 mptext 服务地址
- `--config`：指定账号配置文件，默认是 `references/source_accounts.json`
- `--account`：只抓某几个账号，可重复传入
- `--limit`：每个账号最多抓取多少篇，mptext 接口最大为 20
- `--begin`：文章列表分页偏移量
- `--days`：只保留最近 N 天内容
- `--search-size`：公众号搜索结果中参与匹配的候选数量
- `--json-output`：将结果写入本地文件
- `--compact`：输出紧凑 JSON
- `--summary-max-chars`：摘要最大保留字符数

`scripts/fetch_github_trending.py` 支持以下主要参数：

- `--base-url`：指定 Trending 基础地址，默认 `https://github.com/trending`
- `--language`：指定语言路径，如 `python`、`typescript`
- `--since`：趋势时间窗，可选 `daily`、`weekly`、`monthly`
- `--limit`：输出保留的仓库数量
- `--top`：只分析前 N 个解析到的趋势仓库
- `--keyword`：追加 AI 相关关键词，可重复传入
- `--all`：输出全部趋势项目，而不只保留 AI 相关项目
- `--json-output`：把结果写入本地文件
- `--html-output`：把抓到的原始 HTML 落盘，便于页面结构变更时排查
- `--compact`：输出紧凑 JSON

完整帮助：

```bash
python3 scripts/fetch_wechat_articles.py --help
python3 scripts/fetch_github_trending.py --help
python3 scripts/send_markdown_email.py --help
python3 scripts/send_markdown_wechat.py --help
```

其中 `scripts/send_markdown_wechat.py` 额外常用参数包括：

- `--title`：覆盖从 Markdown 自动提取的标题
- `--author`：覆盖公众号作者名
- `--digest`：覆盖自动生成或环境变量提供的摘要
- `--content-source-url`：设置“原文链接”
- `--thumb-media-id`：直接指定封面 `media_id`
- `--thumb-image`：上传本地或远程封面图并自动使用返回的 `media_id`
- `--payload-output`：把最终草稿请求体写到本地 JSON 文件

## 输出格式

### 公众号文章抓取输出

脚本输出 JSON，顶层字段包括：

- `fetched_at`：抓取时间
- `base_url`：实际使用的接口地址
- `requested_accounts`：请求抓取的账号名称
- `per_account_limit`：每个账号实际抓取上限
- `days_filter`：时间过滤条件
- `sources`：按账号组织的文章列表
- `errors`：解析账号或拉取文章时的错误

`sources[].articles[]` 中包含：

- `title`：文章标题
- `url`：文章链接
- `summary`：摘要
- `published_timestamp`：原始时间戳
- `published_at`：标准化后的发布时间
- `author_name`：作者
- `cover`：封面图
- `copyright_type`：版权类型

示例结构：

```json
{
  "fetched_at": "2026-04-15T21:00:00+08:00",
  "requested_accounts": ["机器之心"],
  "sources": [
    {
      "requested_name": "机器之心",
      "resolved_account": {
        "nickname": "机器之心",
        "alias": "almosthuman2014",
        "fakeid": "..."
      },
      "articles": [
        {
          "title": "示例标题",
          "url": "https://mp.weixin.qq.com/...",
          "summary": "示例摘要",
          "published_at": "2026-04-15T08:00:00+08:00"
        }
      ]
    }
  ],
  "errors": []
}
```

### GitHub Trending 输出

`scripts/fetch_github_trending.py` 输出 JSON，顶层字段包括：

- `fetched_at`：抓取时间
- `source_url`：实际访问的 Trending URL
- `language`：指定的语言过滤条件
- `since`：趋势时间窗
- `requested_limit`：请求输出上限
- `parsed_count`：页面中实际解析到的仓库数量
- `ai_relevant_count`：识别为 AI 相关的仓库数量
- `keywords`：用于 AI 相关性判断的关键词列表
- `repositories`：最终输出的趋势仓库列表

`repositories[]` 中包含：

- `repo`：`owner/name`
- `url`：仓库链接
- `description`：仓库描述
- `language`：主要语言
- `stars`：累计 Star 数
- `today_stars`：Trending 页面展示的当日新增 Star 数
- `forks`：Fork 数
- `built_by`：页面中的贡献者用户名
- `ai_score`：基于关键词的 AI 相关性打分
- `ai_keywords`：命中的关键词

## 作为 Codex Skill 使用

这个仓库本身是一个 skill，核心行为定义在 `SKILL.md`。

skill 的工作流是：

1. 先运行 `scripts/fetch_wechat_articles.py` 拉取公众号文章列表
2. 再运行 `scripts/fetch_github_trending.py` 收集 GitHub Trending 中 AI / ML / Agent / 多模态 / 图像 / 语音 / 推理 / 数据工具相关项目
   - `Stars` 使用项目当前累计 Star 总数
   - `今日增长` 使用 GitHub Trending 页面显示的当日新增 Star 数
   - 不要把累计 Star 和今日增长写成同一个值，除非源页面确实一致
3. 归并、去重、筛选，优先保留技术、产品和开源生态消息
4. 输出 Markdown 简报，并写入当前目录下的 `ai-news-daily-YYYY-MM-DD.md`
5. 如果用户明确要求发到邮箱，则调用 `scripts/send_markdown_email.py` 发送第 4 步产出的 Markdown 文件
6. 如果用户明确要求发到微信公众号，则调用 `scripts/send_markdown_wechat.py` 创建草稿；只有明确要求直接发布时才传 `--publish`

日报默认输出结构：

- `Top 10 最热 / 最前沿消息`
- `更多新闻`
- `模型 / 研究`
- `AI 产品 / Agent`
- `开源项目`
- `基础设施 / 硬件 / 安全`

具体格式和筛选规则以 `SKILL.md` 为准。

如果用户要求“把简报发到邮箱”，仍然直接使用 `ai-news-daily` 即可，不需要切换到独立的邮件 skill。

如果用户要求“发到微信公众号”或“帮我生成公众号草稿”，也仍然直接使用 `ai-news-daily` 即可，不需要切到别的 skill。

## 配置说明

### 公众号源配置

`references/source_accounts.json` 中保存每个目标账号的匹配信息：

- 展示名称 `name`
- 搜索关键词 `search_keyword`
- 预期昵称 `expected_nickname`
- 预期别名 `expected_alias`
- 优先使用的 `preferred_fakeid`

这些字段用于在 mptext 搜索结果中稳定解析到正确公众号，避免同名或近似账号误匹配。

### mptext API 说明

接口细节和排障笔记见 `references/mptext-api.md`，包括：

- 认证头格式
- 基础地址
- 账号搜索接口
- 文章列表接口
- 当前脚本实际依赖的返回字段

### 微信公众号发布说明

环境变量和使用示例见 `references/wechat-official-account-env.md`。

脚本默认行为是创建草稿，不会直接发布。只有显式传 `--publish` 时，才会在草稿创建成功后提交发布任务。
