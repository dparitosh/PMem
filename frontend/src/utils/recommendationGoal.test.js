import {recommendationGoalEvidence} from './recommendationGoal';
const context={recommendation_service:'change-impact',recommendation_object:'Motor',recommendation_top_n:10};
const run={status:'completed',context,result:{recommendation_observation_id:'observation-2'},observations:[{id:'observation-2',tool_id:'recommendation.change_impact',status:'completed',result:{decision_policy:{status:'blocked'}}}]};
test('only selected, cited, untruncated server evidence is displayed',()=>{
 expect(recommendationGoalEvidence(run,context).decision_policy.status).toBe('blocked');
 expect(recommendationGoalEvidence(run,{...context,recommendation_object:'Other'})).toBeNull();
 expect(recommendationGoalEvidence({...run,status:'running'},context)).toBeNull();
 expect(recommendationGoalEvidence({...run,result:{summary:'Uncited claim'}},context)).toBeNull();
 expect(recommendationGoalEvidence({...run,observations:[{...run.observations[0],result:{truncated:true,decision_policy:{status:'passed'}}}]},context)).toBeNull();
});
