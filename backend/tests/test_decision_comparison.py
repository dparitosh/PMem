import copy
import pytest
from backend.agentic_service.decision_comparison import evaluate
QUESTION='Require temperature <=80 degC, speed >=1500 rpm and lead time <=10 days. Choose the lowest incremental-cost feasible option.'
def fixture():
 return {'comparison_rows':[{'option_record_id':name,'option':name,'option_values':{'externalId':name,'estimatedIncrementalCost':cost,'cost_unit':'USD/unit','leadTime':days,'leadTime_unit':'day'},'evaluations':[{'record_id':'test-'+name,'values':{'externalId':'TEST-'+name,'temperature':temp,'temperature_unit':'degC','speed':speed,'speed_unit':'rpm'}}]} for name,cost,days,temp,speed in [('A',3,5,85,1500),('B',8,5,76,1500),('C',2,1,78,1300)]]}
def test_evaluates_actual_measurements_and_cost_without_hardcoded_winner():
 source=fixture();result=evaluate(QUESTION,source)
 assert result['comparison']['preferred_record_ids']==['B']
 assert 'TEST-B' in result['business_summary']
 source['comparison_rows'][0]['evaluations'][0]['values']['temperature']=75
 assert evaluate(QUESTION,source)['comparison']['preferred_record_ids']==['A']
 assert evaluate(QUESTION.replace('<=80','<=90'),fixture())['comparison']['preferred_record_ids']==['A']
@pytest.mark.parametrize('value',[None,'NaN',True,'not measured'])
def test_missing_or_invalid_potentially_feasible_measurement_holds(value):
 source=fixture();source['comparison_rows'][1]['evaluations'][0]['values']['temperature']=value
 with pytest.raises(ValueError):evaluate(QUESTION,source)
def test_unit_mismatch_and_conflicting_test_results_hold():
 source=fixture();source['comparison_rows'][1]['evaluations'][0]['values']['temperature_unit']='degF'
 with pytest.raises(ValueError):evaluate(QUESTION,source)
 source=fixture();test=copy.deepcopy(source['comparison_rows'][1]['evaluations'][0]);test['values']['temperature']=90;source['comparison_rows'][1]['evaluations'].append(test)
 with pytest.raises(ValueError):evaluate(QUESTION,source)
def test_unknown_criteria_and_missing_objective_hold():
 with pytest.raises(ValueError):evaluate(QUESTION.replace('temperature','pressure'),fixture())
 with pytest.raises(ValueError):evaluate(QUESTION.replace('lowest incremental-cost','preferred'),fixture())
def test_comparison_does_not_mutate_source_or_grant_approval():
 source=fixture();before=copy.deepcopy(source);result=evaluate(QUESTION,source)
 assert source==before
 assert result['comparison']['advisory_only'] is True
 assert 'approved' not in result['business_summary'].lower()
