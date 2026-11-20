import * as d3 from 'd3';
import {safeString} from '../../utils/safeAccess';
import {getLinkEndpointId} from '../../utils/graphUtils';
import {logger} from '../../utils/logger';
import {TCS_GRAPH_THEME,resolveNodeType,resolveNodeName} from './graphRenderingPolicy';
const VIEWPORT_PADDING=50;
const ENTITY_COLOR_SWATCH = [
  '#1F3D63', '#0F766E', '#7C3AED', '#C05621', '#0E7490', '#A16207',
  '#BE185D', '#486581', '#355C7D', '#2F855A', '#B45309', '#6B46C1',
];

const hashText = (value) => {
  const text = String(value || '');
  let hash = 0;
  for (let index = 0; index < text.length; index += 1) {
    hash = ((hash << 5) - hash) + text.charCodeAt(index);
    hash |= 0;
  }
  return Math.abs(hash);
};

const resolveNodeColorKey = (nodeLike) => {
  if (typeof nodeLike === 'string') return nodeLike;
  const props = nodeLike?.properties && typeof nodeLike.properties === 'object' && !Array.isArray(nodeLike.properties)
    ? nodeLike.properties
    : nodeLike || {};
  return safeString(
    props.sub_type ||
    props.subtype ||
    props.entity_subtype ||
    props.entitySubtype ||
    props.subclass ||
    props.sub_class ||
    props.subclass_of ||
    props.subClassOf ||
    props.parent_class ||
    props.parentClass ||
    props.super_class ||
    props.superClass ||
    props.owl_class ||
    props.owlClass ||
    props.rdf_type ||
    props.rdfType ||
    props.class_label ||
    props.entity_type ||
    props.original_type ||
    props.concept_type ||
    props.class_name ||
    props.type ||
    nodeLike?.entity_type ||
    nodeLike?.label ||
    nodeLike?.labels?.[0] ||
    'Node',
    'Node'
  );
};

const varyColorBySeed = (baseColor, seed, options = {}) => {
  const {
    lightnessRange = 18,
    saturationBoost = 0,
    chromaFloor = 26,
  } = options;
  const color = d3.hcl(baseColor);
  if (!color) return baseColor;
  const hash = hashText(seed || baseColor);
  const offset = (hash % (lightnessRange * 2 + 1)) - lightnessRange;
  color.l = Math.max(32, Math.min(78, color.l + offset));
  color.c = Math.max(chromaFloor, Math.min(92, color.c + saturationBoost + ((hash % 9) - 4)));
  return color.formatHex();
};

const ONTOLOGY_CLASS_PALETTE = ['#163E6D', '#1D4F91', '#2563EB', '#3B82F6', '#5B9BFF', '#2B6CB0'];
const OBJECT_PROPERTY_PALETTE = ['#C05621', '#DD6B20', '#F97316', '#FB923C', '#EA580C', '#B45309'];
const DATATYPE_PROPERTY_PALETTE = ['#2C5282', '#3B82F6', '#60A5FA', '#D97706', '#F59E0B', '#FDBA74'];

