/* components/Graph.js
   Horizontal tree / dendrogram (OSINT-Framework style) replacing the force-directed
   sigma graph. Structure only was taken from the reference — the content is VERTEX's
   own investigation hierarchy:

       Target (seed)                      ← root, far left
         ├─ Exact match                   ← the anchor account(s) that literally match the seed
         │    └─ INSTAGRAM · ash29_03
         ├─ Identity A · 92%              ← each multi-member cluster = one linked identity
         │    ├─ GITHUB · ashwinh
         │    └─ TWITTER · ash_h
         └─ Unlinked leads (7)            ← singletons / rejects, colored by their own tier
              └─ …

   Nodes are hollow rings colored by tier (HIGH=emerald, MEDIUM=amber, LOW/REJECT=crimson,
   anchor/root/selected=cyan). Category labels sit LEFT of their node, account labels RIGHT —
   exactly the reference layout. Curved cubic-bezier links connect parent→child. The view
   fits to a viewBox and supports wheel-zoom + drag-pan; a search box dims non-matching nodes.
   Clicking an account leaf calls onSelect(entity_id) (same contract as before, keeps the side
   panel working); clicking a category node collapses/expands it. */
"use client";
import { useEffect, useMemo, useRef, useState } from "react";

// tier -> ring color (matches the legend under the graph in page.js)
const RING = {
  HIGH: "#00ff88", MEDIUM: "#ffb703", LOW: "#ff3366", REJECT: "#ff3366",
  ANCHOR: "#00f2fe", ROOT: "#00f2fe", CATEGORY: "#8892b0",
};
const TEXT = "#cbd5e0";
const TEXT_DIM = "#64748b";
const SELECTED = "#00f2fe";
const HL_LINK = "#00ff88";

const COL = 210;   // horizontal spacing per depth
const ROW = 30;    // vertical spacing per leaf
const PAD_L = 180; // left margin (room for the root label)
const PAD_T = 26;  // top margin
const NODE_R = 5;

const letter = (i) => (i < 26 ? String.fromCharCode(65 + i) : `#${i + 1}`);
const trunc = (s, n) => (s && s.length > n ? s.slice(0, n - 1) + "…" : s || "");

