"""Offline regression tests. Run with the project's Python; no SQL/API access."""
import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace as NS
import pandas as pd
import pyodbc

# Fail closed if imports or tests unexpectedly try external connections.
SQL_GUARD=patch.object(pyodbc,'connect',side_effect=AssertionError('SQL disabled in offline suite'))
NETWORK_GUARD=patch.object(socket.socket,'connect',side_effect=AssertionError('Network disabled in offline suite'))
SQL_GUARD.start();NETWORK_GUARD.start()
sys.path.insert(0,os.getenv('VENESSE_TEST_PROJECT',str(Path(__file__).resolve().parent)))
import venesse_ai_agent_edit as agent
import venesse_ai_client as client
import venesse_ai_interpreter as interpreter
import venesse_ai_summary as summary
import venesse_html as sales_html


def sales(year=2026):
    return pd.DataFrame({'order_date_key':[year*10000+101,year*10000+201], 'net_revenue':[100.,200.], 'cogs':[60.,150.]})


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env=patch.dict(os.environ,{'VENESSE_AI_PROVIDER':'nanogpt','VENESSE_AI_MODEL':'offline-test','NANOGPT_API_KEY':'offline-test-only','VENESSE_AI_USAGE_LOG':str(Path(self.temp.name)/'usage.jsonl')})
        self.env.start();self.addCleanup(self.env.stop)
        summary._COMMENTARY_CACHE.clear()

    def test_sales_financials(self):
        with patch.object(agent,'fetch_sales_data',return_value=sales()):report=agent.generate_sales_report(2026)
        for expected in ('Total Revenue: $300.00','Total COGS: $210.00','Gross Profit: $90.00','Gross Margin: 30.00%','Overall: PASS'):self.assertIn(expected,report)

    def test_invalid_financial_values(self):
        for value in (float('inf'),float('nan'),'bad'):
            with self.subTest(value=value):
                frame=sales();frame['net_revenue']=frame['net_revenue'].astype(object);frame.loc[0,'net_revenue']=value
                with patch.object(agent,'fetch_sales_data',return_value=frame):self.assertIn('Cannot generate',agent.generate_sales_report(2026))

    def test_out_of_period(self):
        for date in (20261001,20250101,20260230):
            with self.subTest(date=date):
                frame=sales();frame.loc[0,'order_date_key']=date
                with patch.object(agent,'fetch_sales_data',return_value=frame):self.assertIn('Cannot generate',agent.generate_sales_report(2026))

    def test_zero_revenue(self):
        frame=sales();frame['net_revenue']=0
        with patch.object(agent,'fetch_sales_data',return_value=frame):self.assertIn('N/A (zero revenue)',agent.generate_sales_report(2026))

    def test_fetch_failure_and_empty(self):
        for frame in (None,pd.DataFrame()):
            with patch.object(agent,'fetch_sales_data',return_value=frame):self.assertNotIn('Overall: PASS',agent.generate_sales_report(2026))

    def test_all_action_shapes(self):
        for action,count in interpreter.YEAR_COUNTS.items():
            with self.subTest(action=action):self.assertIsNone(agent.validate_business_request({'action':action,'years':[2025,2026][-count:],'export':action.endswith('_html')}))

    def test_reject_unsafe_request_shapes(self):
        for request in ({'action':'execute_sql','years':[2026],'export':False},{'action':'sales_report','years':[True],'export':False},{'action':'year_comparison','years':[2026,2026],'export':False},{'action':'sales_html','years':[2026],'export':False},{'action':'sales_report','years':[2026],'export':'yes'}):
            self.assertIsNotNone(agent.validate_business_request(request))

    def test_api_failure_falls_back_to_dashboard(self):
        with patch.object(interpreter,'create_json_completion',side_effect=TimeoutError),contextlib.redirect_stdout(io.StringIO()):
            result=interpreter.interpret_business_request('Generate sales HTML report for 2026',agent.parse_business_request,agent.validate_business_request)
        self.assertEqual(result,{'action':'sales_html','years':[2026],'export':True})

    def test_invalid_model_command_does_not_dispatch(self):
        with patch.object(interpreter,'create_json_completion',side_effect=client.InvalidAIResponse):
            result=interpreter.interpret_business_request('Sales for 2026',agent.parse_business_request,agent.validate_business_request)
        self.assertIn('error',result)

    def test_dispatch_and_summary(self):
        request={'action':'sales_report','years':[2026],'export':False}
        with patch.object(agent,'interpret_business_request',return_value=request),patch.object(agent,'generate_sales_report',return_value='report') as handler,patch.object(agent,'add_ai_summary_to_result',return_value='enriched'),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(agent.business_agent('Sales 2026'),'enriched')
        handler.assert_called_once_with(2026)

    def test_txt_export_success_and_reject_failure(self):
        with patch.object(agent,'fetch_sales_data',return_value=sales()):status=agent.export_sales_report(2026,output_folder=self.temp.name)
        path=Path(status.splitlines()[-1]);self.assertTrue(path.is_file());self.assertIn('Overall: PASS',path.read_text(encoding='utf-8'))
        with patch.object(agent,'generate_sales_report',return_value='Overall: FAIL'):self.assertIn('not saved',agent.export_sales_report(2026,output_folder=self.temp.name))

    def test_html_export_no_browser(self):
        with patch.object(sales_html.webbrowser,'open') as browser:
            status=sales_html.export_sales_html(2026,lambda year:sales(year),output_folder=self.temp.name,open_browser=False)
        browser.assert_not_called();self.assertTrue(Path(status.splitlines()[-1]).is_file())

    def test_commentary_failure_preserves_report(self):
        report='VENESSE SALES REPORT\nTotal Revenue: $300.00\nOverall: PASS'
        with patch.object(summary,'create_json_completion',side_effect=TimeoutError),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(summary.add_ai_summary(report),report)

    def test_cache_invalidation_and_no_failure_cache(self):
        with patch.object(summary,'_generate_commentary',return_value='validated') as generate,contextlib.redirect_stdout(io.StringIO()):
            summary._commentary('source',True,'data1');summary._commentary('source',True,'data1');self.assertEqual(generate.call_count,1)
            summary._commentary('source',True,'data2');self.assertEqual(generate.call_count,2)
            with patch.dict(os.environ,{'VENESSE_AI_MODEL':'other'}):summary._commentary('source',True,'data2')
            self.assertEqual(generate.call_count,3)
        with patch.object(summary,'_generate_commentary',return_value=None) as generate:
            summary._commentary('failure');summary._commentary('failure');self.assertEqual(generate.call_count,2)

    def test_timestamp_normalization_preserves_caveat(self):
        self.assertEqual(summary._stable_evidence_line('January–September Generated 2026-11-17 19:36:36'),'January–September')
        self.assertEqual(summary._stable_evidence_line('Generated 2026-11-17 19:36:36. Provisional costs.'),'Provisional costs.')

    def test_duplicate_filter_keeps_monthly_detail(self):
        highlights=['Operating profit increased but remained negative.']
        self.assertTrue(summary._repeats_highlight('Operating losses remained negative.',highlights))
        self.assertFalse(summary._repeats_highlight('Operating profit was negative in seven months.',highlights))

    def test_seven_section_highlights_and_source_budget(self):
        labels={'sales':'Revenue','customers':'Repeat customer rate','retention':'Retention rate','products':'Units sold','marketing':'Profit after marketing','feedback':'Average rating','operating':'Operating profit · provisional'}
        document='<main>'+''.join(f'<section id="{key}"><template shadowrootmode="open"><article><p>{label}</p><strong>10</strong></article></template></section>' for key,label in labels.items())+'</main>'
        cards=summary._ExecutiveCards();cards.feed(document)
        self.assertEqual(len(cards.highlights()),7)
        parser=summary._DashboardText();parser.feed(document);parser.flush()
        source=summary._compact_html_source(parser)
        self.assertLess(len(source),8200)
        for title,_ in cards.PICKS.values():self.assertIn('['+title+']',source)

    def test_feedback_current_only_wording(self):
        cases={'Total reviews 169 N/A vs 2022':'Total reviews: 169.',
               'Average rating 3.97 / 5 N/A vs 2022':'Average rating: 3.97 / 5.',
               'Negative-review rate 14.79% N/A vs 2022':'Negative-review rate: 14.79%.',
               '[Report] Units sold 1,914':'Units sold: 1,914.'}
        for line,expected in cases.items():self.assertEqual(summary._readable_kpi_statement(line),expected)

    def test_feedback_source_omits_missing_baseline(self):
        parser=summary._DashboardText()
        parser.feed('<article><p>Average rating</p><strong>3.97 / 5</strong><small>N/A vs 2022</small></article>');parser.flush()
        source=summary._compact_html_source(parser)
        self.assertNotIn('2022',source);self.assertIn('3.97 / 5',source)

    def test_single_row_comparison_is_omitted(self):
        response=NS(choices=[NS(finish_reason='stop',message=NS(content=json.dumps({'observations':[
            {'text':'Furniture margin exceeded Electronics margin.','evidence_line':2},
            {'text':'Headphones had the highest product gross profit.','evidence_line':3}]})))])
        report='VENESSE SOURCE\n[Report] Furniture | 380 | 27.85%\n[Report] Highest product gross profit: Headphones ($10,697.72).'
        with patch.object(summary,'create_json_completion',return_value=response),contextlib.redirect_stdout(io.StringIO()):result=summary._generate_commentary(report,html_source=True)
        self.assertNotIn('Furniture',result);self.assertIn('Headphones',result)

    def test_explicit_two_share_summary_is_retained(self):
        text='The share of positive reviews was higher than negative reviews.'
        response=NS(choices=[NS(finish_reason='stop',message=NS(content=json.dumps({'observations':[{'text':text,'evidence_line':2}]})))])
        report='VENESSE SOURCE\n[Report] 75.74% of reviews were positive, 9.47% neutral, and 14.79% negative.'
        with patch.object(summary,'create_json_completion',return_value=response):result=summary._generate_commentary(report,html_source=True)
        self.assertIn(text,result)

    def test_usage_metadata_and_totals(self):
        @client.track_request_usage
        def request():
            client._record_usage(NS(usage=NS(prompt_tokens=10,completion_tokens=2,total_tokens=12)),'offline-test','test',.1,'response_received')
            client.record_commentary_cache_hit()
        output=io.StringIO()
        with contextlib.redirect_stdout(output):request()
        self.assertIn('10 input / 2 output tokens reported',output.getvalue())
        row=json.loads((Path(self.temp.name)/'usage.jsonl').read_text())
        self.assertFalse({'messages','api_key','prompt','content'} & row.keys())
        self.assertIsNone(client._REQUEST_USAGE.get())


if __name__=='__main__':unittest.main(verbosity=2)
