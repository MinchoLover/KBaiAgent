import fs from "node:fs";
import path from "node:path";

const CDP_PORT = Number(process.env.KBAI_CDP_PORT || "9224");
const APP_URL = process.env.KBAI_APP_URL || "http://127.0.0.1:8504/";
const REPOSITORY = process.cwd();
const GOLDEN_EXPORT_PDF = path.join(
  REPOSITORY,
  "dataset/golden_demo/golden_export_contract.pdf",
);
const GOLDEN_IMPORT_PDF = path.join(
  REPOSITORY,
  "dataset/golden_import_hedge_demo/golden_import_payable_contract.pdf",
);
const OUTPUT_DIRECTORY = "/private/tmp";
const BROWSER_DOWNLOAD_DIRECTORY = path.join(
  OUTPUT_DIRECTORY,
  `kbai-final-browser-downloads-${Date.now()}`,
);
fs.mkdirSync(BROWSER_DOWNLOAD_DIRECTORY, { recursive: true });

for (const requiredPath of [GOLDEN_EXPORT_PDF, GOLDEN_IMPORT_PDF]) {
  if (!fs.existsSync(requiredPath)) {
    throw new Error(`Required fixture is missing: ${requiredPath}`);
  }
}

const pages = await (
  await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)
).json();
const page = pages.find((item) => item.type === "page");
if (!page) throw new Error("Chrome page not found");

const socket = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});

let nextId = 1;
const pending = new Map();
const browserErrors = [];
socket.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (message.id && pending.has(message.id)) {
    const handlers = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) handlers.reject(new Error(JSON.stringify(message.error)));
    else handlers.resolve(message.result);
    return;
  }
  if (message.method === "Runtime.exceptionThrown") {
    browserErrors.push({
      kind: "exception",
      text:
        message.params?.exceptionDetails?.exception?.description ||
        message.params?.exceptionDetails?.text ||
        "unknown browser exception",
    });
  }
  if (message.method === "Log.entryAdded") {
    const entry = message.params?.entry;
    if (entry && entry.level === "error") {
      browserErrors.push({ kind: "log", text: entry.text });
    }
  }
});

function command(method, params = {}) {
  const id = nextId++;
  socket.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
  });
}

async function evaluate(expression) {
  const result = await command("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (result.exceptionDetails) {
    throw new Error(JSON.stringify(result.exceptionDetails));
  }
  return result.result.value;
}

async function sleep(milliseconds) {
  await new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitFor(expression, timeoutMs = 30000, message = expression) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      if (await evaluate(expression)) return;
    } catch (error) {
      lastError = error;
    }
    await sleep(250);
  }
  throw new Error(
    `Timed out waiting for ${message}${lastError ? `: ${lastError}` : ""}`,
  );
}

async function waitForText(text, timeoutMs = 30000) {
  const normalized = text.replace(/\s+/g, " ").trim();
  await waitFor(
    `document.body && document.body.innerText.replace(/\\s+/g, " ").includes(${JSON.stringify(
      normalized,
    )})`,
    timeoutMs,
    `text ${JSON.stringify(text)}`,
  );
}

async function setViewport(width, height, mobile) {
  await command("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile,
    screenWidth: width,
    screenHeight: height,
  });
  await sleep(500);
}

async function screenshot(filename) {
  const target = path.join(OUTPUT_DIRECTORY, filename);
  const result = await command("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: false,
  });
  const bytes = Buffer.from(result.data, "base64");
  fs.writeFileSync(target, bytes);
  if (bytes.length < 5000) {
    throw new Error(`Screenshot is unexpectedly small: ${target}`);
  }
  evidence.screenshots.push({ path: target, bytes: bytes.length });
  return target;
}

async function visibleText() {
  return evaluate(`(() => {
    const main = document.querySelector("[data-testid='stMain']") ||
      document.querySelector("main") || document.body;
    return main ? main.innerText.replace(/\\s+/g, " ").trim() : "";
  })()`);
}

async function clickKey(key) {
  const clicked = await evaluate(`(() => {
    const wrapper = document.querySelector(${JSON.stringify(`.st-key-${key}`)});
    const target = wrapper && Array.from(wrapper.querySelectorAll("button, a"))
      .find((item) => item.offsetParent !== null && !item.disabled);
    if (!target) return false;
    target.scrollIntoView({block: "center", inline: "nearest"});
    target.click();
    return true;
  })()`);
  if (!clicked) throw new Error(`Clickable key not found: ${key}`);
  await sleep(700);
}

