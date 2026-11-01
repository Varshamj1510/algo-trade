import os
import subprocess
import sys


def test_render_rejects_sqlite_database_configuration():
    environment = os.environ.copy()
    environment['DATABASE_URL'] = 'sqlite:///temporary.db'
    environment['RENDER_EXTERNAL_URL'] = 'https://alphamind.example.onrender.com'

    result = subprocess.run(
        [sys.executable, '-c', 'import backend.config'],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert 'Render requires persistent PostgreSQL' in result.stderr
