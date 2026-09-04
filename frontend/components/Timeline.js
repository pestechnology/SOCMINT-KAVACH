/* components/Timeline.js
   CHANGED: build items from entity.metadata.posting_hours (hours-of-day plotted on a
   reference day), colored by cluster tier; renders nothing if there is no temporal data.
   DECISION: the parent decides whether to mount this (showing the "insufficient temporal
   data" notice itself), so this component never renders an empty vis-timeline. */
"use client";
import { useEffect, useRef } from "react";
import { Timeline as VisTimeline } from "vis-timeline/standalone";
import { DataSet } from "vis-data";
import "vis-timeline/styles/vis-timeline-graph2d.css";

// §1.7 semantic mapping: HIGH=emerald, MEDIUM=amber, LOW/REJECT=crimson.
const TIER_BG = { HIGH: "#6fae86", MEDIUM: "#cba96a", LOW: "#cf8080", REJECT: "#cf8080" };

export default function Timeline({ entities, clusters }) {
  const ref = useRef(null);
  const tlRef = useRef(null);

  useEffect(() => {
    if (!ref.current) return;
    const tierByEntity = {};
    (clusters || []).forEach((c) => (c.entity_ids || []).forEach((id) => { tierByEntity[id] = c.tier; }));

    const items = [];
    let idc = 0;
    (entities || []).forEach((e) => {
      const hrs = e.metadata && e.metadata.posting_hours;
      if (!Array.isArray(hrs) || !hrs.length) return;
      const tier = tierByEntity[e.entity_id] || "REJECT";
      const color = TIER_BG[tier] || "#4A5568";
      hrs.forEach((h) => {
        const hour = Number(h);
        if (isNaN(hour)) return;
        items.push({
          id: idc++,
          content: (e.platform || "").toUpperCase(),
          start: new Date(2026, 0, 1, hour, 0, 0),
          title: `${e.platform}: ${e.value} @ ${String(hour).padStart(2, "0")}:00`,
          style: `background-color:${color}22;border-color:${color};color:#EDF2F7;font-family:var(--font-mono),monospace;font-size:9px;`,
        });
      });
    });

    if (!items.length) { ref.current.innerHTML = ""; return; }

    const ds = new DataSet(items);
    const tl = new VisTimeline(ref.current, ds, {
      height: "150px",
      stack: true,
      zoomable: true,
      showCurrentTime: false,
      start: new Date(2026, 0, 1, 0, 0, 0),
      end: new Date(2026, 0, 1, 23, 59, 59),
    });
    tlRef.current = tl;
    return () => { tl.destroy(); tlRef.current = null; };
  }, [entities, clusters]);

  return <div ref={ref} className="w-full" />;
}