async function clickButton(text, exact = true) {
  const clicked = await evaluate(`(() => {
    const expected = ${JSON.stringify(text)};
    const target = Array.from(document.querySelectorAll("button"))
      .find((item) => item.offsetParent !== null && !item.disabled &&
        (${exact ? "(item.innerText || '').trim() === expected" : "(item.innerText || '').includes(expected)"}));
    if (!target) return false;
    target.scrollIntoView({block: "center", inline: "nearest"});
    target.click();
    return true;
  })()`);
  if (!clicked) throw new Error(`Button not found: ${text}`);
  await sleep(700);
}

async function clickChoice(text) {
  const clicked = await evaluate(`(() => {
    const expected = ${JSON.stringify(text)};
    const target = Array.from(document.querySelectorAll("label"))
      .find((item) => item.offsetParent !== null &&
        (item.innerText || "").trim() === expected);
    if (!target) return false;
    target.scrollIntoView({block: "center", inline: "nearest"});
    target.click();
    return true;
  })()`);
  if (!clicked) throw new Error(`Choice not found: ${text}`);
  await sleep(700);
}

async function clickCheckboxKey(key) {
  const clicked = await evaluate(`(() => {
    const wrapper = document.querySelector(${JSON.stringify(`.st-key-${key}`)});
    const input = wrapper && wrapper.querySelector("input");
    if (!input) return false;
    if (!input.checked) {
      const label = wrapper.querySelector("label");
      (label || input).click();
    }
    return true;
  })()`);
  if (!clicked) throw new Error(`Checkbox not found: ${key}`);
  await waitFor(
    `Boolean(document.querySelector(${JSON.stringify(
      `.st-key-${key} input`,
    )})?.checked)`,
    5000,
    `checkbox ${key} to be checked`,
  );
}

async function inputValue(key) {
  return evaluate(`document.querySelector(${JSON.stringify(
    `.st-key-${key} input`,
  )})?.value || null`);
}

async function setInputValue(key, value) {
  const changed = await evaluate(`(() => {
    const input = document.querySelector(${JSON.stringify(
      `.st-key-${key} input`,
    )});
    if (!input) return false;
    input.scrollIntoView({block: "center"});
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      "value",
    ).set;
    setter.call(input, ${JSON.stringify(value)});
    input.dispatchEvent(new Event("input", {bubbles: true}));
    input.dispatchEvent(new Event("change", {bubbles: true}));
    input.blur();
    return input.value;
  })()`);
  if (changed !== value) {
    throw new Error(`Input ${key} did not accept ${value}; got ${changed}`);
  }
  await sleep(200);
}

async function setSliderBoundary(key, keyboardKey, expectedValue) {
  const coordinates = await evaluate(`(() => {
    const wrapper = document.querySelector(${JSON.stringify(`.st-key-${key}`)});
    const slider = wrapper && wrapper.querySelector("[role='slider']");
    if (!slider) return null;
    slider.scrollIntoView({block: "center"});
    const track = slider.parentElement.getBoundingClientRect();
    return {
      x: ${JSON.stringify(keyboardKey)} === "Home"
        ? track.left + 1
        : track.right - 1,
      y: track.top + (track.height / 2),
    };
  })()`);
  if (!coordinates) throw new Error(`Slider not found: ${key}`);
  await command("Input.dispatchMouseEvent", {
    type: "mouseMoved",
    x: coordinates.x,
    y: coordinates.y,
  });
  await command("Input.dispatchMouseEvent", {
    type: "mousePressed",
    x: coordinates.x,
    y: coordinates.y,
    button: "left",
    clickCount: 1,
  });
  await command("Input.dispatchMouseEvent", {
    type: "mouseReleased",
    x: coordinates.x,
    y: coordinates.y,
    button: "left",
    clickCount: 1,
  });
  await waitFor(
    `Number(document.querySelector(${JSON.stringify(
      `.st-key-${key} [role='slider']`,
    )})?.getAttribute("aria-valuenow")) === Number(${JSON.stringify(
      expectedValue,
    )})`,
    10000,
    `slider ${key} value ${expectedValue}`,
  );
  await sleep(500);
}

async function clickExpander(text) {
  const clicked = await evaluate(`(() => {
    const expected = ${JSON.stringify(text)};
    const summary = Array.from(document.querySelectorAll("details summary"))
      .find((item) => item.offsetParent !== null &&
        (item.innerText || "").includes(expected));
    if (!summary) return false;
    const details = summary.closest("details");
    if (!details.open) summary.click();
    summary.scrollIntoView({block: "center"});
    return true;
  })()`);
  if (!clicked) throw new Error(`Expander not found: ${text}`);
  await sleep(350);
}

async function closeExpander(text) {
  await evaluate(`(() => {
    const expected = ${JSON.stringify(text)};
    const summary = Array.from(document.querySelectorAll("details summary"))
      .find((item) => (item.innerText || "").includes(expected));
    const details = summary && summary.closest("details");
    if (details?.open) summary.click();
  })()`);
  await sleep(250);
}

