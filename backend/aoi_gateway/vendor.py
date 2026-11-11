"""Copy approved AOI assets byte-for-byte; never modify the IIF installation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys


def prepare(source, destination):
    if sys.version_info[:2] != (3, 12):
        raise ValueError('This gateway release requires CPython 3.12')
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination == source or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('Wrapper copies must be outside the IIF installation')
    names = {'CustomAOI_helper.py': source/'sample_package/CustomAOI_helper.py',
             'lib/CustomAOI.cpython-312.pyc': source/'lib/CustomAOI.cpython-312.pyc',
             'lib/CustomAOI_Core.cpython-312.pyc': source/'lib/CustomAOI_Core.cpython-312.pyc'}
    hashes = {}
    for name, path in names.items():
        data = path.read_bytes()
        if path.suffix == '.pyc' and data[:4] != importlib.util.MAGIC_NUMBER:
            raise ValueError('AOI bytecode does not match this Python interpreter')
        hashes[name] = hashlib.sha256(data).hexdigest()
    destination.mkdir(parents=True, exist_ok=True)
    for name, path in names.items():
        target = (destination/name).resolve()
        if not target.is_relative_to(destination) or target.is_relative_to(source):
            raise ValueError('Wrapper-copy path escapes the separate runtime directory')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != hashes[name]:
            raise ValueError('Wrapper-copy digest mismatch')
    receipt_path = (destination/'wrapper-receipt.json').resolve()
    if not receipt_path.is_relative_to(destination):
        raise ValueError('Wrapper receipt escapes the separate runtime directory')
    receipt_path.write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    return hashes


def verify(directory):
    directory = Path(directory).resolve()
    names = ('CustomAOI_helper.py', 'lib/CustomAOI.cpython-312.pyc', 'lib/CustomAOI_Core.cpython-312.pyc')
    receipt = json.loads((directory/'wrapper-receipt.json').read_text(encoding='utf-8'))
    if set(receipt) != set(names):
        raise ValueError('Incomplete AOI wrapper receipt')
    for name in names:
        path = (directory/name).resolve()
        if not path.is_relative_to(directory):
            raise ValueError('AOI wrapper path escapes its private directory')
        if hashlib.sha256(path.read_bytes()).hexdigest() != receipt[name]:
            raise ValueError('AOI wrapper changed after preparation')
