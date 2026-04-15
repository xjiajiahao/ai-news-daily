# SMTP Environment

Required variables:

- `SMTP_HOST`: SMTP server hostname, for example `smtp.qq.com`
- `SMTP_PORT`: SMTP port, usually `465` for SSL or `587` for STARTTLS
- `SMTP_USER`: Sender email address or SMTP username
- `SMTP_PASSWORD`: SMTP password or provider authorization code

Optional variables:

- `SMTP_FROM_NAME`: Friendly display name for the `From` header
- `SMTP_SECURITY`: Force connection mode. Supported values: `auto`, `ssl`, `starttls`, `plain`

QQ Mail example:

```bash
export SMTP_HOST=smtp.qq.com
export SMTP_PORT=465
export SMTP_USER='your-account@qq.com'
export SMTP_PASSWORD='qq-mail-authorization-code'
export SMTP_FROM_NAME='Your Name'
```

Notes:

- QQ Mail usually requires the SMTP authorization code from the mailbox settings page instead of the account login password.
- `SMTP_SECURITY=auto` chooses `ssl` for port `465`, `starttls` for port `587`, and `plain` otherwise.