const pickPaletteColor = (palette, seed) => {
  if (!Array.isArray(palette) || palette.length === 0) return TCS_GRAPH_THEME.primary;
  return palette[hashText(seed) % palette.length];
};

  const processLinksForOffset = (links) => {
    // First, filter out HAS_PARENT links when there's a corresponding HAS_CHILD link
    const filteredLinks = [];
    const hasChildPairs = new Set();

    // First pass: identify all HAS_CHILD relationships
    links.forEach(link => {
      if (link.type === 'HAS_CHILD') {
        const sourceId = getLinkEndpointId(link.source);
        const targetId = getLinkEndpointId(link.target);
        const pairKey = [sourceId, targetId].sort().join('-');
        hasChildPairs.add(pairKey);
      }
    });

    // Second pass: filter out HAS_PARENT if HAS_CHILD exists for the same node pair
    links.forEach(link => {
      if (link.type === 'HAS_PARENT') {
        const sourceId = getLinkEndpointId(link.source);
        const targetId = getLinkEndpointId(link.target);
        const pairKey = [sourceId, targetId].sort().join('-');

        // Skip HAS_PARENT if HAS_CHILD exists for the same node pair
        if (hasChildPairs.has(pairKey)) {
          logger.render('Filtering out HAS_PARENT link as HAS_CHILD exists for the same node pair:', pairKey);
          return; // Skip this link
        }
      }
      filteredLinks.push(link);
    });

    // Group links by node pairs (regardless of direction)
    const linkPairs = new Map();

    filteredLinks.forEach(link => {
      // Create a consistent key for node pairs (sorted to handle both directions)
      const sourceId = getLinkEndpointId(link.source);
      const targetId = getLinkEndpointId(link.target);
      const pairKey = [sourceId, targetId].sort().join('-');

      if (!linkPairs.has(pairKey)) {
        linkPairs.set(pairKey, []);
      }
      linkPairs.get(pairKey).push(link);
    });

    // Add offset information to links that have multiple relationships
    linkPairs.forEach(pairLinks => {
      if (pairLinks.length > 1) {
        // Multiple links between same nodes - add offset info
        pairLinks.forEach((link, index) => {
          link.isOffset = true;
          link.offsetIndex = index;
          link.totalOffsets = pairLinks.length;
        });
      } else {
        // Single link - no offset needed
        pairLinks[0].isOffset = false;
      }
    });

    return filteredLinks;
  };

  // Function to calculate curved path for bidirectional links
  const calculateCurvedPath = (link, sourceX, sourceY, targetX, targetY) => {
    if (!link.isOffset || link.totalOffsets <= 1) {
      // Single direction link - use straight line
      return `M${sourceX},${sourceY}L${targetX},${targetY}`;
    }

    // Calculate curve parameters for bidirectional links
    const dx = targetX - sourceX;
    const dy = targetY - sourceY;
    const length = Math.sqrt(dx * dx + dy * dy);

    if (length === 0) return `M${sourceX},${sourceY}L${targetX},${targetY}`;

    // Perpendicular unit vector for curve direction
    const perpX = -dy / length;
    const perpY = dx / length;

    // Calculate curve offset - ensure opposite directions for bidirectional links
    const baseOffset = Math.max(50, length * 0.2); // Larger base offset for more visible curves

    // Create consistent curve direction based on link direction and offset index
    // For bidirectional links, we want them to curve in opposite directions
      const sourceId = getLinkEndpointId(link.source);
      const targetId = getLinkEndpointId(link.target);

    // Use source and target IDs to determine consistent curve direction
    const linkDirection = sourceId < targetId ? 1 : -1;
    const offsetDirection = link.offsetIndex % 2 === 0 ? 1 : -1;
    const curveDirection = linkDirection * offsetDirection;

    const offsetMultiplier = Math.floor(link.offsetIndex / 2) + 1; // Increase curve for multiple pairs
    const curveOffset = baseOffset * offsetMultiplier * curveDirection;

    // Calculate control point for quadratic curve
    const midX = (sourceX + targetX) / 2;
    const midY = (sourceY + targetY) / 2;
    const controlX = midX + perpX * curveOffset;
    const controlY = midY + perpY * curveOffset;

    // Return quadratic curve path
    return `M${sourceX},${sourceY}Q${controlX},${controlY} ${targetX},${targetY}`;
  };

const boundaryForce = (width, height) => {
  let nodes;

  const force = (alpha) => {
    nodes.forEach(node => {
      const padding = VIEWPORT_PADDING;
      const strength = 0.1 * alpha;

      if (node.x < padding) {
        node.vx += (padding - node.x) * strength;
      } else if (node.x > width - padding) {
        node.vx += (width - padding - node.x) * strength;
      }

      if (node.y < padding) {
        node.vy += (padding - node.y) * strength;
      } else if (node.y > height - padding) {
        node.vy += (height - padding - node.y) * strength;
      }
    });
  };

  force.initialize = (_nodes) => { nodes = _nodes; };
  return force;
};

