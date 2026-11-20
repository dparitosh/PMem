import React from 'react';

export default function ApprovalMatrix({change}) {
 const matrix=change?.approval_matrix;
 if(!matrix)return <section aria-label="Approval matrix"><h4>Approval matrix</h4><p>No matrix snapshot is retained for this historical request.</p></section>;
 const policy=matrix.policy;
 if(!policy||!Array.isArray(policy.stages)||!Array.isArray(matrix.signoffs))return <p role="alert">Approval matrix evidence is incomplete.</p>;
 return <section aria-label="Approval matrix"><h4>Approval matrix · {policy.name} · version {policy.revision}</h4><div className="change-control__table"><table><thead><tr><th>Stage</th><th>Responsible function</th><th>Assigned principals</th><th>Signoff</th><th>Recorded decisions</th></tr></thead><tbody>{policy.stages.map(row=>{const signs=matrix.signoffs.filter(s=>s.action===row.action&&s.plan_digest===matrix.plan_digest);return <tr key={row.action}><th>{row.action==='accept'?'CR evidence review':'CO authorization'}</th><td>{row.function}</td><td>{row.members.length?row.members.join(', '):'Verified owning-service approver'}</td><td>{row.mode}</td><td>{signs.length?signs.map(s=>`${s.actor} · ${new Date(s.at).toLocaleString()}`).join('; '):'Pending'}</td></tr>;})}</tbody></table></div><p>Requester approval: {policy.separate_requester?'Blocked':'Allowed'} · Review and authorization: {policy.distinct_stage_actors?'Different principals required':'May use the same principal'}</p></section>;
}
