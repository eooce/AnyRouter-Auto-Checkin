import { chromium } from "playwright";
import fetch from "node-fetch";

const USER_ID = process.env.USER_ID || 173952;
const SESSION = process.env.SESSION || 'MTc4Mjk2Nzk5N3xEWDhFQVFMX2dBQUJFQUVRQUFEXzVQLUFBQWNHYzNSeWFXNW5EQVlBQkhKdmJHVURhVzUwQkFJQUFnWnpkSEpwYm1jTUNBQUdjM1JoZEhWekEybHVkQVFDQUFJR2MzUnlhVzVuREFjQUJXZHliM1Z3Qm5OMGNtbHVad3dKQUFka1pXWmhkV3gwQm5OMGNtbHVad3dGQUFOaFptWUdjM1J5YVc1bkRBWUFCRWhOUjFnR2MzUnlhVzVuREEwQUMyOWhkWFJvWDNOMFlYUmxCbk4wY21sdVp3d09BQXhCTkhZeWNrdDFia05XVUVNR2MzUnlhVzVuREFRQUFtbGtBMmx1ZEFRRkFQMEZUd0FHYzNSeWFXNW5EQW9BQ0hWelpYSnVZVzFsQm5OMGNtbHVad3dRQUE1c2FXNTFlR1J2WHpFM016azFNZz09fKughFbFl4sHiBeB3s4UApu9M0ph8mPSn9n9OMYZnGfr';

const TG_BOT_TOKEN = process.env.TG_BOT_TOKEN;
const TG_CHAT_ID = process.env.TG_CHAT_ID;

function now() {
    return new Date().toLocaleString("zh-CN", {
        hour12: false,
        timeZone: "Asia/Shanghai"
    });
}

async function sendTG(message) {

    if (!TG_BOT_TOKEN || !TG_CHAT_ID) {
        console.log("未配置TG");
        return;
    }

    await fetch(
        `https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage`,
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                chat_id: TG_CHAT_ID,
                text: message
            })
        }
    );
}

(async () => {

    const browser = await chromium.launch({
        headless: true
    });

    const context = await browser.newContext();

    await context.addCookies([
        {
            name: "USER_ID",
            value: USER_ID,
            domain: "anyrouter.top",
            path: "/"
        },
        {
            name: "SESSION",
            value: SESSION,
            domain: "anyrouter.top",
            path: "/",
            httpOnly: true
        }
    ]);

    const page = await context.newPage();

    console.log("打开控制台...");

    await page.goto(
        "https://anyrouter.top/console",
        {
            waitUntil: "networkidle"
        }
    );

    if (page.url().includes("/login")) {

        console.log("Cookie失效");

        await sendTG(`❌ Anyrouter 登录失败

👤 用户：${USER_ID}

时间：${now()}
`);

        await browser.close();

        process.exit(1);
    }

    console.log("登录成功");

    async function getBalance() {

        const balance = await page.locator("text=当前余额")
            .locator("xpath=following-sibling::*[1]")
            .innerText();

        return parseFloat(balance.replace("$", ""));
    }

    const oldBalance = await getBalance();

    console.log("余额:", oldBalance);

    await page.waitForTimeout(3000);

    await page.reload({
        waitUntil: "networkidle"
    });

    const newBalance = await getBalance();

    console.log("刷新余额:", newBalance);

    let status = "余额无变化";

    if (newBalance > oldBalance) {

        status = `余额增加 ${newBalance - oldBalance}$`;

    } else if (newBalance < oldBalance) {

        status = `余额减少 ${oldBalance - newBalance}$`;
    }

    const text =

`🎁 Anyrouter 余额通知

👤 登录账户: ${USER_ID}

💰 初始余额: ${oldBalance}$

💰 当前余额: ${newBalance}$

📈 状态: ${status}

⏱️ 检查时间: ${now()}
`;

    console.log(text);

    await sendTG(text);

    await browser.close();

})();
