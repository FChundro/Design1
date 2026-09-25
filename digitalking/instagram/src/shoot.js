// Screenshots each generated HTML page at its exact size.
const path = require('path');
const { execSync } = require('child_process');
const { chromium } = require(path.join(execSync('npm root -g').toString().trim(), 'playwright'));
const jobs = require('./jobs.json');
(async () => {
  const browser = await chromium.launch();
  for (const [url, out, w, h] of jobs) {
    const page = await browser.newPage({ viewport: { width: w, height: h } });
    await page.goto(url);
    await page.screenshot({ path: out });
    await page.close();
  }
  await browser.close();
})();
