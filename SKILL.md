---
name: ai-news-daily
description: 收集每日 AI 技术与产品动态，聚合 GitHub Trending 与指定微信公众号文章列表，生成偏技术/产品取向的简报；当用户明确要求时，将简报发送到指定邮箱或微信公众号草稿箱
---

# AI 每日新闻简报

## 何时使用

当用户要看“今天 AI 有什么新东西”、“做一份 AI 日报”、“汇总最新 AI 技术/产品动态”、“Anything new?”时使用。

如果用户明确要求“把简报发到邮箱”“发给某个收件人”“邮件发送日报”“发到微信公众号”“生成公众号草稿”，也继续使用这个 skill，不需要切到别的 skill。

## 数据源

- GitHub Trending：`https://github.com/trending`
- 微信公众号：见 `references/source_accounts.json`
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

微信公众号文章列表统一通过 `scripts/fetch_wechat_articles.py` 获取。

严格限制：

- 只允许使用本 skill 明确列出的两个数据源：微信公众号文章列表和 GitHub Trending
- 不允许为了“补充信息”“交叉验证”“查官方原文”“补当天新闻”而额外搜索外网、浏览新闻站、搜索引擎、官方博客或任意第三方站点
- 不允许在公众号抓取正常返回后，再去外网补充“本日 AI 新闻”
- 如果公众号抓取失败，或结果里 `sources` 为空，必须立即停止任务并明确报告失败原因；不要改用外部网站兜底，不要继续生成日报，不要继续发邮件或发公众号
- 如果 GitHub Trending 抓取失败，也必须明确报告失败原因并停止任务；不要改用其他开源榜单代替

## Claude Code 兼容规则

Claude Code 执行 skill 内的 shell 命令时，当前工作目录不一定是这个 skill 目录。

因此：

- 本文里的命令默认都按 skill 目录作为当前工作目录来写
- 如果在 Claude Code 里执行时当前目录不是这个 skill 目录，需要手动给脚本路径补上 `${CLAUDE_SKILL_DIR}/`
- 读取本 skill 附带的参考文件时，优先使用相对链接让 Claude 按需读取；只有在 shell 中直接访问文件时，才需要显式使用 `${CLAUDE_SKILL_DIR}/...`
- 只有日报输出文件这类用户产物，才应该写到当前工作目录或用户指定路径；不要把生成结果写回 skill 自带目录

## 工作流

### 1. 拉取公众号文章列表

先运行：

```bash
python3 scripts/fetch_wechat_articles.py --limit 15 --days 1 --json-output /tmp/ai-news-wechat.json
```

规则：

- 默认从环境变量 `MPTEXT_API_KEY` 读取密钥
- 如需只抓部分公众号，追加 `--account "机器之心"` 等参数
- 输出 JSON 会包含：
  - 解析后的公众号信息
  - 文章标题
  - 文章链接
  - 摘要
  - 发布时间

仅在需要改脚本或排查接口异常时，再读 [references/mptext-api.md](references/mptext-api.md)。

硬性规则：

- 抓取完成后，必须先检查输出 JSON
- 如果命令失败、JSON 不存在、`sources` 为空，或所有账号都落在 `errors` 中，立即停止任务并向用户报告“公众号抓取失败”
- 失败后禁止继续执行 GitHub Trending、外部搜索、写 Markdown、发邮件、发公众号中的任何一步

### 2. 收集 GitHub Trending

运行：

```bash
python3 scripts/fetch_github_trending.py --since daily --limit 15 --json-output /tmp/ai-news-trending.json
```

默认会抓取 GitHub Trending Daily，并优先保留 AI / ML / Agent / 多模态 / 语音 / 图像 / 推理 / 数据工具相关项目。

重点关注：

- AI / ML / Agent / 多模态 / 语音 / 图像 / 推理 / 数据工具相关项目
- 项目描述
- 当日 Star 增长

脚本输出 JSON，单条仓库会包含：

- `repo`
- `url`
- `description`
- `language`
- `stars`
- `today_stars`
- `ai_score`
- `ai_keywords`