export const getNodeColor = (nodeLike) => {
    const label = resolveNodeType(nodeLike);
    if (!label) return TCS_GRAPH_THEME.inkMuted;
    const nodeLabels = Array.isArray(nodeLike?.labels) ? nodeLike.labels.map((entry) => String(entry || '')) : [];
    const subtypeKey = resolveNodeColorKey(nodeLike);
    const displayName = resolveNodeName(nodeLike);
    const normalizedLabel = String(subtypeKey || label).toLowerCase();
    const hashSeed = (() => {
      const baseKey = String(subtypeKey || label || 'Node').toLowerCase();
      const genericType = ['ontologyclass', 'class', 'individual', 'resource', 'node', 'entity', 'item'].includes(baseKey);
      if (genericType && displayName) return `${baseKey}:${displayName}`;
      return subtypeKey || label;
    })();

    // Explicit color map for known ontology labels - optimized for clarity
    const colorMap = {
      // Ontology Schema Layer (Classes and Properties)
      'OntologyClass':     '#1F3D63',
      'Class':             '#274C77',
      'ObjectProperty':    '#5D6D7E',
      'DatatypeProperty':  '#8D6E63',
      'OntologyProperty':  '#5D6D7E',
      'Property':          '#5D6D7E',
      'Relationship':      '#486581',
      'Annotation':        '#7B8794',
      'Requirement':       '#7C3AED',
      'RequirementRevision':'#6D28D9',
      'Specification':     '#5B21B6',
      'Document':          '#0F766E',
      'Package':           '#0E7490',
      'View':              '#BE185D',

      // Instance Data Layer
      'Individual':        '#486581',
      'Resource':          '#61788A',
      'Datum':             '#61788A',

      // CAD/PLM Specific
      'Part':              '#355C7D',
      'SurfaceFinish':     '#8D6E63',
      'Dimension':         '#486581',
      'GeometricTolerance':'#3E4C59',

      // File Types
      'PLMXMLFile':        '#7B8794',
      'StepFile':          '#9AA5B1',
      'StepInstance':      '#52606D',
      'MetadataAsset':     '#0F766E',
      'GeneralRelation':   '#C05621',
    };

    const explicitColor = colorMap[subtypeKey] || colorMap[label];
    const variantSeed = `${subtypeKey || label}:${displayName || hashSeed}`;
    const isOntologyClassFamily = label === 'OntologyClass' || nodeLabels.includes('OntologyClass');
    const isObjectPropertyFamily = ['ObjectProperty', 'OntologyProperty', 'Property'].includes(label) || nodeLabels.includes('ObjectProperty');
    const isDatatypePropertyFamily = label === 'DatatypeProperty' || nodeLabels.includes('DatatypeProperty');
    if (isOntologyClassFamily) {
      return pickPaletteColor(ONTOLOGY_CLASS_PALETTE, variantSeed);
    }
    if (isObjectPropertyFamily) {
      return pickPaletteColor(OBJECT_PROPERTY_PALETTE, variantSeed);
    }
    if (isDatatypePropertyFamily) {
      return pickPaletteColor(DATATYPE_PROPERTY_PALETTE, variantSeed);
    }
    if (explicitColor) {
      return varyColorBySeed(explicitColor, variantSeed, {
        lightnessRange: ['OntologyClass', 'ObjectProperty', 'DatatypeProperty', 'Property'].includes(label) ? 16 : 12,
        saturationBoost: ['OntologyClass', 'ObjectProperty', 'DatatypeProperty', 'Property'].includes(label) ? 6 : 0,
      });
    }

    if (normalizedLabel.includes('property')) return '#0E7490';
    if (normalizedLabel.includes('class')) return '#1F3D63';
    if (normalizedLabel.includes('assembly') || normalizedLabel.includes('bom')) return '#2F855A';
    if (normalizedLabel.includes('product')) return '#274C77';
    if (normalizedLabel.includes('part')) return '#355C7D';
    if (normalizedLabel.includes('requirement')) return '#7C3AED';
    if (normalizedLabel.includes('document')) return '#0F766E';
    if (normalizedLabel.includes('process')) return '#C05621';
    if (normalizedLabel.includes('geometry') || normalizedLabel.includes('shape') || normalizedLabel.includes('cad')) return '#8D6E63';
    if (normalizedLabel.includes('material')) return '#A16207';
    if (normalizedLabel.includes('organization') || normalizedLabel.includes('person')) return '#BE185D';
    if (normalizedLabel.includes('instance')) return '#486581';
    if (normalizedLabel.includes('metadata')) return '#0F766E';
    if (normalizedLabel.includes('generalrelation') || normalizedLabel.includes('trace')) return '#C05621';

    return ENTITY_COLOR_SWATCH[hashText(hashSeed) % ENTITY_COLOR_SWATCH.length];
  };

export {processLinksForOffset,calculateCurvedPath,boundaryForce};
