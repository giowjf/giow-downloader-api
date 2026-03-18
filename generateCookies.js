import fs from "fs";
import puppeteer from "puppeteer";

const COOKIE_PATH = "./cookies.txt";

function convertToNetscape(cookies) {
  return cookies.map(c => {
    return [
      c.domain,
      "TRUE",
      c.path,
      c.secure ? "TRUE" : "FALSE",
      Math.floor(Date.now() / 1000) + 3600 * 24 * 7,
      c.name,
      c.value
    ].join("\t");
  }).join("\n");
}

(async () => {
  const browser = await puppeteer.launch({
    headless: false,
    userDataDir: "/app/chrome-data",
    args: ["--no-sandbox", "--disable-setuid-sandbox"]
  });

  const page = await browser.newPage();

  console.log("👉 Abra o YouTube e faça login manualmente...");
  await page.goto("https://youtube.com", { waitUntil: "networkidle2" });

  await new Promise(r => setTimeout(r, 120000));

  const cookies = await page.cookies();
  fs.writeFileSync("cookies.txt", convertToNetscape(cookies));

  console.log("✅ cookies.txt atualizado!");

  await browser.close();
})();
