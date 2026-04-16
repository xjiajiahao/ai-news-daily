---
name: ai-news-daily
description: 收集每日 AI 技术与产品动态，聚合 GitHub Trending 与指定微信公众号文章列表，生成偏技术/产品取向的简报；当用户明确要求时，将简报发送到指定邮箱
---

# AI 每日新闻简报

## 何时使用

当用户要看“今天 AI 有什么新东西”、“做一份 AI 日报”、“汇总最新 AI 技术/产品动态”、“Anything new?”时使用。

如果用户明确要求“把简报发到邮箱”“发给某个收件人”“邮件发送日报”，也继续使用这个 skill，不需要切到别的 skill。

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

微信公众号文章列表统一通过 `scripts/fetch_wechat_articles.py` 获取。

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

仅在需要改脚本或排查接口异常时，再读 `references/mptext-api.md`。

### 2. 收集 GitHub Trending

访问 `https://github.com/trending`。

重点关注：

- AI / ML / Agent / 多模态 / 语音 / 图像 / 推理 / 数据工具相关项目
- 项目描述
- 当日 Star 增长

### 3. 归并与筛选

默认优先级：

1. 技术突破：新模型、训练/推理方法、评测、系统优化、论文和开源代码
2. AI 产品：新功能上线、可体验产品、开发者工具、Agent 工作流
3. 开源生态：GitHub Trending 上的 AI 项目
4. 商业信息：只在直接影响技术路线、产品能力或开源生态时保留

处理规则：

- 优先“近 24 小时”内容
- 同一消息跨公众号重复时去重，保留信息量更高的链接
- 融资、估值、空泛战略表态默认降权

### 4. 写出 Markdown 简报

简报必须同时写成当前目录下的 Markdown 文件，文件名默认使用 `ai-news-daily-YYYY-MM-DD.md`。

如果用户没有单独指定文件名，就按这个默认文件名写出，后续发邮件也使用这个文件。

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
- SMTP 配置来自环境变量，具体见 `references/smtp-env.md`
- 如果缺少收件人邮箱地址，需要用一句简短问题向用户补齐
- 如果网络被限制，不能假装已发送，必须明确报告限制

发信环境变量：

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- 可选：`SMTP_FROM_NAME`
- 可选：`SMTP_SECURITY`，可用值为 `auto`、`ssl`、`starttls`、`plain`

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
- [项目名] - Stars: N | 今日增长: N - [链接]
  [一句话介绍]

### 基础设施 / 硬件 / 安全
- [标题] - [链接]
```

## 要求

- Top 10 以技术、产品、开源为主
- 每条至少包含标题和链接，尽量补一句摘要
- 开源项目每条都要补一行一句话介绍，优先使用 GitHub Trending 的项目描述
- 商业新闻不允许为了凑数挤占 Top 10
- 仅在用户只是要简报正文时，结果只输出简报正文，不要追加“如果你要，我可以继续…”之类的收尾话术
- 如果用户要求发邮件，先生成并写入 Markdown，再执行发送；最终响应只需要简短确认发送结果或失败原因，不要再重复整篇简报，除非用户明确要求同时展示正文
