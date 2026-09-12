// Draws the server's engine rectangles (mm, Y up) as SVG. It flips Y and scales;
// every rectangle, size and position comes from the engine, never from this file.
import { GROUP, KIND, fmt, pair } from "./messages.js";

const NS = "http://www.w3.org/2000/svg";
const round = (value) => Math.round(value * 1000) / 1000;
// Labels are sized against the drawing; a narrow panel gets relatively larger text.
const divisor = (host) => (host.clientWidth > 0 && host.clientWidth < 600 ? 28 : 42);

function add(parent, name, attrs = {}, text) {
  const el = document.createElementNS(NS, name);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, typeof value === "number" ? String(round(value)) : value);
  if (text !== undefined) el.textContent = text;
  if (parent) parent.appendChild(el);
  return el;
}

function dimH(parent, x0, x1, y, label, font, cls) {
  const t = font * 0.55;
  const g = add(parent, "g", { class: cls });
  add(g, "line", { x1: x0, y1: y, x2: x1, y2: y });
  add(g, "line", { x1: x0, y1: y - t, x2: x0, y2: y + t });
  add(g, "line", { x1: x1, y1: y - t, x2: x1, y2: y + t });
  add(g, "text", { x: (x0 + x1) / 2, y: y - t - font * 0.3, "text-anchor": "middle", "font-size": font }, label);
}

function dimV(parent, y0, y1, x, label, font, cls, right) {
  const t = font * 0.55;
  const g = add(parent, "g", { class: cls });
  add(g, "line", { x1: x, y1: y0, x2: x, y2: y1 });
  add(g, "line", { x1: x - t, y1: y0, x2: x + t, y2: y0 });
  add(g, "line", { x1: x - t, y1: y1, x2: x + t, y2: y1 });
  // rotate(-90) puts the glyphs on the -x side of the baseline.
  const tx = right ? x + t + font * 1.05 : x - t - font * 0.3;
  add(g, "text", { transform: `translate(${round(tx)} ${round((y0 + y1) / 2)}) rotate(-90)`, "text-anchor": "middle", "font-size": font }, label);
}

export function drawElevation(host, data, { basis, tip }) {
  const { width: W, height: H, parts, leaves, picture } = data.assembly;
  const font = Math.max(W, H) / divisor(host);
  const m = font * 4.4;
  const byId = new Map(parts.map((p) => [p.id, p]));
  const hinge = new Set(leaves.map((leaf) => leaf.hinge_stile));
  const svg = add(null, "svg", {
    class: "elev", viewBox: [-m, -m, W + 2 * m, H + 2 * m].map(round).join(" "), role: "img",
    "aria-label": `정면도: 외경 ${pair(data.size.outer_mm)} mm, 부품 ${parts.length}개`,
  });
  for (const family of ["FRAME", "SASH", "LATTICE"]) {
    for (const p of parts.filter((q) => q.family === family)) {
      const [x0, y0, x1, y1] = p.rect;
      add(svg, "rect", {
        class: `mk-${family.toLowerCase()}${hinge.has(p.id) ? " mk-hinge" : ""}`,
        x: x0, y: H - y1, width: x1 - x0, height: y1 - y0, "data-id": p.id,
      });
    }
  }
  if (picture) {
    const [x0, y0, x1, y1] = picture.sheet;
    add(svg, "rect", { class: "mk-pic", x: x0, y: H - y1, width: x1 - x0, height: y1 - y0 });
    add(svg, "text", { class: "mk-pic-t", x: (x0 + x1) / 2, y: H - y0 - font * 0.9, "text-anchor": "middle", "font-size": font * 0.85 },
      `그림 ${pair(picture.size_mm)} · 뒤판`);
  }
  for (const id of hinge) {
    const [x0, y0, x1, y1] = byId.get(id)?.rect ?? [];
    if (x0 === undefined) continue;
    add(svg, "text", {
      class: "mk-hinge-t", transform: `translate(${round((x0 + x1) / 2 + font * 0.35)} ${round(H - (y0 + y1) / 2)}) rotate(-90)`,
      "text-anchor": "middle", "font-size": font * 0.85,
    }, "경첩 쪽");
  }
  // The inner opening is bounded by the four fixed-frame members.
  const left = byId.get("F01-1").rect[2];
  const right = byId.get("F01-2").rect[0];
  const bottom = byId.get("F02-1").rect[3];
  const top = byId.get("F02-2").rect[1];
  const [outerTag, innerTag] = basis === "inner" ? ["", " (입력)"] : [" (입력)", ""];
  const [outerCls, innerCls] = basis === "inner" ? ["mk-dim", "mk-dim mk-dim-in"] : ["mk-dim mk-dim-in", "mk-dim"];
  dimH(svg, 0, W, -m * 0.42, `외경 ${fmt(data.size.outer_mm[0])}${outerTag}`, font, outerCls);
  dimV(svg, 0, H, W + m * 0.36, `외경 ${fmt(data.size.outer_mm[1])}${outerTag}`, font, outerCls, true);
  dimH(svg, left, right, H + m * 0.62, `내경 ${fmt(data.size.inner_mm[0])}${innerTag}`, font, innerCls);
  dimV(svg, H - top, H - bottom, -m * 0.42, `내경 ${fmt(data.size.inner_mm[1])}${innerTag}`, font, innerCls, false);
  host.replaceChildren(svg);
  tip?.attach(svg, (id) => {
    const p = byId.get(id);
    const [x0, y0, x1, y1] = p.rect;
    return `${p.id} · ${KIND[p.kind] ?? p.kind} · ${fmt(x1 - x0)} × ${fmt(y1 - y0)} mm · ${GROUP[p.group] ?? p.group}`;
  });
}