async function setUploadFile(filePath, requireAttached = true) {
  const document = await command("DOM.getDocument", { depth: -1, pierce: true });
  const result = await command("DOM.querySelector", {
    nodeId: document.root.nodeId,
    selector: "input[type='file']",
  });
  if (!result.nodeId) throw new Error("Upload input not found");
  await command("DOM.setFileInputFiles", {
    nodeId: result.nodeId,
    files: [filePath],
  });
  await sleep(1200);
  if (requireAttached) {
    await waitFor(
      `Array.from(document.querySelectorAll("input[type='file']"))
        .some((item) => item.files && item.files.length === 1)`,
      10000,
      "uploaded file to be attached",
    );
  }
}

async function responsiveEvidence(name) {
  return evaluate(`(() => {
    const visible = Array.from(document.querySelectorAll("body *"))
      .filter((item) => item.offsetParent !== null)
      .filter((item) => {
        const sidebar = item.closest("[data-testid='stSidebar']");
        return !sidebar || sidebar.getBoundingClientRect().right > 0;
      });
    const isInsideHorizontalClip = (item) => {
      let parent = item.parentElement;
      while (parent && parent !== document.body) {
        const overflowX = getComputedStyle(parent).overflowX;
        if (["auto", "scroll", "hidden", "clip"].includes(overflowX)) {
          const rect = parent.getBoundingClientRect();
          if (rect.left >= -2 && rect.right <= window.innerWidth + 2) return true;
        }
        parent = parent.parentElement;
      }
      return false;
    };
    const offenders = visible.filter((item) => !isInsideHorizontalClip(item))
      .map((item) => {
      const rect = item.getBoundingClientRect();
      return {
        tag: item.tagName,
        text: (item.innerText || "").trim().slice(0, 80),
        left: Math.round(rect.left),
        right: Math.round(rect.right),
        width: Math.round(rect.width),
      };
    }).filter((item) => item.left < -2 || item.right > window.innerWidth + 2)
      .filter((item) => !["STYLE", "SCRIPT"].includes(item.tag))
      .slice(0, 12);
    const actions = visible.filter((item) =>
      item.matches("button, a[download], input, [role='radio']") &&
      !(item.closest("[data-testid='stSidebar']") &&
        getComputedStyle(item.closest("[data-testid='stSidebar']")).visibility === "hidden")
    ).map((item) => {
      const rect = item.getBoundingClientRect();
      return {
        text: (item.innerText || item.getAttribute("aria-label") || "").trim().slice(0, 80),
        left: Math.round(rect.left),
        right: Math.round(rect.right),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      };
    }).filter((item) => item.width > 0 && item.height > 0);
    return {
      name: ${JSON.stringify(name)},
      viewport: [window.innerWidth, window.innerHeight],
      documentWidth: document.documentElement.scrollWidth,
      horizontalOverflow:
        document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      overflowOffenders: offenders,
      shortestActionHeight: actions.length
        ? Math.min(...actions.map((item) => item.height))
        : null,
      shortActions: actions.filter((item) => item.height < 38).slice(0, 10),
      cutActions: actions.filter((item) =>
        item.left < -2 || item.right > window.innerWidth + 2
      ).slice(0, 10),
      visiblePrimaryActions: Array.from(document.querySelectorAll("button[kind='primary']"))
        .filter((item) => item.offsetParent !== null)
        .map((item) => (item.innerText || "").trim())
        .filter(Boolean),
    };
  })()`);
}

async function captureResponsive(name) {
  await setViewport(1440, 1000, false);
  await evaluate(`(() => {
    const main = document.querySelector("[data-testid='stMain']");
    if (main) main.scrollTop = 0;
    window.scrollTo(0, 0);
  })()`);
  await sleep(250);
  evidence.responsive.push(await responsiveEvidence(`${name}-desktop`));
  await screenshot(`kbai-final-desktop-${name}.png`);
  await setViewport(390, 844, true);
  await evaluate(`(() => {
    const main = document.querySelector("[data-testid='stMain']");
    if (main) main.scrollTop = 0;
    window.scrollTo(0, 0);
  })()`);
  await sleep(250);
  evidence.responsive.push(await responsiveEvidence(`${name}-mobile`));
  await screenshot(`kbai-final-mobile-${name}.png`);
  await setViewport(1440, 1000, false);
}

