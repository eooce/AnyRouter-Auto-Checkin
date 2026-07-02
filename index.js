import { chromium } from "playwright";
import { sendTG } from "./tg.js";
import { updateSessionSecret } from "./github.js";

const USER_ID = process.env.USER_ID;
const SESSION = process.env.SESSION;

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

await page.goto("https://anyrouter.top/console", {
    waitUntil: "networkidle"
});

if (page.url().includes("/login")) {
    throw new Error("Cookie 已失效");
}

async function getBalance() {

    const locator = page.locator(".text-lg.font-semibold").first();

    const txt = await locator.innerText();

    return parseFloat(txt.replace("$", ""));
}

const before = await getBalance();

console.log(before);

await page.waitForTimeout(3000);

await page.reload({
    waitUntil: "networkidle"
});

const after = await getBalance();

console.log(after);

const cookies = await context.cookies();

const sessionCookie = cookies.find(c => c.name === "SESSION");

if (sessionCookie && sessionCookie.expires > 0) {

    const remain = sessionCookie.expires - Math.floor(Date.now() / 1000);

    if (remain < 2 * 24 * 3600) {

        console.log("Session 即将过期");

        await updateSessionSecret(sessionCookie.value);
    }
}

await sendTG({
    user: USER_ID,
    before,
    after
});

await browser.close();
