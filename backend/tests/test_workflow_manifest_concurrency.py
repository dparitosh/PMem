import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ManifestConcurrencyTests(unittest.TestCase):
    def test_multiple_processes_preserve_every_artifact_record(self):
        script = "from pathlib import Path; import sys; from backend.Services.workflow_artifact_service import WorkflowArtifactService as S; S.ARTIFACT_ROOT=Path(sys.argv[1]); S.write_bytes('shared-task','reports',sys.argv[2],sys.argv[2].encode(),'report')"
        environment = dict(os.environ)
        environment.pop('DEPO_DATABASE_URL',None)
        environment.pop('DATABASE_URL',None)
        with tempfile.TemporaryDirectory() as directory:
            children=[subprocess.Popen([sys.executable,'-B','-c',script,directory,f'report-{index}.txt'],env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for index in range(6)]
            for child in children:
                _, errors=child.communicate(timeout=30)
                self.assertEqual(child.returncode,0,errors.decode())
            manifest=json.loads((Path(directory)/'shared-task'/'manifest.json').read_text())
            self.assertEqual({item['path'] for item in manifest['artifacts']},{f'reports/report-{index}.txt' for index in range(6)})
            for item in manifest['artifacts']:
                self.assertTrue((Path(directory)/'shared-task'/item['path']).is_file())


if __name__ == '__main__': unittest.main()
