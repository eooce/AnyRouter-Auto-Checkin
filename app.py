#!/usr/bin/env python3
"""
Ayrouter 自动领币脚本
=====================
功能：
1. 使用 Cookie 登录 https://ayrouter.top/console
2. 获取当前余额
3. 等待 3 秒后刷新页面，重新获取余额，检查是否有变化
4. 检查 Session 有效期是否大于 2 天，若小于则通过 GitHub PAT 更新 Secret
5. 发送 Telegram 通知

环境变量：
  USER_ID                - 用户 ID（默认 173952）
  SESSION                - Session Cookie 值（必填）
  SITE_URL               - 站点地址（默认 https://ayrouter.top）
  TG_BOT_TOKEN           - Telegram Bot Token
  TG_CHAT_ID             - Telegram Chat ID
  GITHUB_TOKEN           - GitHub Personal Access Token（需 repo 权限）
  GITHUB_REPOSITORY      - 仓库名（格式 owner/repo）
  SESSION_TTL_DAYS       - Session 有效期天数（默认 7）
  SESSION_THRESHOLD_DAYS - Session 更新阈值天数（默认 2）
  QUOTA_PER_DOLLAR       - Quota 兑换比例（默认 500000，即 500000 quota = $1）
"""

import os
import sys
import base64
import json
import re
import traceback
from datetime import datetime, timezone, timedelta

import requests
from playwright.sync_api import sync_playwright

# ============================================================
# 配置
# ============================================================
USER_ID = os.getenv("USER_ID", "173952")
SESSION = os.getenv("SESSION", "MTc4Mjk2Nzk5N3xEWDhFQVFMX2dBQUJFQUVRQUFEXzVQLUFBQWNHYzNSeWFXNW5EQVlBQkhKdmJHVURhVzUwQkFJQUFnWnpkSEpwYm1jTUNBQUdjM1JoZEhWekEybHVkQVFDQUFJR2MzUnlhVzVuREFjQUJXZHliM1Z3Qm5OMGNtbHVad3dKQUFka1pXWmhkV3gwQm5OMGNtbHVad3dGQUFOaFptWUdjM1J5YVc1bkRBWUFCRWhOUjFnR2MzUnlhVzVuREEwQUMyOWhkWFJvWDNOMFlYUmxCbk4wY21sdVp3d09BQXhCTkhZeWNrdDFia05XVUVNR2MzUnlhVzVuREFRQUFtbGtBMmx1ZEFRRkFQMEZUd0FHYzNSeWFXNW5EQW9BQ0hWelpYSnVZVzFsQm5OMGNtbHVad3dRQUE1c2FXNTFlR1J2WHpFM016azFNZz09fKughFbFl4sHiBeB3s4UApu9M0ph8mPSn9n9OMYZnGfr")
SITE_URL = os.getenv("SITE_URL", "https://ayrouter.top")

# Telegram
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")

# GitHub PAT（用于更新 Secrets）
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "")

# Session 有效期与阈值
SESSION_TTL_DAYS = int(os.getenv("SESSION_TTL_DAYS", "7"))
SESSION_THRESHOLD_DAYS = int(os.getenv("SESSION_THRESHOLD_DAYS", "2"))

# Quota 兑换比例（New API 默认 500000 quota = $1）
QUOTA_PER_DOLLAR = int(os.getenv("QUOTA_PER_DOLLAR", "500000"))

# Cookie 域名
SITE_DOMAIN = "ayrouter.top"


