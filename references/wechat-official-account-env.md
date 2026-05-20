# 微信公众号发布环境变量

用于 `scripts/send_markdown_wechat.py`。

## 必填

- `WECHAT_APP_ID`
- `WECHAT_APP_SECRET`

## 常用可选项

- `WECHAT_AUTHOR`
- `WECHAT_DEFAULT_DIGEST`
- `WECHAT_CONTENT_SOURCE_URL`
- `WECHAT_DEFAULT_THUMB_MEDIA_ID`

## 权限与限制

- 需要公众号后台已开通相应接口权限
- 脚本默认只创建草稿，不会自动发布
- 只有显式传 `--publish` 才会提交发布任务
- 微信图文草稿要求封面，因此必须提供：
  - `WECHAT_DEFAULT_THUMB_MEDIA_ID`
  - 或 `--thumb-media-id`
  - 或 `--thumb-image`
- Markdown 中的图片默认会尝试上传到微信正文图片接口；如果不想自动处理，传 `--skip-image-upload`

## 示例

```bash
export WECHAT_APP_ID="wx123"
export WECHAT_APP_SECRET="secret"
export WECHAT_AUTHOR="AI Daily Bot"
export WECHAT_DEFAULT_THUMB_MEDIA_ID="ABC123MEDIAID"
```

先创建草稿：

```bash
python3 scripts/send_markdown_wechat.py /absolute/path/to/ai-news-daily-2026-05-20.md
```

先看请求体：

```bash
python3 scripts/send_markdown_wechat.py /absolute/path/to/ai-news-daily-2026-05-20.md --dry-run
```

用本地封面图并提交发布：

```bash
python3 scripts/send_markdown_wechat.py /absolute/path/to/ai-news-daily-2026-05-20.md \
  --thumb-image /absolute/path/to/cover.png \
  --publish
```