export function drawNesting(host, data, { tip }) {
  const n = data.nesting;
  const [L, B] = n.stock_mm;
  const M = n.margin_mm;
  const font = L / divisor(host);
  const pad = font * 0.8;
  const byId = new Map(n.parts.map((p) => [p.id, p]));
  const svg = add(null, "svg", {
    class: "nest", viewBox: [-pad, -pad, L + 2 * pad, B + 2 * pad].map(round).join(" "), role: "img",
    "aria-label": `원판 ${pair([L, B])} mm 위 부품 ${n.parts.length}개 배치`,
  });
  add(svg, "rect", { class: "nk-board", x: 0, y: 0, width: L, height: B });
  add(svg, "rect", { class: "nk-margin", x: M, y: M, width: L - 2 * M, height: B - 2 * M });
  for (const p of n.parts) {
    const [x0, y0, x1, y1] = p.rect;
    add(svg, "rect", { class: `nk-${p.family.toLowerCase()}`, x: x0, y: B - y1, width: x1 - x0, height: y1 - y0, "data-id": p.id });
  }
  const [x0, y0, x1, y1] = n.bounds;
  const e = font * 0.3;
  add(svg, "rect", { class: "nk-used", x: x0 - e, y: B - y1 - e, width: x1 - x0 + 2 * e, height: y1 - y0 + 2 * e });
  const above = B - y1 - e - font * 0.45;
  add(svg, "text", { class: "nk-t", x: x0, y: above > font ? above : Math.min(B - y0 + e + font * 1.1, B - font * 0.3), "font-size": font },
    `쓰는 범위 ${pair(n.used_mm)} mm`);
  host.replaceChildren(svg);
  tip?.attach(svg, (id) => {
    const p = byId.get(id);
    const [a, b, c, d] = p.rect;
    return `${p.id} · ${KIND[p.kind] ?? p.kind} · 길이 ${fmt(c - a)} × 폭 ${fmt(d - b)} mm`;
  });
}

export function tooltip(pane, box) {
  let hot = null;
  const hide = () => {
    hot?.classList.remove("mk-hot");
    hot = null;
    box.hidden = true;
  };
  return {
    hide,
    attach(svg, describe) {
      svg.addEventListener("pointermove", (event) => {
        const target = event.target instanceof Element ? event.target : null;
        const id = target?.getAttribute("data-id");
        if (!id) return hide();
        if (hot !== target) {
          hot?.classList.remove("mk-hot");
          hot = target;
          hot.classList.add("mk-hot");
          box.textContent = describe(id);
          box.hidden = false;
        }
        const area = pane.getBoundingClientRect();
        box.style.left = `${Math.max(6, Math.min(event.clientX - area.left + 14, area.width - box.offsetWidth - 6))}px`;
        box.style.top = `${event.clientY - area.top + 16}px`;
      });
      svg.addEventListener("pointerleave", hide);
    },
  };
}