# ============================================================
# 工具函数
# ============================================================
def log(level: str, msg: str):
    """带时间戳的日志输出"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)


def decode_session_timestamp(session_value: str) -> int | None:
    """
    从 gorilla securecookie 格式的 SESSION 值中解码创建时间戳。

    Cookie 值整体是 base64 编码，解码后格式为: timestamp|data|hmac
    第一部分是 Unix 时间戳（秒）。
    """
    if not session_value:
        return None

    # 策略 1：整体 base64 解码后分割
    try:
        padded = session_value + "=" * (4 - len(session_value) % 4) if len(session_value) % 4 else session_value
        try:
            decoded = base64.urlsafe_b64decode(padded)
        except Exception:
            decoded = base64.b64decode(padded)

        parts = decoded.split(b"|")
        if parts and parts[0].strip().isdigit():
            return int(parts[0].strip())
    except Exception as e:
        log("WARN", f"base64 解码失败: {e}")

    # 策略 2：直接按 | 分割（cookie 值本身含 | 的情况）
    try:
        parts = session_value.split("|")
        if parts and parts[0].strip().isdigit():
            return int(parts[0].strip())
    except Exception:
        pass

    return None


def check_session_expiry(session_value: str, ttl_days: int = 7, threshold_days: int = 2):
    """
    检查 Session 是否即将过期。

    Returns:
        (remaining_days, need_update)
        remaining_days - 剩余有效天数（浮点），无法判断时为 None
        need_update    - 是否需要更新
    """
    timestamp = decode_session_timestamp(session_value)
    if not timestamp:
        log("WARN", "无法解码 Session 时间戳，跳过期检查")
        return None, False

    created_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    expiry_time = created_time + timedelta(days=ttl_days)
    now = datetime.now(tz=timezone.utc)

    remaining = expiry_time - now
    remaining_days = remaining.total_seconds() / 86400

    # 转为本地时间显示
    created_local = created_time.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    expiry_local = expiry_time.astimezone().strftime("%Y-%m-%d %H:%M:%S")

    log("INFO", f"Session 创建时间: {created_local}")
    log("INFO", f"Session 过期时间: {expiry_local}")
    log("INFO", f"剩余有效时间: {remaining_days:.2f} 天")

    need_update = remaining_days < threshold_days
    if need_update:
        log("WARN", f"Session 剩余 {remaining_days:.2f} 天 < {threshold_days} 天阈值，需要更新！")

    return remaining_days, need_update


def update_github_secret(token: str, repository: str, secret_name: str, secret_value: str) -> bool:
    """通过 GitHub REST API 更新 Actions Secret"""
    if not token:
        log("WARN", "GITHUB_TOKEN 未配置，跳过 Secret 更新")
        return False
    if not repository:
        log("WARN", "GITHUB_REPOSITORY 未配置，跳过 Secret 更新")
        return False

    try:
        from nacl import public, encoding
    except ImportError:
        log("ERROR", "缺少 pynacl 库，请运行: pip install pynacl")
        return False

    try:
        owner, repo = repository.split("/")
    except ValueError:
        log("ERROR", f"仓库名格式错误: {repository}，应为 owner/repo")
        return False

    api_base = "https://api.github.com"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        # 1. 获取仓库公钥
        log("INFO", f"获取仓库 {repository} 的公钥...")
        resp = requests.get(
            f"{api_base}/repos/{owner}/{repo}/actions/secrets/public-key",
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        key_data = resp.json()

        # 2. 加密 secret 值
        public_key = public.PublicKey(key_data["key"].encode(), encoding.Base64Encoder())
        sealed_box = public.SealedBox(public_key)
        encrypted = sealed_box.encrypt(secret_value.encode())

        # 3. 更新 secret
        log("INFO", f"更新 Secret: {secret_name}")
        payload = {
            "encrypted_value": base64.b64encode(encrypted).decode(),
            "key_id": key_data["key_id"],
        }
        resp = requests.put(
            f"{api_base}/repos/{owner}/{repo}/actions/secrets/{secret_name}",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()

        log("INFO", f"GitHub Secret '{secret_name}' 更新成功！")
        return True

    except requests.exceptions.HTTPError as e:
        log("ERROR", f"GitHub API HTTP 错误: {e}")
        try:
            log("ERROR", f"响应内容: {resp.text}")
        except Exception:
            pass
        return False
    except Exception as e:
        log("ERROR", f"更新 GitHub Secret 失败: {e}")
        return False


def send_telegram(message: str) -> bool:
    """发送 Telegram 消息"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        log("WARN", "Telegram 配置不完整，跳过发送")
        print(f"--- 消息内容 ---\n{message}\n---------------")
        return False

    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TG_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
        }
        resp = requests.post(url, json=data, timeout=30)
        resp.raise_for_status()
        log("INFO", "Telegram 消息发送成功")
        return True
    except Exception as e:
        log("ERROR", f"Telegram 发送失败: {e}")
        return False


# ============================================================
# 余额提取
# ============================================================
def get_balance_from_api(page):
    """
    通过 /api/user/self 接口获取余额信息。

    New API / One API 的用户接口返回:
    {
      "success": true,
      "data": {
        "id": 173952,
        "quota": 262500000,        // 剩余 quota
        "used_quota": 50000000,    // 已使用 quota
        ...
      }
    }
    """
    try:
        result = page.evaluate("""
            async () => {
                try {
                    const res = await fetch('/api/user/self', {
                        credentials: 'include',
                        headers: { 'Accept': 'application/json' },
                    });
                    return await res.json();
                } catch(e) {
                    return { success: false, message: e.message };
                }
            }
        """)

        if result and result.get("success"):
            data = result.get("data", {})
            return {
                "quota": data.get("quota", 0),
                "used_quota": data.get("used_quota", 0),
                "username": data.get("username", ""),
                "raw": data,
            }
        else:
            log("WARN", f"API 返回非成功: {result}")
    except Exception as e:
        log("WARN", f"API 获取余额失败: {e}")

    return None