常用参数：

- `--since daily|weekly|monthly`
- `--language python`
- `--limit 15`
- `--all`：输出全部趋势项目，而不只保留 AI 相关项目
- `--keyword xxx`：补充自定义关键词
- `--html-output /tmp/trending.html`：排查 GitHub 页面结构变化时保存原始 HTML

开源项目数据提取规则：

- `Stars` 填项目当前累计 Star 总数，不是当天增长值
- `今日增长` 只填 GitHub Trending 页面展示的当日新增 Star 数
- 如果只能拿到累计 Star、拿不到当日增长，就不要伪造“今日增长”数字
- 严禁把累计 Star 总数和“今日增长”写成同一个值，除非源页面两者确实一致

硬性规则：

- 只有在“公众号抓取成功”之后，才能执行这一步
- 如果 GitHub Trending 抓取失败，立即停止任务并报告失败原因
- 失败后禁止改用其他网站、榜单或搜索结果替代

### 3. 归并与筛选

默认优先级：

1. 技术突破：新模型、训练/推理方法、评测、系统优化、论文和开源代码
2. AI 产品：新功能上线、可体验产品、开发者工具、Agent 工作流
3. 开源生态：`scripts/fetch_github_trending.py` 输出的 AI 相关趋势项目
4. 商业信息：只在直接影响技术路线、产品能力或开源生态时保留

处理规则：

- 优先“近 24 小时”内容
- 同一消息跨公众号重复时去重，保留信息量更高的链接
- 融资、估值、空泛战略表态默认降权
- `Top 10` 默认应以“模型 / 研究 / AI 产品 / 基础设施更新”为主，GitHub Trending 只作为补充信号
- `Top 10` 中 GitHub Trending 条目默认不超过 2 条；只有当天公众号和产品信号明显不足时，才放宽到 3 条
- GitHub Trending 更适合放在 `### 开源项目` 小节集中展示，不要用多个趋势项目挤占 `Top 10`
- 不允许因为“公众号信息量不足”而切换到外部搜索补足条目；宁可减少候选范围，也不要引入未授权来源

### 4. 写出 Markdown 简报

简报必须同时写成当前目录下的 Markdown 文件，文件名默认使用 `ai-news-daily-YYYY-MM-DD.md`。

如果用户没有单独指定文件名，就按这个默认文件名写出，后续发邮件或发公众号也使用这个文件。

如果用户后续要求发邮件或发公众号，不要重新手工拼正文，统一复用这个 Markdown 文件作为唯一来源。

### 5. 用户要求发邮件时发送简报

仅当用户明确要求发到邮箱，且请求里提供了收件人邮箱地址时，执行发送流程。

使用：

```bash
python3 scripts/send_markdown_email.py /absolute/path/to/ai-news-daily-YYYY-MM-DD.md recipient1@example.com recipient2@example.com --cc manager@example.com
```

需要先验证配置、解析结果或当前环境网络受限时，使用：

```bash
python3 scripts/send_markdown_email.py /absolute/path/to/ai-news-daily-YYYY-MM-DD.md recipient1@example.com recipient2@example.com --cc manager@example.com --dry-run
```

发信规则：

- 从第一行 Markdown 标题自动提取邮件主题
- 如果没有标题，则回退到文件名
- 邮件正文同时包含纯文本和 HTML
- 原始 Markdown 文件作为附件一并发送
- Markdown 解析、标题提取和 HTML 渲染逻辑统一走 `scripts/markdown_utils.py`
- SMTP 配置来自环境变量，具体见 [references/smtp-env.md](references/smtp-env.md)
- 如果缺少收件人邮箱地址，需要用一句简短问题向用户补齐
- 如果网络被限制，不能假装已发送，必须明确报告限制

发信环境变量：

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- 可选：`SMTP_FROM_NAME`
- 可选：`SMTP_SECURITY`，可用值为 `auto`、`ssl`、`starttls`、`plain`

### 6. 用户要求发到微信公众号时创建草稿或提交发布

