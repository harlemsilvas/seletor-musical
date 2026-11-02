# Dependências e referências de terceiros

A licença [MIT](LICENSE) cobre o código e a documentação originais deste projeto. Ela não substitui as licenças das dependências nem concede direitos sobre músicas, vídeos, miniaturas, marcas ou outros materiais de terceiros.

## Dependências

A aplicação utiliza FastAPI/Starlette, Uvicorn, yt-dlp/EJS, mutagen (tags ID3, instalado com `yt-dlp[default]` e usado diretamente), React/Vite e suas dependências transitivas. FFmpeg/FFprobe e Node.js são programas externos necessários ao funcionamento. Playwright é usado apenas em testes opcionais.

As versões Python de referência estão em `requirements.lock.txt`; as dependências JavaScript estão em `frontend/package-lock.json`. Consulte os arquivos de licença e avisos distribuídos com cada versão efetivamente instalada. Alterações de versão ou modo de distribuição podem mudar as obrigações aplicáveis.

Os programas externos não são incorporados a um instalador neste repositório. Antes de distribuir binários ou pacotes para Windows/macOS, revise as licenças e avisos de todos os componentes incluídos, especialmente a compilação escolhida do FFmpeg. Este documento não é um inventário completo de licenças de um futuro instalador.

## Referência funcional

[dsymbol/yt-dlp-gui](https://github.com/dsymbol/yt-dlp-gui) foi consultado como referência funcional. A [licença Unlicense](https://github.com/dsymbol/yt-dlp-gui/blob/main/LICENSE) foi consultada; nenhum código foi copiado desse projeto e sua interface PySide6 não foi incorporada.

O protótipo existente em `web/` e os scripts antigos foram preservados como referência do próprio projeto. Qualquer reutilização futura de outros materiais deve registrar origem e condições de uso.
