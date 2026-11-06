import { diagramTypeConfigs } from '../../config/diagramTypes';

const registry = new Map(diagramTypeConfigs.map((config) => [config.id, config]));

export function registerDiagramType(config) {
  if (!config?.id) throw new Error('Diagram type config requires id.');
  registry.set(config.id, config);
  return config;
}

export function getDiagramType(id = 'uaf') {
  return registry.get(id) || registry.get('uaf') || [...registry.values()][0];
}

export function listDiagramTypes() {
  return [...registry.values()];
}
