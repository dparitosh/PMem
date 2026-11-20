import re
from contextlib import contextmanager
from unittest.mock import MagicMock
import pytest
from backend.mesh_store import PostgresRegistry


@pytest.mark.parametrize('size',[1,49,50,51,57,64])
def test_projected_registry_pages_stay_within_postgres_function_limits(size):
    registry=PostgresRegistry('fixture')
    cursor=MagicMock();cursor.fetchone.return_value=(1,);cursor.fetchall.return_value=[({'field0':'retained'},)]
    database=MagicMock();database.cursor.return_value.__enter__.return_value=cursor
    @contextmanager
    def connection():yield database
    registry._connect=connection
    projection={f'field{index}':['nested',str(index)] for index in range(size)}
    total,rows=registry.page(limit=25,projection=projection)
    assert total==1 and rows==[{'field0':'retained'}]
    statement,args=cursor.execute.call_args.args
    calls=re.findall(r'jsonb_build_object\(([^)]*)\)',statement)
    assert sum(call.count('%s::text, value') for call in calls)==size
    assert all(call.count('%s::text, value')*2<=100 for call in calls)
    assert len(args)==2*size+3
    assert args[:2]==['field0',['nested','0']]
    assert args[-3:]==['fixture',25,0]
