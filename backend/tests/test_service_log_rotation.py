from concurrent.futures import ThreadPoolExecutor
from backend.depo_platform.service_log_stream import RotatingServiceStream


def test_partial_writes_unicode_and_concurrent_rotation_are_bounded(tmp_path):
    path=tmp_path/'service.err.log'
    stream=RotatingServiceStream(path,max_bytes=512,backups=2)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _:stream.write('event αβγ\n'*30),range(25)))
    stream.write('final ');stream.write('receipt\n');stream.close()
    files=list(tmp_path.glob('service.err.log*'))
    assert len(files)<=3
    assert all(file.stat().st_size<=512 for file in files)
    assert path.read_text(encoding='utf-8').endswith('final receipt\n')


def test_one_huge_print_is_rotated_in_bounded_chunks(tmp_path):
    path=tmp_path/'service.out.log'
    with RotatingServiceStream(path,max_bytes=128,backups=2) as stream:
        assert stream.write('x'*10000)==10000
    assert len(list(tmp_path.iterdir()))==3
    assert all(file.stat().st_size<=128 for file in tmp_path.iterdir())


def test_logging_reconfiguration_cannot_close_the_live_service_stream(tmp_path):
    import logging.config
    import subprocess,sys
    # Run real dictConfig in a child so pytest's capture handlers are unaffected.
    source="""from backend.depo_platform.service_log_stream import RotatingServiceStream
import logging.config
from pathlib import Path
p=Path(__import__('sys').argv[1])
s=RotatingServiceStream(p,max_bytes=128,backups=2)
s.write('before reconfiguration\\n')
logging.config.dictConfig({'version':1,'handlers':{},'root':{'handlers':[],'level':'INFO'}})
s.write('after reconfiguration\\n')
s.close()
assert 'after reconfiguration' in p.read_text()
"""
    result=subprocess.run([sys.executable,'-c',source,str(tmp_path/'service.err.log')],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
