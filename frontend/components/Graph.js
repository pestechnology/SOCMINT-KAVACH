/* components/Graph.js
   REDESIGN §4.4.4.2 / §1.7 — semantic node colors (HIGH=emerald, MEDIUM=amber,
   LOW/REJECT=crimson), translucent-cyan edges, selected node = cyan with emerald
   edges. Selection recolors via sigma node/edge reducers + refresh() so it never
   re-runs the force layout (no jitter). Rebuild still keyed on node/cluster signature. */
"use client";
import { useEffect, useMemo, useRef } from "react";
import Graph from "graphology";
import Sigma from "sigma";
import forceAtlas2 from "graphology-layout-forceatlas2";

// §1.7 semantic mapping.
const NODE_COLOR = { HIGH: "#00ff88", MEDIUM: "#ffb703", LOW: "#ff3366", REJECT: "#ff3366" };
const EDGE_DEFAULT = "rgba(0, 242, 254, 0.4)"; // translucent cyan
const EDGE_SELECTED = "#00ff88";               // emerald highlight on selected node's edges
const NODE_SELECTED = "#00f2fe";               // cyan

// entities: [{entity_id, platform, value}], clusters: [{tier, entity_ids, confidence_score}]
export default function NetworkGraph({ entities, clusters, onSelect, onHover, selectedId }) {
  const containerRef = useRef(null);
  const sigmaRef = useRef(null);
  const onSelectRef = useRef(onSelect);
  const onHoverRef = useRef(onHover);
  const selectedRef = useRef(selectedId);
  onSelectRef.current = onSelect;
  onHoverRef.current = onHover;
  selectedRef.current = selectedId;

  // rebuild only when nodes/clusters actually change, not on every poll
  const signature = useMemo(
    () =>
      (entities || []).map((e) => e.entity_id).join("|") +
      "::" +
      (clusters || [])
        .map((c) => `${c.tier}:${Math.round(c.confidence_score || 0)}:${(c.entity_ids || []).join(",")}`)
        .join("|"),
    [entities, clusters]
  );

  useEffect(() => {
    if (!containerRef.current) return;
    const g = new Graph();

    const info = {}; // entity_id -> {tier, score}
    clusters.forEach((c) =>
      (c.entity_ids || []).forEach((id) => { info[id] = { tier: c.tier, score: c.confidence_score }; })
    );

    entities.forEach((e, i) => {
      const meta = info[e.entity_id] || { tier: "REJECT", score: 0 };
      const tier = meta.tier;
      const size =
        tier === "HIGH" ? Math.max(8, (meta.score || 80) / 8) :
        tier === "MEDIUM" ? 9 :
        tier === "LOW" ? 7 : 5;
      if (!g.hasNode(e.entity_id)) {
        g.addNode(e.entity_id, {
          label: (e.platform || "").toUpperCase(),
          size,
          color: NODE_COLOR[tier] || "#ff3366",
          x: Math.cos((i / Math.max(entities.length, 1)) * 2 * Math.PI),
          y: Math.sin((i / Math.max(entities.length, 1)) * 2 * Math.PI),
        });
      }
    });

    clusters.forEach((c) => {
      const ids = (c.entity_ids || []).filter((id) => g.hasNode(id));
      if (ids.length < 2) return; // no edges between unlinked/reject singletons
      const w = c.tier === "HIGH" ? 2.5 : c.tier === "MEDIUM" ? 1.5 : 1;
      for (let a = 0; a < ids.length; a++) {
        for (let b = a + 1; b < ids.length; b++) {
          const key = `${ids[a]}--${ids[b]}`;
          if (!g.hasEdge(key)) {
            g.addEdgeWithKey(key, ids[a], ids[b], { size: w, color: EDGE_DEFAULT });
          }
        }
      }
    });

    try {
      forceAtlas2.assign(g, { iterations: 120, settings: { gravity: 1, scalingRatio: 12 } });
    } catch (_) {}

    const renderer = new Sigma(g, containerRef.current, {
      renderEdgeLabels: false,
      labelColor: { color: "#CBD5E0" },
      labelSize: 11,
      labelFont: "var(--font-mono), 'JetBrains Mono', monospace",
      defaultEdgeColor: EDGE_DEFAULT,
      // §1.7 — selected node cyan; its edges emerald. Reducers avoid a rebuild/relayout.
      nodeReducer: (node, data) => {
        if (selectedRef.current && node === selectedRef.current) {
          return { ...data, color: NODE_SELECTED, size: (data.size || 6) + 2, zIndex: 2 };
        }
        return data;
      },
      edgeReducer: (edge, data) => {
        if (selectedRef.current && g.hasExtremity(edge, selectedRef.current)) {
          return { ...data, color: EDGE_SELECTED, size: (data.size || 1) + 0.5, zIndex: 1 };
        }
        return data;
      },
    });
    renderer.on("clickNode", ({ node }) => onSelectRef.current && onSelectRef.current(node));
    renderer.on("enterNode", ({ node }) => onHoverRef.current && onHoverRef.current(node));
    renderer.on("leaveNode", () => onHoverRef.current && onHoverRef.current(null));
    sigmaRef.current = renderer;
    return () => { renderer.kill(); sigmaRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);

  // Recolor on selection change without rebuilding/relaying out the graph.
  useEffect(() => {
    if (sigmaRef.current) sigmaRef.current.refresh();
  }, [selectedId]);

  return <div ref={containerRef} id="network-graph" className="w-full h-full" />;
}
