/* components/Graph.js
   CHANGED: sigma config only — Case Room tier colors, size-by-confidence for HIGH nodes,
   tier-weighted edges, mono labels, and enterNode/leaveNode hover events.
   DECISION: hover/select callbacks held in refs so the graph rebuilds ONLY on the
   node/cluster signature (not every poll) — no re-layout jitter. */
"use client";
import { useEffect, useMemo, useRef } from "react";
import Graph from "graphology";
import Sigma from "sigma";
import forceAtlas2 from "graphology-layout-forceatlas2";

// Brightened for contrast against the near-black (#0E1117) canvas: the old LOW
// (#8A4A2E) and UNLINKED (#4A5568) were nearly invisible, and most nodes are those.
const NODE_COLOR = { HIGH: "#D4900A", MEDIUM: "#5B9BD5", LOW: "#E08A4A", REJECT: "#8A97AD" };
const EDGE_COLOR = { HIGH: "#D4900A", MEDIUM: "#5B9BD5", LOW: "#E08A4A", REJECT: "#3A4358" };

// entities: [{entity_id, platform, value}], clusters: [{tier, entity_ids, confidence_score}]
export default function NetworkGraph({ entities, clusters, onSelect, onHover }) {
  const containerRef = useRef(null);
  const sigmaRef = useRef(null);
  const onSelectRef = useRef(onSelect);
  const onHoverRef = useRef(onHover);
  onSelectRef.current = onSelect;
  onHoverRef.current = onHover;

  // rebuild only when nodes/clusters actually change, not on every poll
  const signature = useMemo(
    () =>
      (entities || []).map((e) => e.entity_id).join("|") +
      "::" +
      // include confidence_score: node size / edge weight depend on it, so it
      // must be part of the signature or the graph keeps stale sizes as scores
      // firm up during polling.
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
          color: NODE_COLOR[tier] || "#8A97AD",
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
            g.addEdgeWithKey(key, ids[a], ids[b], { size: w, color: EDGE_COLOR[c.tier] || "#2A3148" });
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
      defaultEdgeColor: "#2A3148",
    });
    renderer.on("clickNode", ({ node }) => onSelectRef.current && onSelectRef.current(node));
    renderer.on("enterNode", ({ node }) => onHoverRef.current && onHoverRef.current(node));
    renderer.on("leaveNode", () => onHoverRef.current && onHoverRef.current(null));
    sigmaRef.current = renderer;
    return () => { renderer.kill(); sigmaRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);

  return <div ref={containerRef} className="w-full h-full" />;
}
