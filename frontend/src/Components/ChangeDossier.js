import React from 'react';
import {businessText} from '../utils/businessText';

const object = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
const text = value => ['string','number','boolean'].includes(typeof value) ? businessText(String(value)) : 'Not recorded';
const validDigest = value => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
const localLink = value => typeof value === 'string' && value.startsWith('#/');

export default function ChangeDossier({dossier}) {
  if (!dossier || object(dossier) !== dossier) return <p>Detailed baseline and release evidence is unavailable for this record.</p>;
  const baseline=object(dossier.baseline), release=object(dossier.release), proposal=object(dossier.request);
  const isRequest=proposal.resource_type === 'oslc_cm:ChangeRequest' || proposal.type === 'oslc_cm:ChangeRequest';
  const order=object(release.order);
  const isOrder=isRequest&&typeof proposal.identifier==='string'&&proposal.identifier.trim()&&(order.operation==='publish_selected_mappings'?order.request_id===proposal.identifier&&order.order_id===release.operation_identifier:order.order_id===proposal.identifier)&&
    typeof order.authorized_by==='string'&&order.authorized_by.trim()&&['authorized','executing','executed','needs_recovery','awaiting_delivery'].includes(proposal.state)&&(['create_merged_draft','coordinate_source_to_release'].includes(order.operation)&&order.publish===false||['publish_selected_mappings','publish_product_version','publish_accepted_partition','publish_ontology_artifact'].includes(order.operation)&&order.publish===true)&&validDigest(order.plan_digest)&&order.plan_digest===release.plan_digest;
  const rawMembers=Array.isArray(baseline.members) ? baseline.members : [];
  const seen=new Set();
  const members=rawMembers.slice(0,16).filter(member=>{
    if (object(member)!==member || typeof member.identifier!=='string' || !member.identifier.trim() || member.identifier.length>300 || !validDigest(member.artifact_sha256) || seen.has(member.identifier)) return false;
    seen.add(member.identifier);return true;
  });
  const incomplete=(baseline.members!==undefined && !Array.isArray(baseline.members)) || members.length!==rawMembers.length ||
    members.some(member=>!localLink(member.workspace)) ||
    (baseline.snapshot_digest!=null && !validDigest(baseline.snapshot_digest)) || (release.plan_digest!=null && !validDigest(release.plan_digest));
  return <section aria-label="Change dossier">
    <div className="change-control__dossier-phases">
      <section><h4>{isRequest ? 'Change request (CR)' : 'Retained evidence'}</h4><p>{text(proposal.state)}</p><p>Review remains with the owning workflow.</p></section>
      <section><h4>Source baseline</h4><p>{incomplete ? 'Incomplete source evidence' : text(baseline.status)}</p><p>{text(baseline.currentness)}</p></section>
      <section><h4>{isOrder ? 'Authorized release (CO)' : isRequest ? 'Native authorization and execution' : 'Execution evidence'}</h4><p>{text(release.state)}</p><p>{text(release.authority)}</p></section>
    </div>
    {incomplete && <p role="status">Some source evidence is incomplete or unsupported. No missing versions were substituted.</p>}
    {members.length > 0 && <ul aria-label="Retained source versions">{members.map(member=><li key={member.identifier}>{localLink(member.workspace) ? <a href={member.workspace}>{text(member.title || member.identifier)}</a> : <span>{text(member.title || member.identifier)}</span>}<details><summary>Retained version identity</summary><code>{member.identifier}</code><p>Artifact digest: <code>{member.artifact_sha256}</code></p></details></li>)}</ul>}
    <p>Execution: {text(release.execution_state)}. Delivery: {text(release.delivery_state)}.</p>
    <details><summary>Baseline and reviewed-plan identities</summary><dl><dt>Baseline digest</dt><dd>{validDigest(baseline.snapshot_digest) ? baseline.snapshot_digest : 'Not recorded'}</dd><dt>Plan schema</dt><dd>{text(release.plan_schema)}</dd><dt>Plan digest</dt><dd>{validDigest(release.plan_digest) ? release.plan_digest : 'Not recorded'}</dd></dl><p>{text(baseline.configuration_conformance)}</p></details>
    <p>A request, baseline or agent assessment does not authorize a write. Existing service approval and validation still apply.</p>
  </section>;
}
