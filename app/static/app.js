/* 航海测深图拼接裁决 —— 页面逻辑。
 * 页面只负责录入与渲染：拼接顺序、配对、未配对刻度、误差等一切证据
 * 均来自服务端 /api/adjudicate 的真实响应，本地不做任何求解。
 */
"use strict";

const TYPE_LABELS = {
  major: "主刻线",
  intermediate: "中级刻线",
  minor: "次刻线",
};

const SAMPLE = [
  { id: 1, scales: "100, 110, 120, 130, 140", types: "major, minor, intermediate, minor, major" },
  { id: 2, scales: "105, 115, 125, 135, 150", types: "minor, intermediate, minor, major, major" },
  { id: 3, scales: "98, 108, 118, 128, 138", types: "intermediate, minor, major, minor, intermediate" },
];

let limits = { minSegments: 3, maxSegments: 6, minMarks: 4, maxMarks: 10 };
let allowedTypes = Object.keys(TYPE_LABELS);

const segmentsEl = document.getElementById("segments");
const errorEl = document.getElementById("error");
const resultPanel = document.getElementById("result-panel");
const addBtn = document.getElementById("add-segment");
const adjudicateBtn = document.getElementById("adjudicate");

function typeLabel(t) {
  return TYPE_LABELS[t] ? `${TYPE_LABELS[t]}（${t}）` : t;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/* ---------- 录入卡片 ---------- */

function segmentCount() {
  return segmentsEl.querySelectorAll(".segment-card").length;
}

function refreshButtons() {
  const count = segmentCount();
  addBtn.disabled = count >= limits.maxSegments;
  segmentsEl.querySelectorAll(".remove-segment").forEach((btn) => {
    btn.disabled = count <= limits.minSegments;
  });
}

function addSegment(data) {
  const index = segmentCount() + 1;
  const card = el("div", "segment-card");

  const head = el("div", "segment-head");
  head.appendChild(el("span", "segment-title", `第 ${index} 段`));
  const removeBtn = el("button", "remove-segment", "移除");
  removeBtn.type = "button";
  removeBtn.addEventListener("click", () => {
    card.remove();
    renumber();
    refreshButtons();
  });
  head.appendChild(removeBtn);
  card.appendChild(head);

  const idField = el("label", "field");
  idField.appendChild(el("span", null, "编号"));
  const idInput = el("input", "seg-id");
  idInput.type = "number";
  idInput.min = "1";
  idInput.step = "1";
  idInput.value = data ? data.id : index;
  idField.appendChild(idInput);
  card.appendChild(idField);

  const scaleField = el("label", "field");
  scaleField.appendChild(el("span", null, "刻度（严格递增整数，逗号或空格分隔）"));
  const scaleInput = el("input", "seg-scales");
  scaleInput.type = "text";
  scaleInput.placeholder = "例如：100, 110, 120, 130";
  scaleInput.value = data ? data.scales : "";
  scaleField.appendChild(scaleInput);
  card.appendChild(scaleField);

  const typeField = el("label", "field");
  typeField.appendChild(el("span", null, "刻线类型（与刻度一一对应）"));
  const typeInput = el("input", "seg-types");
  typeInput.type = "text";
  typeInput.placeholder = `例如：${allowedTypes.join(", ")}`;
  typeInput.value = data ? data.types : "";
  typeField.appendChild(typeInput);
  card.appendChild(typeField);

  segmentsEl.appendChild(card);
  refreshButtons();
}

function renumber() {
  segmentsEl.querySelectorAll(".segment-title").forEach((node, i) => {
    node.textContent = `第 ${i + 1} 段`;
  });
}

/* ---------- 录入收集（仅做格式转换，合法性由服务端裁决） ---------- */

function splitTokens(text) {
  return text.split(/[\s,，、]+/).map((t) => t.trim()).filter(Boolean);
}

function toNumberOrRaw(token) {
  const n = Number(token);
  return Number.isInteger(n) ? n : token;
}

function collectPayload() {
  const segments = [];
  segmentsEl.querySelectorAll(".segment-card").forEach((card) => {
    const idRaw = card.querySelector(".seg-id").value.trim();
    segments.push({
      id: idRaw === "" ? null : toNumberOrRaw(idRaw),
      scales: splitTokens(card.querySelector(".seg-scales").value).map(toNumberOrRaw),
      types: splitTokens(card.querySelector(".seg-types").value),
    });
  });
  return { segments };
}

/* ---------- 结果渲染（全部数据来自 API 响应） ---------- */

function clearResult() {
  resultPanel.hidden = true;
  document.getElementById("order").replaceChildren();
  document.getElementById("summary").replaceChildren();
  document.getElementById("boundaries").replaceChildren();
  document.getElementById("unpaired").replaceChildren();
}

function showError(message) {
  errorEl.textContent = message;
  errorEl.hidden = false;
}

function clearError() {
  errorEl.hidden = true;
  errorEl.textContent = "";
}

function renderResult(data) {
  const orderEl = document.getElementById("order");
  orderEl.appendChild(el("span", "order-label", "拼接顺序："));
  data.order.forEach((id, i) => {
    if (i > 0) orderEl.appendChild(el("span", "order-arrow", "→"));
    orderEl.appendChild(el("span", "order-chip", `段 ${id}`));
  });

  const summaryEl = document.getElementById("summary");
  summaryEl.appendChild(el("span", "summary-item", `总配对数：${data.totalPairs}`));
  summaryEl.appendChild(el("span", "summary-item", `总拼接误差：${data.totalError}`));

  const boundariesEl = document.getElementById("boundaries");
  data.boundaries.forEach((b) => {
    const card = el("div", "boundary-card");
    card.appendChild(el("h4", null, `段 ${b.left} → 段 ${b.right}`));
    const meta = el("div", "boundary-meta");
    meta.appendChild(el("span", null, `平移量：${b.delta >= 0 ? "+" : ""}${b.delta}`));
    meta.appendChild(el("span", null, `配对数：${b.pairCount}`));
    card.appendChild(meta);

    const table = el("table", "pairs-table");
    const headRow = el("tr");
    ["左段刻度", "右段刻度", "刻线类型"].forEach((h) => headRow.appendChild(el("th", null, h)));
    table.appendChild(headRow);
    b.pairs.forEach((p) => {
      const row = el("tr");
      row.appendChild(el("td", null, String(p.leftValue)));
      row.appendChild(el("td", null, String(p.rightValue)));
      row.appendChild(el("td", null, typeLabel(p.type)));
      table.appendChild(row);
    });
    card.appendChild(table);
    boundariesEl.appendChild(card);
  });

  const unpairedEl = document.getElementById("unpaired");
  data.unpaired.forEach((seg) => {
    const row = el("div", "unpaired-row");
    row.appendChild(el("span", "order-chip", `段 ${seg.id}`));
    if (seg.marks.length === 0) {
      row.appendChild(el("span", "unpaired-none", "无（全部参与配对）"));
    } else {
      seg.marks.forEach((m) => {
        row.appendChild(el("span", "mark-chip", `${m.value} · ${typeLabel(m.type)}`));
      });
    }
    unpairedEl.appendChild(row);
  });

  resultPanel.hidden = false;
}

/* ---------- 裁决 ---------- */

async function adjudicate() {
  clearResult();
  clearError();
  adjudicateBtn.disabled = true;
  try {
    const resp = await fetch("/api/adjudicate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectPayload()),
    });
    const data = await resp.json();
    if (resp.ok) {
      renderResult(data);
    } else {
      const err = data && data.error ? data.error : {};
      showError(`裁决失败：${err.message || "未知错误"}${err.field ? `（${err.field}）` : ""}`);
    }
  } catch (e) {
    showError(`裁决请求失败：${e.message}`);
  } finally {
    adjudicateBtn.disabled = false;
  }
}

/* ---------- 初始化 ---------- */

async function loadMeta() {
  const hint = document.getElementById("meta-hint");
  try {
    const resp = await fetch("/api/meta");
    const meta = await resp.json();
    limits = meta.limits;
    allowedTypes = meta.types;
    hint.textContent =
      `每段 ${limits.minMarks}–${limits.maxMarks} 个严格递增整数刻度；` +
      `共 ${limits.minSegments}–${limits.maxSegments} 段；` +
      `刻线类型：${allowedTypes.map(typeLabel).join("、")}。`;
  } catch (e) {
    hint.textContent = "约束信息加载失败，仍可录入并交由服务端校验。";
  }
  refreshButtons();
}

addBtn.addEventListener("click", () => addSegment());
adjudicateBtn.addEventListener("click", adjudicate);

SAMPLE.forEach(addSegment);
loadMeta();
