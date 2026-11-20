"""Independent read-only Store close observation and protected targeted regression."""
import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
import psycopg
import pytest
from psycopg.conninfo import make_conninfo
from psycopg_pool import AsyncConnectionPool
from pydantic import SecretStr
from app.core.config import Settings
from app.infrastructure.postgres import open_pool, validate_test_target
from app.infrastructure.store import store_resources
from scripts import run_async
from scripts.verify_05_memory_manage import database_snapshot, fingerprints

OUT = ROOT / 'docs/question/06-state-events-qa-evidence-20261114.json'
report = {}

def protected_files():
    paths = [ROOT / '.env', ROOT / 'AGENTS.md']
    for directory in ('app', 'tests', 'migrations', '.codex', 'scripts'):
        paths.extend(p for p in (ROOT / directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

async def observe():
    original = Settings()
    validate_test_target(original.test_database_url, original.database_url)
    settings = original.model_copy(update={'database_url': original.test_database_url, 'app_env': 'test'})
    pool = await open_pool(settings)
    before = await database_snapshot(pool)
    report['protected_before'] = fingerprints(before)
    prefix = 'qa612-close-' + uuid4().hex
    report['observation_prefix'] = prefix
    report['close_observations'] = []
    observer = await psycopg.AsyncConnection.connect(original.test_database_url.get_secret_value(), autocommit=True)
    try:
        for mode in ('normal', 'exception', 'cancel'):
            for index in range(4):
                name = f'{prefix}-{mode}-{index}'
                identified = settings.model_copy(update={'database_url': SecretStr(make_conninfo(original.test_database_url.get_secret_value(), application_name=name))})
                captured = []
                close = AsyncConnectionPool.close
                async def observed_close(self, *args, **kwargs):
                    clients = list(self._pool)
                    await close(self, *args, **kwargs)
                    captured.append({'pool_closed': self.closed, 'clients_closed': [c.closed for c in clients]})
                async def rows():
                    return await (await observer.execute('SELECT pid,state FROM pg_stat_activity WHERE application_name=%s', (name,))).fetchall()
                entered = asyncio.Event()
                async def owner():
                    async with store_resources(identified) as resource:
                        await resource.aget(('qa612', prefix), 'absent')
                        observed = await rows()
                        assert observed
                        entered.set()
                        if mode == 'exception':
                            raise ValueError('deliberate exit')
                        if mode == 'cancel':
                            await asyncio.Event().wait()
                with patch.object(AsyncConnectionPool, 'close', observed_close):
                    task = asyncio.create_task(owner())
                    if mode == 'cancel':
                        await entered.wait()
                        task.cancel()
                    try:
                        await task
                    except ValueError:
                        assert mode == 'exception'
                    except asyncio.CancelledError:
                        assert mode == 'cancel'
                start = time.perf_counter()
                samples = [{'ms': 0, 'backends': await rows()}]
                if samples[0]['backends']:
                    for delay in (0.02, 0.1, 0.5):
                        await asyncio.sleep(delay)
                        samples.append({'ms': round((time.perf_counter()-start)*1000, 2), 'backends': await rows()})
                report['close_observations'].append({'mode': mode, 'index': index, 'client': captured, 'samples': samples})
                assert all(c['pool_closed'] and all(c['clients_closed']) for c in captured)
                assert samples[-1]['backends'] == []
        report['remaining_named_backends'] = await (await observer.execute('SELECT application_name,pid,state FROM pg_stat_activity WHERE application_name LIKE %s', (prefix+'%',))).fetchall()
        assert not report['remaining_named_backends']
    finally:
        after = await database_snapshot(pool)
        report['protected_after'] = fingerprints(after)
        report['protected_unchanged'] = before == after
        await observer.close()
        await pool.close()
        OUT.write_text(json.dumps(report, indent=2), encoding='utf-8')
        assert before == after

before_files = protected_files()
run_async(observe())
os.environ['AGENT_TEST_DATABASE_URL'] = Settings().test_database_url.get_secret_value()
report['targeted_exit'] = pytest.main(['tests/test_memory_postgres.py::test_real_store_cross_threads_process_persistence_and_exact_cleanup', '-q', '--tb=short'])
report['protected_files_unchanged'] = before_files == protected_files()
OUT.write_text(json.dumps(report, indent=2), encoding='utf-8')
assert report['protected_files_unchanged']
print('Independent Store observations:', len(report['close_observations']), 'targeted exit:', report['targeted_exit'])
