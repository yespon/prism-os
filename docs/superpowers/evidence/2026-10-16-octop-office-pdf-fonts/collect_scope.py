from pathlib import Path
import json,sys
import pytest
HERE=Path(__file__).resolve().parent
class Records:
 def __init__(self):self.nodes=[];self.skipped=[]
 def pytest_collectreport(self,report):
  if report.skipped:self.skipped.append({'nodeid':report.nodeid,'reason':str(report.longrepr)})
 def pytest_collection_finish(self,session):self.nodes=[item.nodeid for item in session.items]
records=Records()
code=pytest.main(['tests/','--collect-only','-q'],plugins=[records])
(HERE/'collection-scope.json').write_text(json.dumps({'returncode':code,'nodes':records.nodes,'skipped_collectors':records.skipped},indent=2)+'\n')
print(json.dumps({'collected_nodes':len(records.nodes),'skipped_collectors':records.skipped}))
raise SystemExit(code)
