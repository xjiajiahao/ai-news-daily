# ai-news-daily

`ai-news-daily` 是一个面向 Codex 的 skill，用于收集每日 AI 技术与产品动态，聚合 GitHub Trending 与指定微信公众号文章列表，生成偏技术、产品、开源生态取向的日报，并在用户明确要求时把生成的 Markdown 简报发送到指定邮箱。

仓库当前包含三部分能力：

- `SKILL.md`：定义 skill 的触发条件、工作流和输出要求
- `scripts/fetch_wechat_articles.py`：拉取配置公众号最新文章列表，供日报生成阶段使用
- `scripts/send_markdown_email.py`：把生成好的 Markdown 简报作为邮件正文和附件发送

## 适用场景

适合以下需求：

- 生成“今天 AI 有什么新东西”的简报
- 汇总近 24 小时 AI 技术、模型、产品、Agent、开源项目动态
- 为每日晨报、群内播报、内部情报汇总准备结构化素材
- 把已经生成的 AI 简报发到指定邮箱

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
│   └── source_accounts.json
└── scripts/
    ├── fetch_wechat_articles.py
    └── send_markdown_email.py
```

## 运行要求

- Python 3.9+
- 可访问 `https://down.mptext.top`
- 有效的 mptext API Key
- 如需发送邮件，还需要可用的 SMTP 配置

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

### 4. 发送已生成的简报

```bash
python3 scripts/send_markdown_email.py /absolute/path/to/ai-news-daily-YYYY-MM-DD.md recipient@example.com
```

如果要先验证标题提取、HTML 渲染和 SMTP 配置，可以先执行：

```bash
python3 scripts/send_markdown_email.py /absolute/path/to/ai-news-daily-YYYY-MM-DD.md recipient@example.com --dry-run
```

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

完整帮助：

```bash
python3 scripts/fetch_wechat_articles.py --help
```

## 输出格式

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

## 作为 Codex Skill 使用

这个仓库本身是一个 skill，核心行为定义在 `SKILL.md`。

skill 的工作流是：

1. 先运行 `scripts/fetch_wechat_articles.py` 拉取公众号文章列表
2. 再收集 GitHub Trending 中 AI / ML / Agent / 多模态 / 图像 / 语音 / 推理 / 数据工具相关项目
3. 归并、去重、筛选，优先保留技术、产品和开源生态消息
4. 输出 Markdown 简报，并写入当前目录下的 `ai-news-daily-YYYY-MM-DD.md`
5. 如果用户明确要求发到邮箱，则调用 `scripts/send_markdown_email.py` 发送该 Markdown 文件

日报默认输出结构：

- `Top 10 最热 / 最前沿消息`
- `更多新闻`
- `模型 / 研究`
- `AI 产品 / Agent`
- `开源项目`
- `基础设施 / 硬件 / 安全`

具体格式和筛选规则以 `SKILL.md` 为准。

如果用户要求“把简报发到邮箱”，仍然直接使用 `ai-news-daily` 即可，不需要切换到独立的邮件 skill。

## 配置说明

### 公众号配置

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

## 常见问题

### 1. 提示缺少 API Key

脚本会直接退出并提示：

```text
Missing mptext API key. Set MPTEXT_API_KEY or pass --api-key.
```

处理方式是设置 `MPTEXT_API_KEY`，或在命令行传入 `--api-key`。

### 2. 某个公众号抓取失败

失败信息会进入输出 JSON 的 `errors` 字段。常见原因包括：

- 搜索结果没有稳定命中目标账号
- 接口网络异常
- API Key 无效或额度受限

如果需要排查接口问题，优先查看 `references/mptext-api.md`。

## 开发说明

如果你要扩展这个仓库，通常会改动这几个位置：

- 修改抓取逻辑：`scripts/fetch_wechat_articles.py`
- 修改邮件发送逻辑：`scripts/send_markdown_email.py`
- 增删数据源：`references/source_accounts.json`
- 调整 SMTP 说明：`references/smtp-env.md`
- 调整日报工作流与输出规范：`SKILL.md`
- 调整 skill 展示信息：`agents/openai.yaml`

保持这些文件的一致性比单独修改某一处更重要，否则 skill 的行为、文档和展示配置会脱节。
