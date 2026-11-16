import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import puppeteer from "puppeteer";
import { renderMermaid } from "@mermaid-js/mermaid-cli";

const [input, output, executablePath] = process.argv.slice(2);
if (!input || !output || !executablePath) {
  process.exit(2);
}

let browser;
try {
  const definition = await readFile(input, "utf8");
  const initialPage = pathToFileURL(resolve(
    dirname(fileURLToPath(import.meta.url)),
    "node_modules", "@mermaid-js", "mermaid-cli", "dist", "index.html",
  )).href;
  browser = await puppeteer.launch({
    executablePath,
    headless: "shell",
    args: [
      "--disable-background-networking",
      "--proxy-server=http://127.0.0.1:9",
      "--proxy-bypass-list=<-loopback>",
    ],
  });
  const newPage = browser.newPage.bind(browser);
  browser.newPage = async () => {
    const page = await newPage();
    page.on("request", (request) => {
      const target = new URL(request.url());
      if (request.url() !== initialPage && target.origin !== "https://mermaid-cli-intercept.invalid") {
        return request.abort("blockedbyclient", 100);
      }
    });
    return page;
  };
  const result = await renderMermaid(browser, definition, "png", {
    mermaidConfig: { securityLevel: "strict", maxTextSize: 100000 },
    fontEmbed: false,
  });
  await writeFile(output, result.data);
} catch {
  console.error("No se pudo validar o renderizar el diagrama Mermaid.");
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
}
