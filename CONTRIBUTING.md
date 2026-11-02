# Como contribuir

Contribuições de código, documentação, acessibilidade e testes são bem-vindas. Leia o [código de conduta](CODE_OF_CONDUCT.md), a [licença MIT](LICENSE) e as orientações em [AGENTS.md](AGENTS.md).

## Escopo atual

A referência funcional é a aplicação local no Debian: FastAPI + React/Vite, SQLite, yt-dlp e FFmpeg. Preserve os arquivos do protótipo e não configure serviços de inicialização automática. Fila de reprodução e organização pessoal seguem o [planejamento](PLANO-BIBLIOTECA.md).

Windows e macOS estão em desenvolvimento. Propostas de portabilidade devem cobrir diretórios, scripts de execução, trava da instância e encerramento de processos/descendentes. A adaptação não estará validada apenas por compilar a interface; informe a plataforma e o que foi testado nela.

## Ambiente de desenvolvimento

Siga primeiro a instalação no [README](README.md). Use sempre `.venv`, sem `--break-system-packages`.

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
npm --prefix frontend ci
```

Não versione `.venv`, `node_modules`, builds, músicas, bancos, logs, cookies ou segredos. O `.gitignore` já cobre os principais arquivos locais. Antes de adicionar arquivos, revise `git status --short` e os arquivos que serão incluídos.

## Testes essenciais

Na raiz do projeto:

```bash
.venv/bin/python -m unittest discover -s tests -v
npm --prefix frontend test
npm --prefix frontend run build
git diff --check
```

Os testes de mídia usam FFmpeg/FFprobe e áudio sintético local; alguns são ignorados se esses programas não estiverem disponíveis. Não considere testes ignorados como validação da conversão. Testes que consultam o YouTube ou baixam mídia real devem ser explícitos e usar conteúdo autorizado. Não inclua downloads reais na execução automática da suíte.

## Testes opcionais no navegador

Playwright é ferramenta de desenvolvimento, não dependência de produção. No Debian, você pode instalá-lo separadamente:

```bash
npm install --prefix /tmp/seletor-browser playwright
/tmp/seletor-browser/node_modules/.bin/playwright install chromium
```

Com a aplicação aberta em `localhost:8766`, execute os testes abaixo separadamente. Eles simulam respostas dos endpoints de downloads e não devem baixar mídia real:

```bash
NODE_PATH=/tmp/seletor-browser/node_modules node tests/browser-smoke.cjs
NODE_PATH=/tmp/seletor-browser/node_modules node tests/browser-verification.cjs
```

Para testar o player com MP3 real sintético e banco temporário, abra em outro terminal:

```bash
PYTHONPATH=. .venv/bin/python tests/serve_library_fixture.py
```

O servidor de teste usa `127.0.0.1:8767`. Depois execute:

```bash
NODE_PATH=/tmp/seletor-browser/node_modules node tests/browser-library.cjs
```

Ctrl+C encerra o servidor de teste e limpa seus dados temporários. Se precisar usar Chromium já instalado, defina `CHROMIUM_PATH=/caminho/para/chrome` no comando de teste. Firefox ainda precisa de validação manual.

## Propor uma mudança

1. Descreva o problema ou a melhoria, consultando issues existentes se houver um repositório remoto.
2. Faça uma alteração de escopo claro, preservando arquivos e dados do usuário.
3. Atualize a documentação e adicione testes quando houver comportamento novo ou risco relevante. Correções apenas editoriais não exigem testes de execução.
4. Descreva no pull request o resultado, os testes realizados e as limitações. Use o modelo disponível em `.github`.

Não publique arquivos pessoais, URLs privadas, logs completos ou credenciais. Use exemplos sintéticos e revise capturas de tela. Falhas de segurança seguem o fluxo de [SECURITY.md](SECURITY.md).

## Regras técnicas

- Escutar somente em loopback; manter validação de Host/Origin nas ações.
- Validar URLs no backend; subprocessos com lista de argumentos e sem shell.
- Não aceitar caminhos arbitrários do navegador nem sobrescrever músicas concluídas.
- Manter consultas, downloads e indexação fora do bloqueio do servidor.
- Preservar histórico e arquivos em migrações, cancelamento e falhas de indexação.
- Documentar alterações de dependências e revisar os arquivos de versões fixadas.
- Não adicionar login, coleta de dados ou leitura de cookies como efeito indireto de outra funcionalidade.

Ao enviar uma contribuição, você declara ter direito de oferecê-la sob a licença MIT do projeto. Dependências e código de terceiros devem manter os avisos e as condições de suas próprias licenças.
