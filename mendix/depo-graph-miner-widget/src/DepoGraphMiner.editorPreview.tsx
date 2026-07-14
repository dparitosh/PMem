import { ReactElement } from "react";
import { DepoGraphMinerPreviewProps } from "../typings/DepoGraphMinerProps";

export function preview(props: DepoGraphMinerPreviewProps): ReactElement {
    return (
        <div style={{ height: props.height || 520, border: "1px solid #9fb3c8", display: "grid", placeItems: "center", color: "#334e68" }}>
            DEPO Graph Miner · {props.renderer === "d3" ? "D3" : "React Flow"}
        </div>
    );
}

export function getPreviewCss(): string {
    return "";
}
