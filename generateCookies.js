const puppeteer = require("puppeteer");
const fs = require("fs");

(async () => {

const browser = await puppeteer.launch({
  headless: true,
  executablePath: "/usr/bin/chromium",
  args: [
    "--no-sandbox",
    "--disable-setuid-sandbox"
  ]
});

const page = await browser.newPage();

console.log("Abrindo login Google...");

await page.goto("https://accounts.google.com/signin/v2/identifier", {
  waitUntil: "networkidle2"
});

await page.type('input[type="email"]', process.env.YT_EMAIL);

await page.click("#identifierNext");

await new Promise(r => setTimeout(r, 3000));

await page.type('input[type="password"]', process.env.YT_PASSWORD);

await page.click("#passwordNext");

await page.waitForTimeout(8000);

console.log("Entrando no YouTube...");

await page.goto("https://www.youtube.com", {
  waitUntil: "networkidle2"
});

const cookies = await page.cookies();

let cookieTxt = "";

cookies.forEach(c => {
  cookieTxt += [
    ".youtube.com",
    "TRUE",
    c.path,
    c.secure ? "TRUE" : "FALSE",
    c.expires || "0",
    c.name,
    c.value
  ].join("\t") + "\n";
});

fs.writeFileSync("cookies.txt", cookieTxt);

console.log("cookies.txt gerado com conta logada");

await browser.close();

})();