def get_balance_from_dom(page) -> str | None:
    """
    从页面 DOM 中提取余额文本。
    尝试匹配 $X.XX 或 X.XX$ 格式。
    """
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass

    try:
        content = page.content()

        # 匹配 $数字 格式（如 $525.00）
        matches = re.findall(r'\$\s*[\d,]+\.?\d*', content)
        if matches:
            # 过滤掉过小的值（可能是其他金额如 $0.01）
            valid = [m for m in matches if float(m.replace('$', '').replace(',', '').strip()) > 0]
            if valid:
                return valid[0].strip()

        # 匹配 数字$ 格式
        matches = re.findall(r'[\d,]+\.?\d*\s*\$', content)
        if matches:
            valid = [m for m in matches if float(m.replace('$', '').replace(',', '').strip()) > 0]
            if valid:
                return valid[0].strip()

    except Exception as e:
        log("WARN", f"DOM 提取余额失败: {e}")

    return None


def format_balance(api_result, dom_balance) -> str:
    """
    格式化余额显示，统一输出为 数字$ 格式。

    优先使用 DOM 提取的值，其次从 API quota 计算。
    """
    # 优先使用 DOM 值
    if dom_balance:
        # 提取纯数字
        num_str = dom_balance.replace('$', '').replace(',', '').strip()
        try:
            num = float(num_str)
            if num == int(num):
                return f"{int(num)}$"
            return f"{num:.2f}$"
        except ValueError:
            return dom_balance

    # 从 API quota 计算
    if api_result:
        quota = api_result.get("quota", 0)
        balance = quota / QUOTA_PER_DOLLAR
        if balance == int(balance):
            return f"{int(balance)}$"
        return f"{balance:.2f}$"

    return "N/A"