默认优先创建公众号草稿，不要默认直接发布。

使用：

```bash
python3 scripts/send_markdown_wechat.py /absolute/path/to/ai-news-daily-YYYY-MM-DD.md
```

如果用户明确要求直接发布，才使用：

```bash
python3 scripts/send_markdown_wechat.py /absolute/path/to/ai-news-daily-YYYY-MM-DD.md --publish
```

需要先验证配置、标题、摘要、HTML 或请求体时，使用：

```bash
python3 scripts/send_markdown_wechat.py /absolute/path/to/ai-news-daily-YYYY-MM-DD.md --dry-run
```

公众号规则：

- 默认行为是“写 Markdown 文件”后再“创建公众号草稿”
- 只有用户明确要求直接发布时，才传 `--publish`
- 标题默认从 Markdown 第一行标题提取；摘要默认优先取 `WECHAT_DEFAULT_DIGEST`，否则从 Markdown 正文自动压缩生成
- 公众号图文草稿必须有封面，因此需要：
  - 环境变量 `WECHAT_DEFAULT_THUMB_MEDIA_ID`
  - 或运行参数 `--thumb-media-id`
  - 或运行参数 `--thumb-image /absolute/path/to/cover.png`
- `--thumb-image` 可以是本地文件路径，也可以是可访问的远程图片 URL
- Markdown 中如果带图片，脚本默认会把图片上传到微信正文图片接口后替换 URL
- 如需检查最终请求体或联调接口，优先使用 `--dry-run`，必要时加 `--payload-output /tmp/xxx.json`
- 如果用户只是要“生成草稿，我自己点发布”，最终响应只需要简短确认草稿创建结果，不要重复整篇简报
- 如果网络被限制、缺少公众号权限或缺少封面图，不能假装已发布，必须明确报告失败原因

公众号环境变量：

- `WECHAT_APP_ID`
- `WECHAT_APP_SECRET`
- 可选：`WECHAT_AUTHOR`
- 可选：`WECHAT_DEFAULT_DIGEST`
- 可选：`WECHAT_CONTENT_SOURCE_URL`
- 可选：`WECHAT_DEFAULT_THUMB_MEDIA_ID`

## 输出格式

```markdown
# AI每日简报 - [日期]

## Top 10 最热 / 最前沿消息

1. **[标题]** - [一句话摘要]
   链接: [URL]

## 更多新闻

### 模型 / 研究
- [标题] - [链接]

### AI 产品 / Agent
- [标题] - [链接]

### 开源项目
- [项目名] - Stars: N（累计） | 今日增长: N（24h） - [链接]
  [一句话介绍]

### 基础设施 / 硬件 / 安全
- [标题] - [链接]
```

## 要求

- Top 10 以技术、产品、开源为主
- Top 10 里优先放“新模型、新研究、新产品、新基础设施”，不要默认把多个 GitHub Trending 条目顶进前 10
- GitHub Trending 条目在 Top 10 中默认最多 2 条，并且要选当天最有代表性的项目，而不是按热度机械罗列
- 每条至少包含标题和链接，尽量补一句摘要
- 开源项目每条都要补一行一句话介绍，优先使用 GitHub Trending 的项目描述
- 商业新闻不允许为了凑数挤占 Top 10
- 数据来源只允许是微信公众号文章列表和 GitHub Trending；禁止混入外部检索结果
- 如果公众号抓取失败或 GitHub Trending 抓取失败，必须停止任务并明确说明失败步骤与原因
- 仅在用户只是要简报正文时，结果只输出简报正文，不要追加“如果你要，我可以继续…”之类的收尾话术
- 如果用户要求发邮件，先生成并写入 Markdown，再执行发送；最终响应只需要简短确认发送结果或失败原因，不要再重复整篇简报，除非用户明确要求同时展示正文
- 如果用户要求发到微信公众号，先生成并写入 Markdown，再执行草稿创建或发布；最终响应只需要简短确认结果或失败原因，不要再重复整篇简报，除非用户明确要求同时展示正文
