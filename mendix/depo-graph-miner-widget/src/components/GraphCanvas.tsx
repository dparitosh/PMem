import { ReactElement, useEffect, useMemo, useRef } from "react";
import * as d3 from "d3";
import { Background, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

export interface GraphNode { id: string; label?: string; type?: string; x?: number; y?: number; [key: string]: unknown }
export interface GraphLink { id?: string; source: string; target: string; type?: string; [key: string]: unknown }
export interface GraphData { nodes: GraphNode[]; links: GraphLink[] }

interface Props {
    graph: GraphData;
    renderer: "reactFlow" | "d3";
    selectedId?: string;
    height: number;
    showLabels: boolean;
    tabIndex?: number;
    onSelect: (node: GraphNode) => void;
    onGraphChange: () => void;
}

function ReactFlowCanvas({ graph, selectedId, height, onSelect, onGraphChange }: Props): ReactElement {
    const nodes = useMemo(() => graph.nodes.map((node, index) => ({
        id: String(node.id),
        position: { x: Number(node.x) || (index % 5) * 180, y: Number(node.y) || Math.floor(index / 5) * 110 },
        data: { label: node.label || node.id, source: node },
        selected: node.id === selectedId
    })), [graph.nodes, selectedId]);
    const edges = useMemo(() => graph.links.map((link, index) => ({
        id: String(link.id || `${link.source}:${link.type || "RELATED_TO"}:${link.target}:${index}`),
        source: String(link.source), target: String(link.target), label: link.type || "RELATED_TO"
    })), [graph.links]);
    return (
        <div style={{ height }}>
            <ReactFlow nodes={nodes} edges={edges} fitView onNodeClick={(_event, node) => onSelect(node.data.source as GraphNode)} onNodeDragStop={onGraphChange}>
                <Background />
            </ReactFlow>
        </div>
    );
}

function D3Canvas({ graph, selectedId, height, showLabels, tabIndex, onSelect, onGraphChange }: Props): ReactElement {
    const ref = useRef<SVGSVGElement>(null);
    useEffect(() => {
        if (!ref.current) return;
        const width = Math.max(ref.current.clientWidth, 320);
        const nodes = graph.nodes.map(node => ({ ...node }));
        const links = graph.links.map(link => ({ ...link }));
        const svg = d3.select(ref.current);
        svg.selectAll("*").remove();
        const root = svg.append("g");
        const edge = root.append("g").selectAll("line").data(links).join("line").attr("stroke", "#9fb3c8");
        const node = root.append("g").selectAll("g").data(nodes).join("g").attr("tabindex", tabIndex ?? 0)
            .attr("role", "button").attr("aria-label", item => `${item.label || item.id}, ${item.type || "Element"}`)
            .on("click", (_event, item) => onSelect(item))
            .on("keydown", (event, item) => {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(item);
                }
            });
        node.append("circle").attr("r", item => item.id === selectedId ? 10 : 7).attr("fill", "#005ea8")
            .attr("stroke", item => item.id === selectedId ? "#111827" : "#fff").attr("stroke-width", 2);
        if (showLabels && nodes.length <= 250) node.append("text").attr("x", 11).attr("y", 4).attr("font-size", 10).text(item => item.label || item.id);
        const simulation = d3.forceSimulation(nodes as d3.SimulationNodeDatum[])
            .force("link", d3.forceLink(links).id((item: any) => item.id).distance(72))
            .force("charge", d3.forceManyBody().strength(-100)).force("center", d3.forceCenter(width / 2, height / 2))
            .on("tick", () => {
                edge.attr("x1", (item: any) => item.source.x).attr("y1", (item: any) => item.source.y)
                    .attr("x2", (item: any) => item.target.x).attr("y2", (item: any) => item.target.y);
                node.attr("transform", (item: any) => `translate(${item.x},${item.y})`);
            });
        node.call(d3.drag<SVGGElement, any>().on("start", (_event, item) => { item.fx = item.x; item.fy = item.y; simulation.alphaTarget(0.3).restart(); })
            .on("drag", (event, item) => { item.fx = event.x; item.fy = event.y; })
            .on("end", (_event, item) => { item.fx = null; item.fy = null; simulation.alphaTarget(0); onGraphChange(); }));
        return () => { simulation.stop(); svg.selectAll("*").remove(); };
    }, [graph, height, onGraphChange, onSelect, selectedId, showLabels, tabIndex]);
    return <svg ref={ref} width="100%" height={height} role="img" aria-label={`Graph with ${graph.nodes.length} nodes and ${graph.links.length} relationships`} />;
}

export function GraphCanvas(props: Props): ReactElement {
    if (!props.graph.nodes.length) return <div className="depo-graph-miner-empty">No graph data available.</div>;
    return props.renderer === "d3" ? <D3Canvas {...props} /> : <ReactFlowCanvas {...props} />;
}
