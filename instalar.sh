#!/usr/bin/env bash
set -euo pipefail
command -v python3 >/dev/null || { echo 'Instale Python: sudo apt install python3'; exit 1; }
origem="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
destino="$HOME/.local/share/minhas-musicas"
mkdir -p "$destino/web" "$HOME/.config/systemd/user"
if [[ "$origem" != "$destino" ]]; then
  cp "$origem/servidor.py" "$destino/servidor.py"
  cp "$origem/web/index.html" "$destino/web/index.html"
fi
python3 - "$destino" <<'PY'
from pathlib import Path
import sys
root=Path(sys.argv[1])
def quoted(s):
    return '"'+str(s).replace('\\','\\\\').replace('"','\\"').replace('%','%%')+'"'
unit='''[Unit]
Description=Minha seleção musical local
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 '''+quoted(root/'servidor.py')+'''
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
'''
(Path.home()/'.config/systemd/user/minhas-musicas.service').write_text(unit)
PY
if command -v systemctl >/dev/null && systemctl --user daemon-reload && systemctl --user enable --now minhas-musicas.service; then
  echo 'Instalado! Acesse http://localhost:8765'
  echo 'O serviço será iniciado automaticamente nas próximas sessões do seu usuário.'
else
  echo 'Arquivos instalados, mas o serviço automático não pôde ser ativado.'
  echo "Para iniciar manualmente: python3 \"$destino/servidor.py\""
fi
