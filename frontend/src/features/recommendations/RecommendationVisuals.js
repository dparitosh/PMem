import { CARD, SectionHeader, ResultEmptyState } from "./RecommendationPrimitives.js";
import React, { useEffect, useRef, useState } from "react";
import * as d3 from "d3";
import { BarChart2 } from "lucide-react";
import { UI_COLORS as C } from "../../styles/uiTokens";

const FLOW_COLORS = { direct: C.primary, instance: C.orange, related: C.amber };

const ProcessFlowTimeline = ({ data }) => {
  const svgRef = useRef(null);
  const [layoutWidth, setLayoutWidth] = useState(700);
  useEffect(() => {
    const element = svgRef.current;
    if (!element) return;
    const measure = () => setLayoutWidth(Math.max(320, element.clientWidth || 700));
    measure();
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(measure) : null;
    observer?.observe(element.parentElement);
    window.addEventListener('resize', measure);
    return () => { observer?.disconnect(); window.removeEventListener('resize', measure); };
  }, [data]);

  useEffect(() => {
    if (!svgRef.current || !data?.part) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    // Gather groups
    const groups = [];
    if (data.direct_processes?.length) groups.push({ label: 'Direct Processes', items: data.direct_processes.map(p => ({ name: p.process_name, tag: p.source_tag })), color: FLOW_COLORS.direct });
    if (data.process_instances?.length) groups.push({ label: 'Process Instances', items: data.process_instances.map(p => ({ name: p.name, tag: p.source_tag })), color: FLOW_COLORS.instance });
    if (data.related_part_processes?.length) groups.push({ label: 'Related Processes', items: data.related_part_processes.slice(0, 20).map(p => ({ name: p.process_name, tag: p.source_tag })), color: FLOW_COLORS.related });
    if (groups.length === 0) return;

    const itemH = 28, groupPad = 40, headerH = 30, leftPad = 160;
    const totalH = groups.reduce((h, g) => h + headerH + g.items.length * itemH + groupPad, 0) + 20;
    const width = layoutWidth;
    svg.attr('width', width).attr('height', totalH);

    let yOffset = 15;
    const g = svg.append('g');

    // Central timeline line
    g.append('line')
      .attr('x1', leftPad - 10).attr('y1', 0)
      .attr('x2', leftPad - 10).attr('y2', totalH)
      .attr('stroke', C.border).attr('stroke-width', 2);

    groups.forEach((group) => {
      // Group header
      g.append('rect')
        .attr('x', 0).attr('y', yOffset)
        .attr('width', width - 20).attr('height', headerH)
        .attr('rx', 6)
        .attr('fill', group.color).attr('opacity', 0.1);
      g.append('text')
        .attr('x', 12).attr('y', yOffset + 20)
        .attr('font-size', 13).attr('font-weight', 700).attr('fill', group.color)
        .text(`${group.label} (${group.items.length})`);
      yOffset += headerH + 4;

      // Items
      group.items.forEach((item, i) => {
        const iy = yOffset + i * itemH;
        // Dot on timeline
        g.append('circle')
          .attr('cx', leftPad - 10).attr('cy', iy + itemH / 2)
          .attr('r', 5).attr('fill', group.color).attr('stroke', '#fff').attr('stroke-width', 1.5);
        // Connector line
        g.append('line')
          .attr('x1', leftPad - 5).attr('y1', iy + itemH / 2)
          .attr('x2', leftPad + 8).attr('y2', iy + itemH / 2)
          .attr('stroke', group.color).attr('stroke-width', 1).attr('opacity', 0.5);
        // Process card
        g.append('rect')
          .attr('x', leftPad + 10).attr('y', iy + 2)
          .attr('width', Math.min(width - leftPad - 40, 400)).attr('height', itemH - 5)
          .attr('rx', 4)
          .attr('fill', C.surface).attr('stroke', group.color).attr('stroke-width', 1);
        // Name
        g.append('text')
          .attr('x', leftPad + 18).attr('y', iy + itemH / 2 + 4)
          .attr('font-size', 11).attr('fill', C.textPrimary)
          .text(item.name?.length > 45 ? item.name.slice(0, 43) + 'Ã¢â‚¬Â¦' : item.name);
        // Tag badge
        if (item.tag) {
          const tagX = leftPad + Math.min(width - leftPad - 40, 400) - 5;
          g.append('text')
            .attr('x', tagX).attr('y', iy + itemH / 2 + 3)
            .attr('text-anchor', 'end')
            .attr('font-size', 9).attr('fill', group.color).attr('font-weight', 600)
            .text(item.tag);
        }
      });
      yOffset += group.items.length * itemH + groupPad;
    });
  }, [data, layoutWidth]);

  if (!data?.part) {
    return (
      <ResultEmptyState
        icon={BarChart2}
        title="No process timeline available"
        message={data?.message || 'The manufacturing response did not include a structured part for timeline rendering.'}
        color={C.green}
      />
    );
  }
  const hasAny = data.direct_processes?.length || data.process_instances?.length || data.related_part_processes?.length;
  if (!hasAny) {
    return (
      <ResultEmptyState
        icon={BarChart2}
        title="No process timeline available"
        message="No assessed process links were returned for this timeline. Unassessed categories do not establish that process links are absent."
        color={C.green}
      />
    );
  }

  return (
    <div style={{ ...CARD, padding: '12px', overflowX: 'auto' }}>
      <SectionHeader icon={BarChart2} label="Process links by category" color={C.primary} />
      <svg ref={svgRef} role="img" aria-label="Recorded processes by category" style={{ width: '100%', minWidth: 320, minHeight: '200px' }} />
    </div>
  );
};

export { FLOW_COLORS, ProcessFlowTimeline };