async function captureResponsiveAtText(name, text) {
  const scrollToText = async () => {
    const scrolled = await evaluate(`(() => {
      const expected = ${JSON.stringify(text)};
      const target = Array.from(document.querySelectorAll("h1, h2, h3, h4"))
        .find((item) => item.offsetParent !== null &&
          (item.innerText || "").includes(expected));
      if (!target) return false;
      target.scrollIntoView({block: "start", inline: "nearest"});
      return true;
    })()`);
    if (!scrolled) throw new Error(`Heading not found for screenshot: ${text}`);
    await sleep(500);
  };
  await setViewport(1440, 1000, false);
  await scrollToText();
  evidence.responsive.push(await responsiveEvidence(`${name}-desktop`));
  await screenshot(`kbai-final-desktop-${name}.png`);
  await setViewport(390, 844, true);
  await scrollToText();
  evidence.responsive.push(await responsiveEvidence(`${name}-mobile`));
  await screenshot(`kbai-final-mobile-${name}.png`);
  await setViewport(1440, 1000, false);
}

async function downloadByKey(key, outputName) {
  const before = new Map(
    fs.readdirSync(BROWSER_DOWNLOAD_DIRECTORY).map((filename) => {
      const stat = fs.statSync(path.join(BROWSER_DOWNLOAD_DIRECTORY, filename));
      return [filename, { mtimeMs: stat.mtimeMs, size: stat.size }];
    }),
  );
  await clickKey(key);
  const deadline = Date.now() + 30000;
  let downloadedPath = null;
  while (Date.now() < deadline) {
    const candidates = fs.readdirSync(BROWSER_DOWNLOAD_DIRECTORY)
      .filter((filename) => !filename.endsWith(".crdownload"))
      .filter((filename) => {
        const previous = before.get(filename);
        if (!previous) return true;
        const current = fs.statSync(path.join(BROWSER_DOWNLOAD_DIRECTORY, filename));
        return current.mtimeMs > previous.mtimeMs || current.size !== previous.size;
      });
    if (candidates.length === 1) {
      const candidate = path.join(BROWSER_DOWNLOAD_DIRECTORY, candidates[0]);
      if (fs.statSync(candidate).size > 0) {
        downloadedPath = candidate;
        break;
      }
    }
    await sleep(200);
  }
  if (!downloadedPath) throw new Error(`Browser download did not finish: ${key}`);
  const outputPath = path.join(OUTPUT_DIRECTORY, outputName);
  fs.copyFileSync(downloadedPath, outputPath);
  const size = fs.statSync(outputPath).size;
  const filename = path.basename(downloadedPath);
  evidence.downloads.push({
    key,
    path: outputPath,
    filename,
    bytes: size,
  });
  return { filename, size, path: outputPath };
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function assertIncludes(text, expected, context) {
  assert(text.includes(expected), `${context} is missing ${JSON.stringify(expected)}`);
}

function validateConsultationArtifacts(
  markdownArtifact,
  jsonArtifact,
  requireGoldenPriorities,
) {
  const markdown = fs.readFileSync(markdownArtifact.path, "utf8");
  const jsonText = fs.readFileSync(jsonArtifact.path, "utf8");
  const packet = JSON.parse(jsonText);
  const expectedPriorities = [
    "수출대금 회수 보호 상담",
    "환율 관리 상담",
    "운영자금 버퍼·수출대금 회수시점 상담",
  ];
  const priorities = packet.consultation_priorities.map((item) => item.title);
  const official = packet.official_candidate_shortlist?.candidates || [];
  assert(
    packet.company_summary.settlement_date === "2026-08-20",
    "Consultation JSON settlement date mismatch",
  );
  if (requireGoldenPriorities) {
    assert(
      JSON.stringify(priorities) === JSON.stringify(expectedPriorities),
      `Consultation Top 3 mismatch: ${JSON.stringify(priorities)}`,
    );
    const statistics = packet.trade_statistics;
    assert(statistics?.status === "OFFICIAL_FIXTURE", "Consultation trade statistics source mismatch");
    assert(statistics?.summary?.scope === "COUNTRY_TOTAL", "Consultation trade statistics scope mismatch");
    assert(statistics?.summary?.latest_12m_export_usd === "8282425000", "Consultation trade export total mismatch");
    assert(statistics?.summary?.latest_12m_import_usd === "6154122000", "Consultation trade import total mismatch");
    assert(statistics?.summary?.latest_12m_balance_usd === "2128302000", "Consultation trade balance mismatch");
    assert(statistics?.summary?.latest_period === "2026-06", "Consultation trade latest period mismatch");
    assert(statistics?.summary?.hs_code === null, "Consultation unexpectedly inferred HS Code");
    for (const expected of [
      "거래국 무역 통계",
      "USD 8,282,425,000",
      "USD 6,154,122,000",
      "USD 2,128,302,000",
      "HS Code",
    ]) {
      assertIncludes(markdown, expected, "Consultation Markdown trade statistics");
    }
  } else {
    assert(priorities.length === 3, `Direct-upload Top 3 count mismatch: ${priorities.length}`);
  }
  assert(official.length <= 3, `Official candidate count exceeds three: ${official.length}`);
  const identities = new Set(
    official.map((item) => `${item.institution}|${item.name}|${item.source.url}`),
  );
  assert(identities.size === official.length, "Official candidate list contains duplicates");
  for (const expected of ["2026-08-20", "USD 100,000", ...priorities]) {
    assertIncludes(markdown, expected, "Consultation Markdown");
  }
  const forbidden = [
    "RM 전송 완료",
    "상담 예약 완료",
    "보험 인수 승인",
    "OPENAI_API_KEY",
  ];
  for (const value of forbidden) {
    assert(!markdown.includes(value), `Consultation Markdown contains ${value}`);
    assert(!jsonText.includes(value), `Consultation JSON contains ${value}`);
  }
  const secretPattern = /\bsk-[A-Za-z0-9_-]{16,}\b/;
  assert(!secretPattern.test(markdown), "Consultation Markdown contains a secret pattern");
  assert(!secretPattern.test(jsonText), "Consultation JSON contains a secret pattern");
  return {
    settlementDate: packet.company_summary.settlement_date,
    priorities,
    officialCandidates: official.map((item) => [item.institution, item.name]),
  };
}

function validateIntegratedArtifacts(markdownArtifact, jsonArtifact) {
  const markdown = fs.readFileSync(markdownArtifact.path, "utf8");
  const report = JSON.parse(fs.readFileSync(jsonArtifact.path, "utf8"));
  const confirmed = report.workflow.confirmed_transaction;
  assert(confirmed.due_date === "2026-08-20", "Report confirmed due date mismatch");
  assert(
    report.stage0.confirmation.confirmed_values.settlement_date === "2026-08-20",
    "Report Stage 0 settlement date mismatch",
  );
  assertIncludes(markdown, "2026-08-20", "Integrated report Markdown");
  assertIncludes(
    markdown,
    "workflow.confirmed_transaction.due_date",
    "Integrated report Markdown",
  );
  if (report.consultation?.trade_statistics?.status === "OFFICIAL_FIXTURE") {
    const statistics = report.consultation.trade_statistics;
    assert(
      statistics.summary.latest_12m_export_usd === "8282425000" &&
        statistics.summary.latest_12m_import_usd === "6154122000" &&
        statistics.summary.latest_12m_balance_usd === "2128302000",
      "Integrated report trade statistics mismatch",
    );
    assertIncludes(markdown, "## 8. 거래국 무역 통계", "Integrated report Markdown");
    assertIncludes(markdown, "USD 8,282,425,000", "Integrated report Markdown");
    assertIncludes(markdown, "+56.4%", "Integrated report Markdown");
    assertIncludes(markdown, "-16.7%", "Integrated report Markdown");
    assert(
      !markdown.includes("56.36383442142403103102139311%"),
      "Integrated report exposes unrounded trade-statistics percentage",
    );
    assert(
      statistics.summary.export_yoy_pct === "56.36383442142403103102139311",
      "Integrated report JSON lost original trade-statistics precision",
    );
  }
  return {
    confirmedDueDate: confirmed.due_date,
    stage0SettlementDate:
      report.stage0.confirmation.confirmed_values.settlement_date,
  };
}

async function confirmCurrentDocument() {
  await clickExpander("거래정보 수정 및 재검증");
  await clickButton("수정 내용 저장 및 다시 검증");
  await waitFor(
    `Boolean(document.querySelector(".st-key-confirm_company_role_widget input"))`,
    30000,
    "document confirmation checkboxes",
  );
  for (const key of [
    "confirm_company_role_widget",
    "confirm_trade_type_widget",
    "confirm_currency_widget",
    "confirm_amount_widget",
    "confirm_due_widget",
  ]) {
    await clickCheckboxKey(key);
  }
  await clickButton("원문과 확인하고 금융분석 시작");
  await waitForText("환율 위험 범위 준비하기");
}

async function runFinancialAnalysis(expectRegisteredDefaults) {
  await clickKey("load_stage1");
  await waitForText("회사 자금 입력");
  assertIncludes(await visibleText(), "결제 예정일 2026-08-20", "Stage 1 UI");
  await clickCheckboxKey("trade_risk_confirm_widget");
  await clickButton("대금 회수조건 확인");
  await waitForText("대금 회수조건 수정");

  const defaults = {
    currentCash: await inputValue("stage2_current_cash_widget"),
    minimumBuffer: await inputValue("stage2_minimum_buffer_widget"),
    creditLimit: await inputValue("stage2_credit_limit_widget"),
    acceptableLoss: await inputValue("stage2_acceptable_loss_widget"),
  };
  evidence.companyFundDefaults.push({ expectRegisteredDefaults, ...defaults });
  if (expectRegisteredDefaults) {
    assert(defaults.currentCash?.replaceAll(",", "") === "20000000.00", "Golden demo cash default mismatch");
    assert(defaults.minimumBuffer?.replaceAll(",", "") === "10000000.00", "Golden demo buffer mismatch");
    assert(defaults.creditLimit?.replaceAll(",", "") === "0.00", "Golden demo credit mismatch");
    assert(defaults.acceptableLoss?.replaceAll(",", "") === "5000000.00", "Golden demo loss mismatch");
  } else {
    assert(
      defaults.currentCash?.replaceAll(",", "") !== "20000000.00",
      "Direct upload incorrectly inherited registered-demo finance defaults",
    );
  }
  await captureResponsive(
    expectRegisteredDefaults ? "company-funds" : "actual-company-funds",
  );
  await clickButton("환율·자금 위험 계산하기");
  try {
    await waitForText("분석 핵심 결과", 30000);
  } catch (error) {
    const diagnostic = (await visibleText()).slice(-3000);
    throw new Error(`${error.message}\nFinancial page diagnostic:\n${diagnostic}`);
  }
  const text = await visibleText();
  const expectedResultText = expectRegisteredDefaults
    ? [
        "기준 원화 수취액",
        "140,000,000원",
        "환율 -5% 원화 수취액",
        "133,000,000원",
        "7,000,000원",
        "스트레스 후 예상 현금 8,000,000원",
        "최소 유지 운영자금 10,000,000원",
        "운영자금 부족 2,000,000원",
        "현금 적자 0원",
        "지급 또는 post-credit 부족 0원",
      ]
    : [
        "기준 원화 수취액",
        "환율 -5% 원화 수취액",
        "결제 예정일 2026-08-20",
        "USD 80,000",
        "현금 적자",
        "지급 또는 post-credit 부족",
      ];
  for (const expected of expectedResultText) {
    assertIncludes(text, expected, "Financial result UI");
  }
  if (expectRegisteredDefaults) {
    for (const expected of [
      "거래국 무역 통계",
      "한국–브라질 교역 동향",
      "국가 전체 교역",
      "USD 8,282,425,000",
      "USD 6,154,122,000",
      "USD 2,128,302,000",
      "2024-07",
      "2026-06",
      "HS Code 미확인",
      "공식 fixture · API-free 데모",
    ]) {
      assertIncludes(text, expected, "Trade statistics UI");
    }
  } else {
    assertIncludes(
      text,
      "공식 무역통계 API 키 설정이 필요합니다",
      "Live trade statistics unavailable state",
    );
    assertIncludes(
      text,
      "현재 환율·현금흐름 계산에는 영향을 주지 않습니다",
      "Live trade statistics boundary",
    );
  }
  return text;
}

async function runConsultationAndDownloads(prefix) {
  await clickKey("go_to_consultation_from_summary");
  await waitForText("상담 Top 3");
  let text = await visibleText();
  const titles = [
    "수출대금 회수 보호 상담",
    "환율 관리 상담",
    "운영자금 버퍼·수출대금 회수시점 상담",
  ];
  if (prefix === "demo") {
    const positions = titles.map((title) => text.indexOf(title));
    assert(positions.every((value) => value >= 0), "Consultation Top 3 is incomplete");
    assert(positions[0] < positions[1] && positions[1] < positions[2], "Top 3 order changed");
    await clickExpander("후보 탐색 기준");
    await setSliderBoundary("stage3_max_forward_widget", "Home", "0");
    await setSliderBoundary("stage3_staged_risk_widget", "End", "1");
  } else {
    const cardCount = await evaluate(`Array.from(document.querySelectorAll(
      ".consultation-card"
    )).filter((item) => item.offsetParent !== null).length`);
    assert(cardCount === 3, `Direct-upload consultation card count: ${cardCount}`);
  }
  await clickKey("optimize_stage3");
  await waitFor(
    `document.body.innerText.includes("세 가지 관점의 계산상 비교안입니다") ||
      document.body.innerText.replace(/\\s+/g, " ").includes(
        "현재 입력된 조건에서는 제시할 수 있는 헤지 비교안이 없습니다."
      )`,
    30000,
    "Stage 3 result",
  );
  text = await visibleText();
  if (text.includes("현재 입력된 조건에서는 제시할 수 있는 헤지 비교안이 없습니다.")) {
    assert(!text.includes("헤지 엔진 미구현"), "No-candidate state claims engine is unimplemented");
    assert(!text.includes("NO_FEASIBLE_CANDIDATE"), "Internal Stage 3 code is visible by default");
  }
  await clickKey("search_stage4");
  await waitFor(
    `Boolean(document.querySelector(".st-key-download_stage4"))`,
    30000,
    "official candidate shortlist",
  );
  text = await visibleText();
  const expectedOfficials = [
    "단기수출보험 검토",
    "은행 선물환·외환스왑 상담",
    "환변동보험 검토",
  ];
  if (prefix === "demo") {
    const officialPositions = expectedOfficials.map((title) => text.indexOf(title));
    assert(
      officialPositions.every((value) => value >= 0) &&
        officialPositions[0] < officialPositions[1] &&
        officialPositions[1] < officialPositions[2],
      `Official candidates missing or reordered: ${JSON.stringify(officialPositions)}`,
    );
  }
  await captureResponsive(prefix === "demo" ? "consultation" : "actual-consultation");

  await clickKey("workflow_nav_download");
  await waitForText("상담 준비서 다운로드");
  await clickExpander("JSON 데이터 및 분석 근거");
  await clickExpander("고급 · 통합 보고서와 기술정보");
  await clickKey("generate_report");
  await waitForText("통합 상담 리포트가 완성되었습니다", 30000);
  await captureResponsive(prefix === "demo" ? "download" : "actual-download");

  const consultationMarkdown = await downloadByKey(
    "stage5_handoff_download",
    `kbai-final-${prefix}-consultation.md`,
  );
  const consultationJson = await downloadByKey(
    "download_consultation_packet_json_stage5",
    `kbai-final-${prefix}-consultation.json`,
  );
  const reportMarkdown = await downloadByKey(
    "download_report_md",
    `kbai-final-${prefix}-integrated-report.md`,
  );
  const reportJson = await downloadByKey(
    "download_report_json",
    `kbai-final-${prefix}-integrated-report.json`,
  );

  for (const expected of [
    "KB_상담_준비서_2026-08-20.md",
    "KB_상담_데이터_2026-08-20.json",
    "KB_통합_금융분석_2026-08-20.md",
    "KB_통합_금융분석_2026-08-20.json",
  ]) {
    assert(
      evidence.downloads.some((item) => item.filename === expected),
      `Download filename is missing: ${expected}`,
    );
  }
  return {
    consultation: validateConsultationArtifacts(
      consultationMarkdown,
      consultationJson,
      prefix === "demo",
    ),
    integrated: validateIntegratedArtifacts(reportMarkdown, reportJson),
  };
}

const evidence = {
  chrome: null,
  screenshots: [],
  responsive: [],
  downloads: [],
  companyFundDefaults: [],
  home: null,
  demo: null,
  actualDocument: null,
  browserErrors,
};

try {
  await command("Page.enable");
  await command("Runtime.enable");
  await command("Log.enable");
  await command("Browser.setDownloadBehavior", {
    behavior: "allow",
    downloadPath: BROWSER_DOWNLOAD_DIRECTORY,
    eventsEnabled: true,
  });
  evidence.chrome = await evaluate(`({
    userAgent: navigator.userAgent,
    platform: navigator.platform,
    language: navigator.language,
  })`);

  await setViewport(1440, 1000, false);
  await command("Page.navigate", { url: APP_URL });
  await waitForText("KBaiAgent");
  if (await evaluate(`Boolean(document.querySelector(".st-key-new_analysis button"))`)) {
    await clickKey("new_analysis");
  }
  await waitForText("3분 데모 시작하기");
  const homeText = await visibleText();
  assertIncludes(homeText, "내 거래문서 분석하기", "Home");
  assert(!homeText.includes("샘플 수출 거래로 체험하기"), "Legacy home CTA remains");
  for (const hiddenTechnicalTerm of ["OPENAI_API_KEY", "provider", "fixture", "모델 ID"]){
    assert(
      !homeText.includes(hiddenTechnicalTerm),
      `Technical setting competes on home: ${hiddenTechnicalTerm}`,
    );
  }
  await captureResponsive("home");
  evidence.home = {
    primary: "3분 데모 시작하기",
    secondary: "내 거래문서 분석하기",
    technicalTermsHidden: true,
  };

  await setViewport(1440, 1000, false);
  await clickExpander("분석 환경 및 고급 설정");
  await screenshot("kbai-final-desktop-advanced-settings.png");
  await closeExpander("분석 환경 및 고급 설정");

  await clickKey("service_sample_export");
  await waitForText("문서 분석하고 거래정보 채우기");
  await clickKey("analyze_document");
  await waitForText("USD 100,000");
  let transactionText = await visibleText();
  for (const expected of [
    "USD 100,000",
    "USD 20,000",
    "USD 80,000",
    "2026-08-20",
    "선지급",
    "확인 필요",
  ]) {
    assertIncludes(transactionText, expected, "Golden transaction UI");
  }
  await captureResponsive("transaction");
  await clickExpander("상세 거래정보");
  await clickExpander("원문 근거");
  transactionText = await visibleText();
  assertIncludes(transactionText, "2026-07-29", "Detailed transaction UI");
  assertIncludes(transactionText, "2026-08-05", "Detailed transaction UI");
  await screenshot("kbai-final-desktop-transaction-details.png");
  await setViewport(390, 844, true);
  await screenshot("kbai-final-mobile-transaction-details.png");
  await setViewport(1440, 1000, false);
  await confirmCurrentDocument();
  await runFinancialAnalysis(true);
  await captureResponsive("analysis-result");
  await captureResponsiveAtText("trade-statistics", "한국–브라질 교역 동향");
  evidence.demo = await runConsultationAndDownloads("demo");

  await clickKey("new_analysis");
  await waitForText("3분 데모 시작하기");
  await clickKey("service_register_document");
  await waitForText("거래문서 업로드");
  await clickKey("analyze_document");
  await waitForText("실제 문서 분석에서는 문서를 업로드하거나 등록된 합성문서를 선택하세요.");
  await captureResponsive("upload-error");

  await clickChoice("판매자 · SELLER");
  await setUploadFile(GOLDEN_EXPORT_PDF);
  const firstUploadName = await evaluate(`document.querySelector("input[type='file']")?.files?.[0]?.name`);
  await setUploadFile(GOLDEN_EXPORT_PDF);
  const repeatedUploadName = await evaluate(`document.querySelector("input[type='file']")?.files?.[0]?.name`);
  assert(firstUploadName === repeatedUploadName, "Same-file reupload did not remain attached");
  await clickKey("analyze_document");
  await waitForText("USD 100,000");
  await captureResponsive("actual-transaction");

  await clickExpander("거래정보 수정 및 재검증");
  await setInputValue("review_document_number_widget", "EXP-2026-BR-RECHECK");
  await clickButton("수정 내용 저장 및 다시 재검증", true).catch(async () => {
    await clickButton("수정 내용 저장 및 다시 검증");
  });
  await waitFor(
    `Boolean(document.querySelector(".st-key-confirm_company_role_widget input"))`,
    30000,
    "document confirmation checkboxes",
  );
  for (const key of [
    "confirm_company_role_widget",
    "confirm_trade_type_widget",
    "confirm_currency_widget",
    "confirm_amount_widget",
    "confirm_due_widget",
  ]) {
    await clickCheckboxKey(key);
  }
  await clickExpander("원문 근거");
  await screenshot("kbai-final-desktop-actual-evidence.png");
  await clickButton("원문과 확인하고 금융분석 시작");
  await waitForText("환율 위험 범위 준비하기");
  await runFinancialAnalysis(false);
  await captureResponsive("actual-analysis-result");
  evidence.actualDocument = {
    firstUploadName,
    repeatedUploadName,
    documentNumber: "EXP-2026-BR-RECHECK",
    downloads: await runConsultationAndDownloads("actual"),
  };

  await clickKey("workflow_nav_transaction");
  await waitForText("거래정보 수정 및 재검증");
  await clickExpander("문서 업로드·다시 추출");
  await setUploadFile(GOLDEN_IMPORT_PDF, false);
  await waitForText("문서·역할·모드 변경을 감지해 이전 계산 결과를 비웠습니다.");
  const staleText = await visibleText();
  assert(!staleText.includes("분석 핵심 결과"), "Old financial result survived different-file upload");
  evidence.actualDocument.differentUpload = path.basename(GOLDEN_IMPORT_PDF);
  evidence.actualDocument.previousResultCleared = true;

  for (const item of evidence.responsive) {
    assert(!item.horizontalOverflow, `Horizontal overflow: ${item.name}`);
    assert(
      item.overflowOffenders.length === 0,
      `Visible overflow offenders: ${item.name} ${JSON.stringify(item.overflowOffenders)}`,
    );
    assert(
      item.cutActions.length === 0,
      `Cut actions: ${item.name} ${JSON.stringify(item.cutActions)}`,
    );
  }
  const meaningfulErrors = browserErrors.filter((item) =>
    !item.text.includes("favicon") &&
    !item.text.includes("Download is disallowed"),
  );
  assert(
    meaningfulErrors.length === 0,
    `Browser console errors: ${JSON.stringify(meaningfulErrors)}`,
  );

  const evidencePath = path.join(
    OUTPUT_DIRECTORY,
    "kbai-final-browser-evidence.json",
  );
  fs.writeFileSync(evidencePath, `${JSON.stringify(evidence, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify({ evidencePath, ...evidence }, null, 2)}\n`);
} finally {
  socket.close();
}
