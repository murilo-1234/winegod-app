"""
Carrega variaveis de ambiente do backend/.env automaticamente.
Uso: import _env  (no topo do script, antes de usar os.environ)
"""
import os

_env_path = os.path.join(os.path.dirname(__file__), '..', 'backend', '.env')
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _, _v = _line.partition('=')
                os.environ.setdefault(_k.strip(), _v.strip())
