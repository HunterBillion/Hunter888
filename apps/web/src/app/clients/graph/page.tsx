"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  Network,
  Loader2,
  ZoomIn,
  ZoomOut,
  Maximize2,
  X,
} from "lucide-react";
import * as d3 from "d3";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { isManager } from "@/lib/guards";
import AuthLayout from "@/components/layout/AuthLayout";

/* ─── Types ─── */

interface GraphNode extends d3.SimulationNodeDatum {
  id: string;
  type: "client" | "manager";
  label: string;
  // client fields
  status?: string;
  debt_amount?: number;
  source?: string;
  created_at?: string | null;
  // manager fields
  role?: string;
  client_count?: number;
}

interface GraphLink extends d3.SimulationLinkDatum<GraphNode> {
  source: string | GraphNode;
  target: string | GraphNode;
  type: string;
}

interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
  status_counts: Record<string, number>;
  transitions: { from: string; to: string }[];
  total_clients: number;
  total_managers: number;
}

/* ─── Status color map ─── */

const STATUS_COLORS: Record<string, string> = {
  new: "#60A5FA",
  contacted: "#818CF8",
  interested: "#A78BFA",
  consultation: "#C084FC",
  thinking: "#FBBF24",
  consent_given: "#34D399",
  contract_signed: "#10B981",
  in_process: "#06B6D4",
  paused: "#94A3B8",
  completed: "#00FF66",
  lost: "#F87171",
  consent_revoked: "#FB923C",
};

const STATUS_LABELS: Record<string, string> = {
  new: "Новый",
  contacted: "Контакт",
  interested: "Интерес",
  consultation: "Консультация",
  thinking: "Думает",
  consent_given: "Согласие",
  contract_signed: "Договор",
  in_process: "В процессе",
  paused: "Пауза",
  completed: "Завершён",
  lost: "Потерян",
  consent_revoked: "Отзыв",
};

const MANAGER_COLOR = "#FFD700";

/* ─── Main Component ─── */

