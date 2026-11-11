// Routing and responsibility only. The owning service authorizes every write.
// There is deliberately no second browser scheduler or agent execution engine.
export const workspaceContracts = {
 'change-control': {execution:'Inspect retained authorization, execution and delivery separately.', agent:'Agent findings are evidence, not approval.', receipt:'Open the owning workflow before making a decision.', next:'data-flow', nextLabel:'Open Data Flow'},
 'data-flow': {execution:'Approved jobs run in a background worker; this page follows the retained run.', agent:'Optional agent review does not replace job validation.', receipt:'A completed job still needs a separate publication receipt.', next:'data-products', nextLabel:'Build a product from run evidence'},
 ontology: {execution:'The Governor proposes and coordinates; the Steward assesses the retained scope.', agent:'Review holds and reasoning limitations remain visible before publication.', receipt:'Approval and graph publication use the owning ontology workflow.', next:'change-control', nextLabel:'Inspect cross-workspace change evidence'},
 catalog: {execution:'Discover ingested sources and published product versions.', agent:'Discovery does not approve a source or certify its business quality.', receipt:'Check the product version, lineage and delivery receipt before reuse.', next:'data-products', nextLabel:'Open product governance'},
 'data-products': {execution:'Select retained evidence, review its semantic release and validate the product contract.', agent:'Agents may explain evidence; an authorized publication action creates the release.', receipt:'Packaging and catalog delivery have separate retained outcomes.', next:'catalog', nextLabel:'Find released products'},
 registry: {execution:'Maintain source definitions, ownership and versioned semantic releases.', agent:'An investigation does not transition the asset lifecycle.', receipt:'An approved definition is distinct from a prepared dataset or published product.', next:'data-flow', nextLabel:'Prepare registered source data'},
};

export const taskIsPending = run => ['queued','running','dispatching','paused','interrupted','pause_requested','cancel_requested'].includes(run?.execution_state || run?.status);
