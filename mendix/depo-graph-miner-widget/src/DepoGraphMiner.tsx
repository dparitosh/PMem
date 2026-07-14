import { ReactElement, useCallback, useMemo, useState } from "react";
import { DepoGraphMinerContainerProps } from "../typings/DepoGraphMinerProps";
import { GraphCanvas, GraphData, GraphNode } from "./components/GraphCanvas";
import "./ui/DepoGraphMiner.css";

function parseArray<T>(value: string | undefined): T[] {
    if (!value) return [];
    try {
        const parsed: unknown = JSON.parse(value);
        return Array.isArray(parsed) ? parsed as T[] : [];
    } catch (_error) {
        return [];
    }
}

export function DepoGraphMiner(props: DepoGraphMinerContainerProps): ReactElement {
    const [internalSelectedId, setInternalSelectedId] = useState<string>();
    const graph = useMemo<GraphData>(() => {
        const limit = Math.max(1, Math.min(Number(props.maxNodes), 5000));
        const nodes = parseArray<GraphNode>(props.nodesJson.value)
            .filter(node => node && typeof node.id === "string" && node.id.length > 0)
            .slice(0, limit);
        const ids = new Set(nodes.map(node => node.id));
        const links = parseArray<{ source?: unknown; target?: unknown }>(props.linksJson.value)
            .filter(link => typeof link?.source === "string" && typeof link?.target === "string" && ids.has(link.source) && ids.has(link.target))
            .slice(0, limit * 10);
        return { nodes, links } as GraphData;
    }, [props.linksJson.value, props.maxNodes, props.nodesJson.value]);
    const selectedId = props.selectedNodeId?.value || internalSelectedId;
    const selectNode = useCallback((node: GraphNode): void => {
        setInternalSelectedId(node.id);
        if (props.onNodeSelect?.canExecute && !props.onNodeSelect.isExecuting) {
            props.onNodeSelect.execute({ nodeId: node.id, nodeLabel: node.label, nodeType: node.type });
        }
    }, [props.onNodeSelect]);
    const graphChanged = useCallback((): void => {
        if (props.onGraphChange?.canExecute && !props.onGraphChange.isExecuting) props.onGraphChange.execute();
    }, [props.onGraphChange]);

    return (
        <GraphCanvas
            graph={graph}
            renderer={props.renderer}
            selectedId={selectedId}
            height={Math.max(280, Number(props.height))}
            showLabels={props.showLabels}
            tabIndex={props.tabIndex}
            onSelect={selectNode}
            onGraphChange={graphChanged}
        />
    );
}