# ============================================================
# 主流程
# ============================================================
def run_checkin():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log("INFO", "=" * 50)
    log("INFO", "Ayrouter 领币脚本启动")
    log("INFO", f"时间: {now_str}")
    log("INFO", f"用户 ID: {USER_ID}")
    log("INFO", "=" * 50)

    if not SESSION:
        log("ERROR", "SESSION 未配置，请设置 SESSION 环境变量")
        sys.exit(1)

    with sync_playwright() as p:
        # ---------- 启动浏览器 ----------
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )

        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        # ---------- 设置 Cookies ----------
        cookies_to_set = [
            {
                "name": "session",
                "value": SESSION,
                "domain": SITE_DOMAIN,
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax",
            },
            {
                "name": "user_id",
                "value": USER_ID,
                "domain": SITE_DOMAIN,
                "path": "/",
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax",
            },
        ]
        context.add_cookies(cookies_to_set)
        log("INFO", "Cookies 已设置")

        page = context.new_page()

        # ---------- 访问控制台 ----------
        log("INFO", f"正在访问 {SITE_URL}/console ...")
        try:
            page.goto(f"{SITE_URL}/console", wait_until="networkidle", timeout=30000)
        except Exception as e:
            log("ERROR", f"页面加载失败: {e}")
            browser.close()
            send_telegram(
                f"❌ <b>Ayrouter 页面加载失败</b>\n"
                f"👤 账户: {USER_ID}\n"
                f"⏱️ 时间: {now_str}\n"
                f"错误: {e}"
            )
            sys.exit(1)

        # 等待页面渲染
        page.wait_for_timeout(3000)

        current_url = page.url
        log("INFO", f"当前 URL: {current_url}")

        # ---------- 检查登录状态 ----------
        if "/login" in current_url:
            log("ERROR", "登录失败！Cookie 可能已过期，被重定向到 /login")
            browser.close()
            send_telegram(
                f"❌ <b>Ayrouter 登录失败</b>\n"
                f"👤 账户: {USER_ID}\n"
                f"⏱️ 时间: {now_str}\n"
                f"📝 原因: Cookie 已过期，请尽快更新 SESSION"
            )
            sys.exit(1)

        log("INFO", "登录成功！")

        # ---------- 获取初始余额 ----------
        log("INFO", "获取初始余额...")
        api_result_1 = get_balance_from_api(page)
        dom_balance_1 = get_balance_from_dom(page)
        first_balance = format_balance(api_result_1, dom_balance_1)
        log("INFO", f"初始余额: {first_balance}")
        if api_result_1:
            log("INFO", f"API Quota: {api_result_1.get('quota')}, Used: {api_result_1.get('used_quota')}")

        # ---------- 尝试点击领币/签到按钮 ----------
        log("INFO", "查找领币/签到按钮...")
        clicked = False
        for text in ["签到", "领取", "领币", "每日", "每日签到", "Check-in", "Claim", "Daily", "Sign"]:
            try:
                btn = page.locator(f"button:has-text('{text}')").first
                if btn.is_visible(timeout=2000):
                    btn.click()
                    clicked = True
                    log("INFO", f"点击了 '{text}' 按钮")
                    page.wait_for_timeout(2000)
                    break
            except Exception:
                continue

        if not clicked:
            log("INFO", "未找到领币按钮，可能无需手动领取（访问页面即自动领取）")

        # ---------- 等待 3 秒后刷新页面 ----------
        log("INFO", "等待 3 秒后刷新页面...")
        page.wait_for_timeout(3000)
        page.reload(wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)

        # ---------- 获取刷新后余额 ----------
        log("INFO", "获取刷新后余额...")
        api_result_2 = get_balance_from_api(page)
        dom_balance_2 = get_balance_from_dom(page)
        second_balance = format_balance(api_result_2, dom_balance_2)
        log("INFO", f"刷新后余额: {second_balance}")
        if api_result_2:
            log("INFO", f"API Quota: {api_result_2.get('quota')}, Used: {api_result_2.get('used_quota')}")

        # ---------- 检查余额变化 ----------
        balance_changed = first_balance != second_balance
        if balance_changed:
            log("INFO", f"✅ 余额发生变化: {first_balance} → {second_balance}")
        else:
            log("INFO", f"余额未变化: {first_balance}")

        # ---------- 检查是否有新的 Session Cookie ----------
        cookies = context.cookies()
        new_session = None
        for cookie in cookies:
            if cookie["name"] == "session":
                if cookie["value"] != SESSION:
                    new_session = cookie["value"]
                    log("INFO", "检测到服务器返回了新的 Session Cookie")
                break

        # ---------- 检查 Session 有效期 ----------
        session_to_check = new_session if new_session else SESSION
        remaining_days, need_update = check_session_expiry(
            session_to_check, SESSION_TTL_DAYS, SESSION_THRESHOLD_DAYS
        )

        # ---------- 若 Session 即将过期，更新 GitHub Secret ----------
        session_status = ""
        if need_update:
            log("WARN", "Session 即将过期，尝试通过 GitHub PAT 更新 Secret...")
            session_to_save = new_session if new_session else SESSION
            success = update_github_secret(GITHUB_TOKEN, GITHUB_REPOSITORY, "SESSION", session_to_save)
            if success:
                session_status = f"✅ Session 已自动更新（剩余 {remaining_days:.1f} 天）" if remaining_days else "✅ Session 已自动更新"
            else:
                session_status = f"⚠️ Session 剩余 {remaining_days:.1f} 天，Secret 更新失败，请手动更新" if remaining_days else "⚠️ Session 需手动更新"
        else:
            if remaining_days is not None:
                session_status = f"✅ Session 有效（剩余 {remaining_days:.1f} 天）"
            else:
                session_status = "⚠️ Session 有效期未知"

        browser.close()

        # ---------- 发送 Telegram 通知 ----------
        message = (
            f"🎁 <b>Anyrouter 领币通知</b>\n"
            f"👤 登录账户: {USER_ID}\n"
            f"💰 昨日余额: {first_balance}\n"
            f"💰 当前余额: {second_balance}\n"
            f"⏱️ 登录时间: {now_str}\n"
            f"📋 {session_status}"
        )

        print()
        log("INFO", "=== 通知内容 ===")
        print(message)
        print()

        send_telegram(message)

    log("INFO", "=== 脚本执行完毕 ===")


def main():
    try:
        run_checkin()
    except KeyboardInterrupt:
        log("WARN", "用户中断")
        sys.exit(130)
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        log("ERROR", f"脚本执行出错: {error_msg}")
        log("ERROR", traceback.format_exc())
        send_telegram(
            f"❌ <b>Ayrouter 脚本异常</b>\n"
            f"👤 账户: {USER_ID}\n"
            f"⏱️ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"📝 错误: {error_msg}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
