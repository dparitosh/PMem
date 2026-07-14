/**
 * This file was generated from DepoGraphMiner.xml
 * WARNING: All changes made to this file will be overwritten
 * @author Mendix Widgets Framework Team
 */
import { ActionValue, DynamicValue, Option } from "mendix";
import { CSSProperties } from "react";

export type RendererEnum = "reactFlow" | "d3";

export interface DepoGraphMinerContainerProps {
    name: string;
    class: string;
    style?: CSSProperties;
    tabIndex?: number;
    nodesJson: DynamicValue<string>;
    linksJson: DynamicValue<string>;
    selectedNodeId?: DynamicValue<string>;
    onNodeSelect?: ActionValue<{ nodeId: Option<string>; nodeLabel: Option<string>; nodeType: Option<string> }>;
    onGraphChange?: ActionValue;
    renderer: RendererEnum;
    height: number;
    showLabels: boolean;
    maxNodes: number;
}

export interface DepoGraphMinerPreviewProps {
    /**
     * @deprecated Deprecated since version 9.18.0. Please use class property instead.
     */
    className: string;
    class: string;
    style: string;
    styleObject?: CSSProperties;
    readOnly: boolean;
    renderMode: "design" | "xray" | "structure";
    translate: (text: string) => string;
    nodesJson: string;
    linksJson: string;
    selectedNodeId: string;
    onNodeSelect: {} | null;
    onGraphChange: {} | null;
    renderer: RendererEnum;
    height: number | null;
    showLabels: boolean;
    maxNodes: number | null;
}
