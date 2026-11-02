# Orientações do projeto

Leia também @/home/harlem/.codex/RTK.md quando disponível.

- Aplicação local leve para Debian e 8 GB de RAM; FastAPI + React/Vite.
- Preserve web/, servidor.py, iniciar.sh, instalar.sh e LEIA-ME.md como referência do protótipo na porta 8765. O instalador antigo configura systemd: não executá-lo durante desenvolvimento.
- Execute a nova aplicação por executar.sh em 127.0.0.1:8766. Não configurar inicialização automática nem usar Docker.
- Python sempre em .venv; nunca usar --break-system-packages.
- Etapa 1: metadados, importação, filtro, seleção e cópia. Não adicionar busca global do YouTube.
- Etapa 2 implementada: fila serial MP3/FFmpeg, progresso, cancelamento de grupos de processos e SQLite em ~/.local/share/seletor-musical/; mídia em ~/Música/SeletorMusical. Não aceitar caminhos do navegador nem sobrescrever MP3s concluídos. Use IDs de vídeo para nomes de arquivo e temporários separados por item. Não retomar fila automaticamente após reinício.
- Etapa 3A: catálogo library_tracks no mesmo SQLite, streaming por ID e player HTML audio único persistente. Indexar apenas MP3s diretos na pasta fixa; ignorar .partial e symlinks. FFprobe em segundo plano com timeout e cache. Preservar histórico e MP3s em falhas de indexação. Fila de reprodução, favoritos e playlists ficam para etapas posteriores.
- URLs do YouTube devem ser validadas no backend. Nunca shell=True ou comandos concatenados com entrada do usuário. Não aceitar caminhos do navegador.
- Manter validação de Host/Origin e cabeçalho personalizado nas ações, sem CORS permissivo; operações externas assíncronas com tempo limite e encerramento de subprocessos.
- Não registrar cookies, credenciais ou saída bruta do yt-dlp. Não implementar cookies nesta etapa.
- .gitignore deve existir antes de git add. Nunca versionar ambientes, node_modules, builds, downloads, SQLite ou segredos.
- Não fazer push, publicar nem criar commits sem solicitação.
- Testes: .venv/bin/python -m unittest discover -s tests -v; em frontend: npm test e npm run build.
- Validar download real apenas com vídeo autorizado pelo usuário. Autorizado nesta sessão: https://www.youtube.com/watch?v=ClU3fctbGls. Não acessar cookies do navegador; YouTube pode exigir confirmação anti-bot. Testes de mídia sintética local não precisam de autorização adicional.
