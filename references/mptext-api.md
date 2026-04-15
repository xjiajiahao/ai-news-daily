# mptext API Notes

仅在需要修改脚本或排查接口问题时读取本文件。

## 认证

- Header: `X-Auth-Key: <MPTEXT_API_KEY>`
- 建议同时带：
  - `User-Agent: Mozilla/5.0`
  - `Accept: application/json`
- 校验接口：`GET /api/public/v1/authkey`

## 基础地址

- 默认：`https://down.mptext.top`
- 可通过环境变量 `MPTEXT_BASE_URL` 覆盖

## 接口

### 1. 搜索公众号

- `GET /api/public/v1/account?keyword=<关键词>`
- 文档来源：`https://docs.mptext.top/advanced/api`
- 当前脚本关注字段：
  - `list[].fakeid`
  - `list[].nickname`
  - `list[].alias`
  - `list[].signature`
  - `list[].verify_status`

### 2. 获取文章列表

- `GET /api/public/v1/article?fakeid=<fakeid>&begin=0&size=20`
- `size` 最大 20
- 当前脚本关注字段：
  - `articles[].title`
  - `articles[].link`
  - `articles[].digest`
  - `articles[].create_time`
  - `articles[].update_time`
  - `articles[].author_name`
  - `articles[].cover`

## 2026-04-15 实测结论

- `GET /api/public/v1/authkey` 在带 `User-Agent` 后可正常返回 `{"code":0,...}`
- 搜索接口返回顶层字段是 `list`
- 文章列表接口返回顶层字段是 `articles`
- 指定 7 个目标公众号都能解析到稳定候选项

## 目标源配置

- 见 `references/source_accounts.json`
- 其中保存：
  - 展示名称
  - 搜索关键词
  - 预期 `nickname`
  - 预期 `alias`
  - 2026-04-15 实测 `preferred_fakeid`