// entities: [{entity_id, platform, value, metadata}], clusters: [{cluster_id, tier, entity_ids, confidence_score, relevance}]
export default function NetworkGraph({ entities, clusters, onSelect, onHover, selectedId, seed }) {
  const svgRef = useRef(null);
  const [collapsed, setCollapsed] = useState(() => new Set());
  const [query, setQuery] = useState("");
  const [view, setView] = useState({ k: 1, x: 0, y: 0 }); // user zoom/pan on top of the fitted viewBox
  const drag = useRef(null);

  const onSelectRef = useRef(onSelect);
  const onHoverRef = useRef(onHover);
  onSelectRef.current = onSelect;
  onHoverRef.current = onHover;

  // -------- build the hierarchy from entities + clusters --------
  const tree = useMemo(() => {
    const ents = entities || [];
    const cls = clusters || [];
    const entById = {};
    ents.forEach((e) => (entById[e.entity_id] = e));
    const shown = new Set(ents.map((e) => e.entity_id));

    // entity -> tier (first cluster that contains it)
    const tierOf = {};
    cls.forEach((c) => (c.entity_ids || []).forEach((id) => { if (!(id in tierOf)) tierOf[id] = c.tier; }));

    const isExactCluster = (c) =>
      (c.relevance?.score || 0) >= 100 ||
      (c.entity_ids || []).some((id) => entById[id]?.metadata?.exact_seed_match);
    const tierRank = { HIGH: 0, MEDIUM: 1, LOW: 2, REJECT: 3 };

    const account = (e, anchor = false) => ({
      id: e.entity_id,
      kind: "account",
      entity: e,
      anchor,
      tier: anchor ? "ANCHOR" : (tierOf[e.entity_id] || "REJECT"),
      label: (e.platform || "?").toUpperCase(),
      sub: e.value || e.metadata?.username || "",
    });

    const accounted = new Set();
    const cats = [];

    // 1) multi-member identity clusters, exact-match first, then tier, then confidence
    const multi = cls
      .filter((c) => (c.entity_ids || []).filter((id) => shown.has(id)).length >= 2)
      .sort((a, b) =>
        (isExactCluster(b) - isExactCluster(a)) ||
        ((tierRank[a.tier] ?? 9) - (tierRank[b.tier] ?? 9)) ||
        ((b.confidence_score || 0) - (a.confidence_score || 0)));
    let idx = 0;
    multi.forEach((c) => {
      const members = (c.entity_ids || []).filter((id) => shown.has(id));
      members.forEach((id) => accounted.add(id));
      const letr = letter(idx++);
      // Leak-account pivot: label the persona with the recovered real name when a member
      // leaked one, else fall back to "Identity A/B/…".
      const idName = c.identity && c.identity.name;
      cats.push({
        id: `cl:${c.cluster_id}`,
        kind: "category",
        tier: c.tier,
        label: idName || `Identity ${letr}`,
        meta: `${Math.round(c.confidence_score || 0)}%`,
        children: members.map((id) => account(entById[id])),
      });
    });

    // 2) exact-match anchor singletons (not already inside a multi-member identity)
    const exactSingles = ents.filter(
      (e) => !accounted.has(e.entity_id) && e.metadata?.exact_seed_match);
    exactSingles.forEach((e) => accounted.add(e.entity_id));
    if (exactSingles.length) {
      cats.unshift({
        id: "cat:exact",
        kind: "category",
        tier: "ANCHOR",
        label: "Exact match",
        meta: "seed",
        children: exactSingles.map((e) => account(e, true)),
      });
    }

    // 3) everything else = unlinked leads (each colored by its own tier)
    const rest = ents.filter((e) => !accounted.has(e.entity_id));
    if (rest.length) {
      cats.push({
        id: "cat:unlinked",
        kind: "category",
        tier: "REJECT",
        label: "Unlinked leads",
        meta: `${rest.length}`,
        children: rest.map((e) => account(e)),
      });
    }

    const seedLabel = (seed || "").trim() || "Target";
    return { id: "__root__", kind: "root", label: seedLabel, children: cats };
  }, [entities, clusters, seed]);

  // -------- tidy horizontal layout (leaves stack; parents center on children) --------
  const layout = useMemo(() => {
    let leaf = 0;
    let maxDepth = 0;
    const walk = (node, depth) => {
      node.depth = depth;
      if (depth > maxDepth) maxDepth = depth;
      node.x = PAD_L + depth * COL;
      const kids = node.children && node.children.length && !collapsed.has(node.id) ? node.children : null;
      if (kids) {
        kids.forEach((k) => walk(k, depth + 1));
        node.y = (kids[0].y + kids[kids.length - 1].y) / 2;
      } else {
        node.y = PAD_T + leaf * ROW;
        leaf += 1;
      }
    };
    walk(tree, 0);

    const nodes = [];
    const links = [];
    const collect = (node) => {
      nodes.push(node);
      const kids = node.children && node.children.length && !collapsed.has(node.id) ? node.children : null;
      if (kids) kids.forEach((k) => { links.push([node, k]); collect(k); });
    };
    collect(tree);

    const width = PAD_L + maxDepth * COL + 300; // right room for account labels
    const height = Math.max(PAD_T * 2 + Math.max(leaf, 1) * ROW, 120);
    return { nodes, links, width, height };
  }, [tree, collapsed]);

  // -------- search: dim everything not on a matching node's ancestor path --------
  const dimSet = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return null;
    const parent = new Map();
    const mark = (node, p) => {
      if (p) parent.set(node, p);
      (node.children || []).forEach((k) => mark(k, node));
    };
    mark(tree, null);
    const keep = new Set();
    const matches = (n) =>
      (n.label || "").toLowerCase().includes(q) || (n.sub || "").toLowerCase().includes(q);
    const visit = (node) => {
      if (matches(node)) {
        let cur = node;
        while (cur) { keep.add(cur); cur = parent.get(cur); }
      }
      (node.children || []).forEach(visit);
    };
    visit(tree);
    return keep; // nodes NOT in keep are dimmed
  }, [query, tree]);

  // ancestor path of the selected account (for highlight)
  const selPath = useMemo(() => {
    if (!selectedId) return new Set();
    const parent = new Map();
    const mark = (node, p) => { if (p) parent.set(node, p); (node.children || []).forEach((k) => mark(k, node)); };
    mark(tree, null);
    const target = layout.nodes.find((n) => n.id === selectedId);
    const set = new Set();
    let cur = target;
    while (cur) { set.add(cur); cur = parent.get(cur); }
    return set;
  }, [selectedId, tree, layout]);

  // map a screen (client) point into viewBox user-units, and expose the current
  // viewBox→screen scale so pan/zoom deltas stay 1:1 with the cursor.
  const toUser = (clientX, clientY) => {
    const el = svgRef.current;
    const ctm = el && el.getScreenCTM ? el.getScreenCTM() : null;
    if (!ctm) return { x: clientX, y: clientY, scale: 1 };
    const inv = ctm.inverse();
    const p = el.createSVGPoint();
    p.x = clientX; p.y = clientY;
    const u = p.matrixTransform(inv);
    return { x: u.x, y: u.y, scale: ctm.a || 1 };
  };

  // -------- wheel zoom (non-passive so we can preventDefault) --------
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const onWheel = (ev) => {
      ev.preventDefault();
      const u = toUser(ev.clientX, ev.clientY); // cursor in viewBox units
      setView((v) => {
        const factor = ev.deltaY < 0 ? 1.12 : 1 / 1.12;
        const k = Math.min(4, Math.max(0.35, v.k * factor));
        // keep the local point under the cursor fixed while scaling
        const nx = u.x - (u.x - v.x) * (k / v.k);
        const ny = u.y - (u.y - v.y) * (k / v.k);
        return { k, x: nx, y: ny };
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onPointerDown = (e) => {
    if (e.target.closest?.("[data-node]")) return; // let node clicks through
    drag.current = { sx: e.clientX, sy: e.clientY, ox: view.x, oy: view.y, scale: toUser(e.clientX, e.clientY).scale };
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };
  const onPointerMove = (e) => {
    if (!drag.current) return;
    const s = drag.current.scale || 1;
    setView((v) => ({
      ...v,
      x: drag.current.ox + (e.clientX - drag.current.sx) / s,
      y: drag.current.oy + (e.clientY - drag.current.sy) / s,
    }));
  };
  const onPointerUp = () => { drag.current = null; };

  const toggle = (node) => {
    if (node.kind === "account") { onSelectRef.current && onSelectRef.current(node.id); return; }
    if (node.kind === "root") return;
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(node.id) ? next.delete(node.id) : next.add(node.id);
      return next;
    });
  };

  const linkPath = (s, t) => {
    const x1 = s.x + NODE_R, y1 = s.y, x2 = t.x - NODE_R, y2 = t.y;
    const mx = (x1 + x2) / 2;
    return `M${x1},${y1}C${mx},${y1} ${mx},${y2} ${x2},${y2}`;
  };

  const ringColor = (n) =>
    n.kind === "root" ? RING.ROOT :
    n.id === selectedId ? SELECTED :
    RING[n.tier] || RING.CATEGORY;

  const resetView = () => setView({ k: 1, x: 0, y: 0 });

  return (
    <div className="relative w-full h-full">
      {/* search box (OSINT-framework style) */}
      <div className="absolute top-2 right-2 z-10 flex items-center gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search accounts…"
          className="w-44 px-3 py-1.5 text-xs rounded-md bg-slate-900/80 border border-slate-700 text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-cyan-500"
        />
        <button
          onClick={resetView}
          title="Reset view"
          className="px-2 py-1.5 text-[11px] font-mono rounded-md bg-slate-900/80 border border-slate-700 text-slate-400 hover:text-cyan-400"
        >
          ⤢ fit
        </button>
      </div>

      <svg
        ref={svgRef}
        id="network-graph"
        className="w-full h-full cursor-grab active:cursor-grabbing select-none"
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        preserveAspectRatio="xMidYMid meet"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={onPointerUp}
      >
        <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          {/* links */}
          {layout.links.map(([s, t]) => {
            const on = selPath.has(s) && selPath.has(t);
            const dim = dimSet && !(dimSet.has(s) && dimSet.has(t));
            return (
              <path
                key={`${s.id}->${t.id}`}
                d={linkPath(s, t)}
                fill="none"
                stroke={on ? HL_LINK : "rgba(0,242,254,0.35)"}
                strokeWidth={on ? 1.8 : 1}
                opacity={dim ? 0.12 : 1}
              />
            );
          })}

          {/* nodes */}
          {layout.nodes.map((n) => {
            const hasKids = n.children && n.children.length;
            const isCollapsed = hasKids && collapsed.has(n.id);
            const dim = dimSet && !dimSet.has(n);
            const selected = n.id === selectedId;
            const rc = ringColor(n);
            const leafLabel = n.kind === "account";
            return (
              <g
                key={n.id}
                data-node="1"
                transform={`translate(${n.x},${n.y})`}
                opacity={dim ? 0.18 : 1}
                style={{ cursor: n.kind === "root" ? "default" : "pointer" }}
                onClick={(e) => { e.stopPropagation(); toggle(n); }}
                onMouseEnter={() => leafLabel && onHoverRef.current && onHoverRef.current(n.id)}
                onMouseLeave={() => leafLabel && onHoverRef.current && onHoverRef.current(null)}
              >
                <title>{leafLabel ? `${n.label} — ${n.sub}` : `${n.label}${n.meta ? " · " + n.meta : ""}`}</title>
                <circle
                  r={selected ? NODE_R + 2 : NODE_R}
                  fill={selected ? SELECTED : (isCollapsed ? rc : "#0b1220")}
                  stroke={rc}
                  strokeWidth={selected ? 2.2 : 1.6}
                />
                {leafLabel ? (
                  // account leaf: label to the RIGHT
                  <text x={NODE_R + 7} y={4} textAnchor="start" fontFamily="var(--font-mono), monospace" fontSize={12}>
                    <tspan fill={selected ? SELECTED : TEXT} fontWeight={n.anchor ? 700 : 500}>
                      {n.anchor ? "★ " : ""}{n.label}
                    </tspan>
                    {n.sub ? <tspan fill={TEXT_DIM} fontSize={11}>{"  " + trunc(n.sub, 22)}</tspan> : null}
                  </text>
                ) : (
                  // root / category: label to the LEFT
                  <text x={-(NODE_R + 7)} y={4} textAnchor="end" fontFamily="var(--font-mono), monospace" fontSize={n.kind === "root" ? 13 : 12}>
                    <tspan fill={n.kind === "root" ? SELECTED : TEXT} fontWeight={n.kind === "root" ? 700 : 600}>
                      {trunc(n.label, 24)}
                    </tspan>
                    {n.meta ? <tspan fill={TEXT_DIM} fontSize={10}>{"  " + n.meta}</tspan> : null}
                    {isCollapsed ? <tspan fill={rc} fontSize={11}>{"  ▸"}</tspan> : null}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      <div className="absolute bottom-1.5 left-2 text-[10px] font-mono text-slate-600 pointer-events-none">
        scroll to zoom · drag to pan · click a branch to collapse
      </div>
    </div>
  );
}
