from scripts.benchmark_agent import blocked_reply, classify_outcome, summarize


def row(duration, **extra):
    return {'case':'trip','complete':True,'error':None,'model':'gpt-test',
            'action':'main_agent','answer':'A sourced itinerary','duration_s':duration,
            'http_status':200,'within_5s':duration<=5,'degraded':False,**extra}


def test_guard_rejection_is_not_a_successful_business_answer():
    rejected=row(13,answer=blocked_reply('en'),action='web_agent')
    assert classify_outcome(rejected)=='blocked'
    rejected['outcome']=classify_outcome(rejected)
    result=summarize([rejected])
    assert result['answer_count']==0
    assert result['model_answer_p50_s'] is None
    assert not result['answer_p50_target_met']


def test_even_sized_model_sample_uses_arithmetic_median():
    results=[row(t,outcome='answer') for t in [4.793,4.954,22.622,27.016]]
    result=summarize(results)
    assert result['model_answer_p50_s']==13.788
    assert result['answer_p95_s']==27.016
    assert not result['answer_p50_target_met']


def test_errors_refusals_and_clarifications_cannot_lower_answer_median():
    cases=[row(0.1,complete=False),row(0.1,case='pet_health',action='refuse'),
           row(0.1,case='off_topic',action='refuse'),row(0.1,action='clarify'),row(12)]
    for item in cases:
        item['outcome']=classify_outcome(item)
    result=summarize(cases)
    assert result['p50_s']==0.1
    assert result['answer_p50_s']==12
    assert result['answer_count']==1
    assert not result['answer_p50_target_met']
