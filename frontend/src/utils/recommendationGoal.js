import {normalizeRecommendationResult} from '../features/recommendations/services/recommendationPresentation';
export const recommendationTools = {'change-impact':'recommendation.change_impact','similar-parts':'recommendation.similar_parts',manufacturing:'recommendation.manufacturing'};
export function recommendationGoalEvidence(run,context){
 if(!run||run.status!=='completed'||!run.result?.recommendation_observation_id)return null;
 if(['recommendation_service','recommendation_object','recommendation_top_n'].some(key=>run.context?.[key]!==context[key]))return null;
 if(['node_id','ontology_id','ontology_prefix'].some(key=>(run.context?.[key]||'')!==(context[key]||'')))return null;
 if(!Array.isArray(run.observations))return null;
 const observation=run.observations.find(item=>item?.id===run.result.recommendation_observation_id);
 const result=observation?.result;
 if(observation?.status!=='completed'||observation.tool_id!==recommendationTools[context.recommendation_service]||!result||result.truncated||!result.decision_policy)return null;
 try{return normalizeRecommendationResult(context.recommendation_service,result);}catch{return null;}
}
export function recommendationTask(context){
 return `Investigate ${context.recommendation_service} for the exact graph object ${JSON.stringify(context.recommendation_object)}. Use the matching recommendation tool with the selected result limit ${context.recommendation_top_n}. Review graph evidence, heuristic score limits and the returned shared Semantica decision-policy assessment. Cite that observation in your conclusion. Explain missing evidence and holds; do not approve or publish changes.`;
}
