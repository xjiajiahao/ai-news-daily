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
- 微信图文草稿要求封面；默认使用 `asset/ai-news-daily.png` 作为主封面，并使用 `asset/ai-news-daily-small.png` 作为 1:1 小封面
- 微信草稿接口只有一个封面素材字段；脚本会合成封面素材，并设置 `pic_crop_235_1` / `pic_crop_1_1`
- 封面上传成功后会按 `WECHAT_APP_ID` 和封面内容哈希缓存 `media_id`，图片未变化时自动复用；如需强制重传，传 `--refresh-thumb-media`
- 如需强制复用已有封面素材，可传 `--thumb-media-id`；此模式无法指定独立小封面
- Markdown 中的图片默认会尝试上传到微信正文图片接口；如果不想自动处理，传 `--skip-image-upload`
- 草稿默认开启留言且允许所有用户留言；如需关闭，传 `--no-open-comment`

## 示例

```bash
export WECHAT_APP_ID="wx123"
export WECHAT_APP_SECRET="secret"
export WECHAT_AUTHOR="AI Daily Bot"
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