export default function ClientGraphPage() {
  const router = useRouter();
  const { user } = useAuth();
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>("");

  const simulationRef = useRef<d3.Simulation<GraphNode, GraphLink> | null>(null);
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);

  /* ── Fetch data ── */
  useEffect(() => {
    if (!user) return;
    if (!isManager(user)) {
      setError("Доступ ограничен");
      setLoading(false);
      return;
    }

    api
      .get("/clients/graph-data")
      .then((resp: GraphData) => setData(resp))
      .catch((err: Error) => setError(err.message || "Ошибка загрузки"))
      .finally(() => setLoading(false));
  }, [user]);

  /* ── Build D3 graph ── */
  const buildGraph = useCallback(() => {
    if (!data || !svgRef.current || !containerRef.current) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const rect = containerRef.current.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;

    svg.attr("width", width).attr("height", height);

    // Filter nodes by status
    let filteredNodes = [...data.nodes];
    let filteredLinks = [...data.links];

    if (filterStatus) {
      const clientIds = new Set(
        filteredNodes
          .filter((n) => n.type === "client" && n.status === filterStatus)
          .map((n) => n.id)
      );
      // Include managers connected to filtered clients
      const managerIds = new Set(
        filteredLinks
          .filter((l) => clientIds.has(typeof l.source === "string" ? l.source : (l.source as GraphNode).id))
          .map((l) => (typeof l.target === "string" ? l.target : (l.target as GraphNode).id))
      );
      filteredNodes = filteredNodes.filter(
        (n) => clientIds.has(n.id) || managerIds.has(n.id)
      );
      const allIds = new Set(filteredNodes.map((n) => n.id));
      filteredLinks = filteredLinks.filter((l) => {
        const sid = typeof l.source === "string" ? l.source : (l.source as GraphNode).id;
        const tid = typeof l.target === "string" ? l.target : (l.target as GraphNode).id;
        return allIds.has(sid) && allIds.has(tid);
      });
    }

    // Create container group for zoom
    const g = svg.append("g");

    // Zoom behavior
    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 5])
      .on("zoom", (event) => g.attr("transform", event.transform));

    svg.call(zoom);
    zoomRef.current = zoom;

    // Defs for arrow markers
    svg
      .append("defs")
      .append("marker")
      .attr("id", "arrowhead")
      .attr("viewBox", "0 0 10 10")
      .attr("refX", 20)
      .attr("refY", 5)
      .attr("markerWidth", 6)
      .attr("markerHeight", 6)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,0L10,5L0,10Z")
      .attr("fill", "var(--text-muted)");

    // Force simulation
    const simulation = d3
      .forceSimulation<GraphNode>(filteredNodes)
      .force(
        "link",
        d3
          .forceLink<GraphNode, GraphLink>(filteredLinks)
          .id((d) => d.id)
          .distance((d) => {
            return d.type === "managed_by" ? 120 : 80;
          })
          .strength(0.4)
      )
      .force("charge", d3.forceManyBody().strength(-200).distanceMax(400))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force(
        "collision",
        d3.forceCollide<GraphNode>().radius((d) => (d.type === "manager" ? 30 : 14))
      )
      .force("x", d3.forceX(width / 2).strength(0.03))
      .force("y", d3.forceY(height / 2).strength(0.03));

    simulationRef.current = simulation;

    // Links
    const link = g
      .append("g")
      .selectAll<SVGLineElement, GraphLink>("line")
      .data(filteredLinks)
      .join("line")
      .attr("stroke", "var(--border-color)")
      .attr("stroke-opacity", 0.4)
      .attr("stroke-width", 1)
      .attr("marker-end", "url(#arrowhead)");

    // Node groups
    const node = g
      .append("g")
      .selectAll<SVGGElement, GraphNode>("g")
      .data(filteredNodes)
      .join("g")
      .style("cursor", "pointer")
      .call(
        d3
          .drag<SVGGElement, GraphNode>()
          .on("start", (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on("drag", (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event, d) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          })
      );

    // Manager nodes: larger golden circles
    node
      .filter((d) => d.type === "manager")
      .append("circle")
      .attr("r", 22)
      .attr("fill", MANAGER_COLOR)
      .attr("fill-opacity", 0.15)
      .attr("stroke", MANAGER_COLOR)
      .attr("stroke-width", 2.5);

    node
      .filter((d) => d.type === "manager")
      .append("text")
      .text("M")
      .attr("text-anchor", "middle")
      .attr("dy", "0.35em")
      .attr("fill", MANAGER_COLOR)
      .attr("font-size", "14px")
      .attr("font-weight", "bold");

    // Client nodes: colored by status
    node
      .filter((d) => d.type === "client")
      .append("circle")
      .attr("r", (d) => {
        const debt = d.debt_amount || 0;
        return Math.max(6, Math.min(16, 6 + debt / 200000));
      })
      .attr("fill", (d) => STATUS_COLORS[d.status || "new"] || "#94A3B8")
      .attr("fill-opacity", 0.7)
      .attr("stroke", (d) => STATUS_COLORS[d.status || "new"] || "#94A3B8")
      .attr("stroke-width", 1.5);

    // Click handler
    node.on("click", (event, d) => {
      event.stopPropagation();
      setSelectedNode(d);
    });

    // Hover effects
    node
      .on("mouseenter", function (event, d) {
        d3.select(this).select("circle").attr("stroke-width", 3);

        // Highlight connected links
        link
          .attr("stroke-opacity", (l) => {
            const sid = typeof l.source === "object" ? (l.source as GraphNode).id : l.source;
            const tid = typeof l.target === "object" ? (l.target as GraphNode).id : l.target;
            return sid === d.id || tid === d.id ? 0.9 : 0.1;
          })
          .attr("stroke-width", (l) => {
            const sid = typeof l.source === "object" ? (l.source as GraphNode).id : l.source;
            const tid = typeof l.target === "object" ? (l.target as GraphNode).id : l.target;
            return sid === d.id || tid === d.id ? 2 : 1;
          })
          .attr("stroke", (l) => {
            const sid = typeof l.source === "object" ? (l.source as GraphNode).id : l.source;
            const tid = typeof l.target === "object" ? (l.target as GraphNode).id : l.target;
            return sid === d.id || tid === d.id ? "var(--accent)" : "var(--border-color)";
          });
      })
      .on("mouseleave", function () {
        d3.select(this).select("circle").attr("stroke-width", (d: unknown) => (d as GraphNode).type === "manager" ? 2.5 : 1.5);
        link
          .attr("stroke-opacity", 0.4)
          .attr("stroke-width", 1)
          .attr("stroke", "var(--border-color)");
      });

    // Labels for managers
    node
      .filter((d) => d.type === "manager")
      .append("text")
      .text((d) => d.label)
      .attr("dy", 36)
      .attr("text-anchor", "middle")
      .attr("fill", "var(--text-muted)")
      .attr("font-size", "10px")
      .attr("pointer-events", "none");

    // Tick
    simulation.on("tick", () => {
      link
        .attr("x1", (d) => ((d.source as GraphNode).x ?? 0))
        .attr("y1", (d) => ((d.source as GraphNode).y ?? 0))
        .attr("x2", (d) => ((d.target as GraphNode).x ?? 0))
        .attr("y2", (d) => ((d.target as GraphNode).y ?? 0));

      node.attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
    });

    // Click on background to deselect
    svg.on("click", () => setSelectedNode(null));

    // Initial zoom to fit
    setTimeout(() => {
      svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity.translate(0, 0).scale(0.85));
    }, 300);
  }, [data, filterStatus]);

  useEffect(() => {
    buildGraph();
    const handleResize = () => buildGraph();
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      simulationRef.current?.stop();
    };
  }, [buildGraph]);

  /* ── Zoom controls ── */
  const handleZoom = (direction: "in" | "out" | "reset") => {
    if (!svgRef.current || !zoomRef.current) return;
    const svg = d3.select(svgRef.current);
    if (direction === "reset") {
      svg.transition().duration(300).call(zoomRef.current.transform, d3.zoomIdentity);
    } else {
      svg.transition().duration(300).call(zoomRef.current.scaleBy, direction === "in" ? 1.5 : 0.67);
    }
  };

  return (
    <AuthLayout>
      <div className="panel-grid-bg" style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 72px)" }}>
        {/* ── Header bar ── */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center justify-between flex-wrap gap-3"
          style={{ padding: "16px 20px", borderBottom: "1px solid var(--border-color)" }}
        >
          <div className="flex items-center gap-3">
            <div
              className="flex h-9 w-9 items-center justify-center rounded-lg"
              style={{ background: "var(--accent)", color: "#000" }}
            >
              <Network size={18} />
            </div>
            <div>
              <h1
                style={{
                  fontFamily: "var(--font-display)",
                  fontSize: 20,
                  fontWeight: 700,
                  color: "var(--text-primary)",
                  margin: 0,
                }}
              >
                Граф клиентов
              </h1>
              {data && (
                <p style={{ color: "var(--text-muted)", fontSize: 12, margin: 0 }}>
                  {data.total_clients} клиентов · {data.total_managers} менеджеров
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Status filter */}
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              style={{
                padding: "6px 10px",
                borderRadius: 8,
                background: "var(--glass-bg)",
                color: "var(--text-primary)",
                border: "1px solid var(--glass-border)",
                fontSize: 12,
              }}
            >
              <option value="">Все статусы</option>
              {Object.entries(STATUS_LABELS).map(([key, label]) => (
                <option key={key} value={key}>
                  {label} {data?.status_counts[key] ? `(${data.status_counts[key]})` : ""}
                </option>
              ))}
            </select>

            {/* Zoom controls */}
            <div className="flex gap-1">
              <button
                onClick={() => handleZoom("in")}
                className="flex h-8 w-8 items-center justify-center rounded-lg"
                style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)", cursor: "pointer", color: "var(--text-primary)" }}
                title="Приблизить"
              >
                <ZoomIn size={14} />
              </button>
              <button
                onClick={() => handleZoom("out")}
                className="flex h-8 w-8 items-center justify-center rounded-lg"
                style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)", cursor: "pointer", color: "var(--text-primary)" }}
                title="Отдалить"
              >
                <ZoomOut size={14} />
              </button>
              <button
                onClick={() => handleZoom("reset")}
                className="flex h-8 w-8 items-center justify-center rounded-lg"
                style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)", cursor: "pointer", color: "var(--text-primary)" }}
                title="Сбросить"
              >
                <Maximize2 size={14} />
              </button>
            </div>
          </div>
        </motion.div>

        {/* ── Main area ── */}
        <div style={{ flex: 1, display: "flex", position: "relative", overflow: "hidden" }}>
          {/* Error */}
          {error && (
            <div className="flex items-center justify-center" style={{ position: "absolute", inset: 0, zIndex: 10 }}>
              <div className="glass-panel rounded-xl" style={{ padding: 32, textAlign: "center", color: "#F87171" }}>
                {error}
              </div>
            </div>
          )}

          {/* Loading */}
          {loading && (
            <div className="flex items-center justify-center" style={{ position: "absolute", inset: 0, zIndex: 10 }}>
              <Loader2 size={32} className="animate-spin" style={{ color: "var(--accent)" }} />
            </div>
          )}

          {/* SVG container */}
          <div ref={containerRef} style={{ flex: 1, position: "relative" }}>
            <svg
              ref={svgRef}
              style={{
                width: "100%",
                height: "100%",
                background: "var(--bg-primary)",
              }}
            />
          </div>

          {/* ── Legend ── */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.3 }}
            className="glass-panel rounded-xl"
            style={{
              position: "absolute",
              bottom: 16,
              left: 16,
              padding: "12px 16px",
              fontSize: 11,
              maxWidth: 200,
            }}
          >
            <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: 8 }}>Легенда</div>

            <div className="flex items-center gap-2" style={{ marginBottom: 6 }}>
              <div
                style={{
                  width: 16,
                  height: 16,
                  borderRadius: "50%",
                  border: `2px solid ${MANAGER_COLOR}`,
                  background: `${MANAGER_COLOR}22`,
                }}
              />
              <span style={{ color: "var(--text-secondary)" }}>Менеджер</span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 8px" }}>
              {Object.entries(STATUS_LABELS).map(([key, label]) => (
                <div key={key} className="flex items-center gap-1.5">
                  <div
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      background: STATUS_COLORS[key],
                      flexShrink: 0,
                    }}
                  />
                  <span style={{ color: "var(--text-muted)", fontSize: 10 }}>{label}</span>
                </div>
              ))}
            </div>

            <div style={{ marginTop: 8, color: "var(--text-muted)", fontSize: 10 }}>
              Размер узла = сумма долга
            </div>
          </motion.div>

          {/* ── Selected node details ── */}
          {selectedNode && (
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              className="glass-panel rounded-xl"
              style={{
                position: "absolute",
                top: 16,
                right: 16,
                padding: 16,
                width: 260,
                zIndex: 20,
              }}
            >
              <div className="flex items-center justify-between" style={{ marginBottom: 12 }}>
                <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: 14 }}>
                  {selectedNode.type === "manager" ? "Менеджер" : "Клиент"}
                </span>
                <button
                  onClick={() => setSelectedNode(null)}
                  style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}
                >
                  <X size={14} />
                </button>
              </div>

              <div className="space-y-2 text-xs">
                <div>
                  <span style={{ color: "var(--text-muted)" }}>Имя: </span>
                  <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>{selectedNode.label}</span>
                </div>

                {selectedNode.type === "manager" && (
                  <>
                    <div>
                      <span style={{ color: "var(--text-muted)" }}>Роль: </span>
                      <span style={{ color: "var(--text-secondary)" }}>{selectedNode.role}</span>
                    </div>
                    <div>
                      <span style={{ color: "var(--text-muted)" }}>Клиентов: </span>
                      <span style={{ color: "var(--accent)", fontWeight: 600 }}>{selectedNode.client_count}</span>
                    </div>
                  </>
                )}

                {selectedNode.type === "client" && (
                  <>
                    <div>
                      <span style={{ color: "var(--text-muted)" }}>Статус: </span>
                      <span
                        className="inline-flex rounded-full px-2 py-0.5"
                        style={{
                          background: `${STATUS_COLORS[selectedNode.status || "new"]}22`,
                          color: STATUS_COLORS[selectedNode.status || "new"],
                          border: `1px solid ${STATUS_COLORS[selectedNode.status || "new"]}44`,
                          fontSize: 10,
                        }}
                      >
                        {STATUS_LABELS[selectedNode.status || "new"] || selectedNode.status}
                      </span>
                    </div>
                    {selectedNode.debt_amount !== undefined && selectedNode.debt_amount > 0 && (
                      <div>
                        <span style={{ color: "var(--text-muted)" }}>Долг: </span>
                        <span style={{ color: "#FBBF24", fontWeight: 500 }}>
                          {new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", maximumFractionDigits: 0 }).format(selectedNode.debt_amount)}
                        </span>
                      </div>
                    )}
                    {selectedNode.source && (
                      <div>
                        <span style={{ color: "var(--text-muted)" }}>Источник: </span>
                        <span style={{ color: "var(--text-secondary)" }}>{selectedNode.source}</span>
                      </div>
                    )}
                  </>
                )}
              </div>
            </motion.div>
          )}

          {/* ── Status summary bar ── */}
          {data && !loading && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 }}
              className="glass-panel rounded-xl"
              style={{
                position: "absolute",
                bottom: 16,
                right: 16,
                padding: "10px 14px",
                fontSize: 11,
              }}
            >
              <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: 6 }}>
                Воронка
              </div>
              <div className="flex gap-1.5" style={{ alignItems: "flex-end", height: 50 }}>
                {Object.entries(data.status_counts)
                  .sort(([a], [b]) => {
                    const order = Object.keys(STATUS_LABELS);
                    return order.indexOf(a) - order.indexOf(b);
                  })
                  .map(([status, count]) => {
                    const maxCount = Math.max(...Object.values(data.status_counts));
                    const barHeight = Math.max(4, (count / maxCount) * 40);
                    return (
                      <div
                        key={status}
                        title={`${STATUS_LABELS[status] || status}: ${count}`}
                        style={{
                          width: 14,
                          height: barHeight,
                          borderRadius: 3,
                          background: STATUS_COLORS[status] || "#94A3B8",
                          opacity: filterStatus && filterStatus !== status ? 0.3 : 1,
                          cursor: "pointer",
                          transition: "opacity 0.2s",
                        }}
                        onClick={() => setFilterStatus(filterStatus === status ? "" : status)}
                      />
                    );
                  })}
              </div>
            </motion.div>
          )}
        </div>
      </div>
    </AuthLayout>
  );
}
