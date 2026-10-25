import { CARD, SectionHeader, ResultEmptyState } from "./RecommendationPrimitives.js";
import React, { useEffect, useRef } from "react";
import * as d3 from "d3";
import { BarChart2, Target } from "lucide-react";
import { UI_COLORS as C } from "../../styles/uiTokens";

const RING_COLORS = [C.red, C.orange, C.amber, C.primary, C.green];

const RadialImpactGraph = ({ data }) => {
  const svgRef = useRef(null);

  useEffect(() => {
    if (!svgRef.current || !data?.change_entity) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const width = svgRef.current.clientWidth || 600;
    const height = 420;
    const cx = width / 2, cy = height / 2;
    svg.attr('width', width).attr('height', height);

    const rings = [
      { label: 'Direct Impact',  items: (data.impacted_parts || []).map(p => p.name),                                    color: RING_COLORS[0] },
      { label: 'Assembly',       items: [...new Set((data.assembly_impact || []).map(a => a.assembly_name))].slice(0, 16), color: RING_COLORS[1] },
      { label: 'Requirements',   items: (data.impacted_requirements || []).map(r => r.name),                              color: RING_COLORS[2] },
      { label: 'Processes',      items: [...new Set((data.process_impacts || []).map(p => p.name))].slice(0, 16),         color: RING_COLORS[3] },
      { label: 'Realization',    items: (data.realization_chain || []).map(r => r.name),                                  color: RING_COLORS[4] },
    ].filter(r => r.items.length > 0);

    if (rings.length === 0) return;

    const maxRadius = Math.min(cx, cy) - 30;
    const ringStep = maxRadius / (rings.length + 1);
    const g = svg.append('g').attr('transform', `translate(${cx},${cy})`);

    // Tooltip div (appended to body for correct positioning)
    let radialTip = d3.select('body').select('.radial-tip');
    if (radialTip.empty()) {
      radialTip = d3.select('body').append('div').attr('class', 'radial-tip')
        .style('position', 'absolute').style('pointer-events', 'none')
        .style('background', 'rgba(26,43,60,0.92)').style('color', '#fff')
        .style('padding', '6px 12px').style('border-radius', '6px')
        .style('font-size', '12px').style('font-weight', '600')
        .style('z-index', '9999').style('opacity', '0')
        .style('transition', 'opacity .15s ease');
    }

    // Draw concentric rings
    rings.forEach((ring, ri) => {
      const r = ringStep * (ri + 1);
      g.append('circle')
        .attr('r', r)
        .attr('fill', 'none')
        .attr('stroke', ring.color)
        .attr('stroke-width', 1.5)
        .attr('stroke-dasharray', '6,4')
        .attr('opacity', 0.5);

      // Ring label
      g.append('text')
        .attr('x', r + 4)
        .attr('y', -4)
        .attr('font-size', 10)
        .attr('fill', ring.color)
        .attr('font-weight', 600)
        .text(`${ring.label} (${ring.items.length})`);

      // Distribute items around the ring
      ring.items.forEach((name, i) => {
        const angle = (2 * Math.PI * i) / ring.items.length - Math.PI / 2;
        const nx = r * Math.cos(angle);
        const ny = r * Math.sin(angle);

        // Line from center
        g.append('line')
          .attr('x1', 0).attr('y1', 0)
          .attr('x2', nx).attr('y2', ny)
          .attr('stroke', ring.color)
          .attr('stroke-width', 0.5)
          .attr('opacity', 0.25);

        // Node dot (interactive)
        g.append('circle')
          .attr('cx', nx).attr('cy', ny)
          .attr('r', 5)
          .attr('fill', ring.color)
          .attr('stroke', '#fff')
          .attr('stroke-width', 1.5)
          .style('cursor', 'pointer')
          .on('mouseover', function(event) {
            d3.select(this).attr('r', 9).attr('stroke-width', 2);
            radialTip
              // Names come from graph/import data. Use D3 text binding rather
              // than HTML interpolation so a source value cannot execute.
              .text(`${name}\n${ring.label}`)
              .style('white-space', 'pre-line')
              .style('left', (event.pageX + 12) + 'px')
              .style('top', (event.pageY - 28) + 'px')
              .style('opacity', '1');
          })
          .on('mousemove', function(event) {
            radialTip.style('left', (event.pageX + 12) + 'px').style('top', (event.pageY - 28) + 'px');
          })
          .on('mouseout', function() {
            d3.select(this).attr('r', 5).attr('stroke-width', 1.5);
            radialTip.style('opacity', '0');
          });

        // Label (show only if few items)
        if (ring.items.length <= 8) {
          g.append('text')
            .attr('x', nx)
            .attr('y', ny - 8)
            .attr('text-anchor', 'middle')
            .attr('font-size', 9)
            .attr('fill', C.textPrimary)
            .text(name.length > 20 ? name.slice(0, 18) + 'Ã¢â‚¬Â¦' : name);
        }
      });
    });

    g.append('circle').attr('r', 20).attr('fill', C.orange).attr('stroke', '#fff').attr('stroke-width', 2);
    g.append('text').attr('text-anchor', 'middle').attr('dy', 4)
      .attr('font-size', 9).attr('fill', '#fff').attr('font-weight', 700).text('CR');

    // Legend
    const legend = svg.append('g').attr('transform', `translate(10, ${height - 20 * rings.length - 10})`);
    rings.forEach((ring, i) => {
      const ly = i * 18;
      legend.append('circle').attr('cx', 6).attr('cy', ly).attr('r', 5).attr('fill', ring.color);
      legend.append('text').attr('x', 16).attr('y', ly + 4).attr('font-size', 11).attr('fill', C.textSec)
        .text(`${ring.label}: ${ring.items.length}`);
    });

  }, [data]);

  if (!data?.change_entity) {
    return (
      <ResultEmptyState
        icon={Target}
        title="No radial impact view available"
        message={data?.message || 'The change-impact response did not include a structured change entity for radial visualization.'}
        color={C.orange}
      />
    );
  }
  const hasAnyData = (data.impacted_parts?.length || data.assembly_impact?.length ||
    data.impacted_requirements?.length || data.process_impacts?.length || data.realization_chain?.length);
  if (!hasAnyData) {
    return (
      <ResultEmptyState
        icon={Target}
        title="No radial impact view available"
        message="The change-impact response loaded successfully, but there are no impacted nodes to visualize in the radial view."
        color={C.orange}
      />
    );
  }

  return (
    <div style={{ ...CARD, padding: '12px' }}>
      <SectionHeader icon={Target} label="Impact Radial View" color={C.orange} />
      <svg ref={svgRef} style={{ width: '100%', minHeight: '420px' }} />
    </div>
  );
};

const FLOW_COLORS = { direct: C.primary, instance: C.orange, related: C.amber };

const ProcessFlowTimeline = ({ data }) => {
  const svgRef = useRef(null);

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
    const width = svgRef.current.clientWidth || 700;
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
          .attr('fill', '#fff').attr('stroke', group.color).attr('stroke-width', 1);
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
  }, [data]);

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
        message="The manufacturing response loaded successfully, but there are no direct, instance, or related processes to draw in the timeline."
        color={C.green}
      />
    );
  }

  return (
    <div style={{ ...CARD, padding: '12px' }}>
      <SectionHeader icon={BarChart2} label="Process Flow Timeline" color={C.primary} />
      <svg ref={svgRef} style={{ width: '100%', minHeight: '200px' }} />
    </div>
  );
};

export { RING_COLORS, RadialImpactGraph, FLOW_COLORS, ProcessFlowTimeline };
