## 🚀 Anyrouter 自动签到领额度（GitHub Actions）

这是一个基于 GitHub Actions 的自动化脚本，用于定时登录自动续期 [anyrouter](https://anyrouter.top) 服务。

━━━━━━━━━━━━━━━━━━━━━━

### 🔐 Secrets 配置说明

| Secret 名称         | 是否必填 | 说明                                              |
|---------------------|----------|---------------------------------------------------|
| USER_ID            | ✅ 必填  | 用户ID,登录后右上角个人设置里进去就看到ID了,一般是6位数      |
| SESSION            | ✅ 必填  | SESSION 在cookie里获取，获取方式见下图                  |
| TG_BOT_TOKEN       | ❌ 可选  | Telegram Bot Token（用于发送通知）                     |
| TG_CHAT_ID         | ❌ 可选  | Telegram Chat ID（接收通知的用户或群组 ID）             |

━━━━━━━━━━━━━━━━━━━━━━

## 部署步骤
1：fork 本项目，在actions菜单允许工作流

2：在`setting`➡`secrets and variables`➡`Actions` 里添加上方必填的secrets

3：去actions菜单手动试运行工作流

### SESSION_TOKEN 获取
登录你的账号,按F12或页面空白处 右键➡检查➡选择应用程序或appcations 找到对应的字段点击获取对应的值，详情如图
<img width="1200" height="600" alt="image" src="https://github.com/user-attachments/assets/93c9bc86-0853-40ef-8f3f-c9322d879e87" />
