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

console.log("cookies.txt gerado");

await browser.close();

})();
