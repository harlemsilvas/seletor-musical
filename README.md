# Seletor Musical

Aplicação web local para selecionar músicas do YouTube, baixar os vídeos escolhidos em MP3 e ouvir os arquivos em uma biblioteca no navegador. Desenvolvida com **FastAPI, React/Vite, SQLite, yt-dlp e FFmpeg**, com foco em uma execução leve no Debian Linux.

Acesse **http://localhost:8766**. O servidor escuta somente em `127.0.0.1` e deve permanecer aberto durante o uso.

## Funcionalidades

- Consulta de vídeos, playlists e Mixes sem baixar mídia, com limite inicial de 50 itens.
- Busca por título/canal, seleção individual ou dos resultados filtrados e cópia de URLs sem parâmetros de playlist.
- Importação opcional de texto, JSON e JSONL do yt-dlp, preservando o fluxo do protótipo.
- Fila de downloads MP3 com um item por vez, progresso real, conversão, cancelamento e remoção de pendentes.
- Histórico SQLite e identificação de arquivos concluídos para evitar downloads repetidos.
- Biblioteca local com busca, ordenação, agrupamento por artista, miniaturas e player para tocar/pausar, ajustar volume e avançar na faixa.
- Tags ID3 (título, artista, ano, ID do YouTube) e capa 500x500 gravadas dentro do MP3, para leitores como o do carro. O áudio não é recodificado.
- Reprodução mantida ao navegar entre as abas da aplicação, sem precisar de internet para ouvir MP3s locais.

Baixe somente conteúdos que você tem autorização para baixar. A licença do software não concede direitos sobre músicas, vídeos ou imagens de terceiros.

## Plataformas

| Plataforma | Situação |
| --- | --- |
| Debian Linux | Ambiente de desenvolvimento e validação atual. |
| Outras distribuições Linux | Podem exigir ajustes; ainda não validadas. |
| Windows | Versão em desenvolvimento, ainda sem distribuição suportada. |
| macOS | Versão em desenvolvimento, ainda sem distribuição suportada. |

**Estamos trabalhando em versões para Windows e macOS.** O planejamento inclui adaptar a instalação, os diretórios de músicas/dados e o cancelamento de processos. O código atual usa recursos POSIX, como `fcntl` e grupos de processos, além de scripts Bash; não há instaladores ou instruções de execução validadas nessas plataformas, nem previsão de lançamento.

## Requisitos no Debian

- Python **3.13**: versão usada para validar o conjunto de dependências fixadas.
- Pacote `python3-venv`.
- Node.js **22 ou superior** e npm: Node também é usado pelo yt-dlp durante o uso, além de compilar a interface.
- **FFmpeg e FFprobe** no `PATH`.
- Navegador atualizado. Os testes automatizados de interface foram realizados no Chromium; Firefox ainda requer validação manual.

Se necessário, instale os pacotes do sistema:

```bash
sudo apt install python3-venv ffmpeg
```

Verifique `python3 --version`, `node --version`, `npm --version`, `ffmpeg -version` e `ffprobe -version`. A versão do Node disponível no repositório da sua distribuição pode variar.

## Instalação e execução

Para obter uma nova cópia do projeto:

```bash
git clone https://github.com/harlemsilvas/seletor-musical.git
cd seletor-musical
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
npm --prefix frontend ci
npm --prefix frontend run build
./executar.sh
```

Se você já tem o projeto local, use a pasta que contém `executar.sh` em vez de clonar novamente.

Abra **http://localhost:8766** e deixe o terminal aberto. **Ctrl+C** encerra a aplicação. Para iniciar novamente, execute `./executar.sh` na mesma pasta.

O Python permanece isolado em `.venv`; não use `--break-system-packages`. O frontend compilado é servido pelo próprio backend, sem manter Vite rodando. Não há Docker ou inicialização automática na nova aplicação. Não inicie múltiplos workers: uma trava protege o histórico de duas instâncias simultâneas.

**Não execute `instalar.sh` para instalar esta versão.** Esse arquivo pertence ao protótipo antigo, usa a porta 8765 e configura um serviço automático. Veja [Referências e protótipo](#referências-e-protótipo).

Após alterar a interface, execute `npm --prefix frontend run build`. Após alterar o backend, reinicie o servidor. Se a porta 8766 estiver ocupada, identifique a instância existente antes de encerrar qualquer processo.

## Como usar

### Selecionar

1. Cole a URL de um vídeo, playlist ou Mix e clique em **Consultar músicas**.
2. Pesquise por título ou canal e marque as faixas desejadas.
3. Copie as URLs ou clique em **Baixar selecionadas em MP3**.

A consulta substitui a lista após sucesso; uma falha preserva a lista anterior. Seleções fora do filtro permanecem marcadas. Mixes são dinâmicos e podem diferir do que aparece no YouTube. Alguns metadados podem não estar disponíveis. Não há busca global do YouTube.

O máximo padrão é 50 itens por consulta. Para alterar o máximo permitido, entre 1 e 200:

```bash
SELETOR_MAX_ITEMS=75 ./executar.sh
```

A importação de arquivos é opcional: use **Ou importe JSONL / texto** para colar URLs, linhas `Nome | URL`, JSON/JSONL ou abrir um arquivo de até 5 MB. Listas com `entries` também são aceitas; duplicados e linhas inválidas são ignorados. Importar substitui a lista atual. A geração manual de JSONL não é necessária para consultar pela página.

### Downloads

Acompanhe o progresso e a conversão na aba **Downloads**. **Cancelar download** encerra o ativo e seus descendentes, inclusive FFmpeg; **Remover da fila** cancela um pendente. Arquivos concluídos são preservados e não são sobrescritos.

A fila aceita até 200 itens por envio e 500 ativos no total. Cada download tem limite de duas horas. A conversão aparece como uma fase separada, sem porcentagem inventada. Falhas não interrompem os itens seguintes.

Fechar a aba não encerra a fila enquanto o servidor estiver aberto. Ao reiniciar o servidor, itens que ficaram pendentes ou ativos aparecem como **Interrompido** e só voltam à fila por **Tentar novamente**.

### Biblioteca

Na aba **Biblioteca**, busque por título, canal ou artista, ordene e clique em **Tocar**. O player permanece ativo ao trocar de aba. Fechar a página ou encerrar o servidor interrompe o áudio.

Os arquivos novos são gravados como `titulo-sem-acentos_IDDOVIDEO.mp3`, sem espaços, acentos ou símbolos. Se um MP3 legível do vídeo já existir (inclusive no formato antigo `ID.mp3`), ele não é baixado de novo; somente arquivos danificados são substituídos. A verificação acontece na própria fila, um item por vez, sem travar o botão de baixar.

Para renomear MP3s antigos (`ID.mp3`) para o novo padrão, com o servidor parado: `.venv/bin/python -m backend.rename_legacy` mostra o plano e `--apply` executa. O nome anterior fica registrado no catálogo e nada é sobrescrito.

Downloads concluídos entram no catálogo em segundo plano. **Atualizar biblioteca** reconhece MP3s que já estejam diretamente em `~/Música/SeletorMusical`, mesmo sem histórico. Não varre subpastas, `.partial` ou links simbólicos. Não duplica, renomeia ou apaga músicas.

Metadados vêm do histórico, das tags do MP3 e do yt-dlp; o nome do arquivo é usado quando faltam informações.

**Artista e álbum.** Para vídeos oficiais o YouTube normalmente **não informa** artista, álbum nem data de lançamento. O artista é inferido do título no formato "Artista - Título" (ou, sem isso, do nome do canal) e a origem fica registrada; o álbum permanece vazio quando não existe. O ano gravado é o de lançamento, se houver, ou o do envio ao YouTube. Em "Artista" é possível ordenar e filtrar; nomes com vírgula ou "ft." usam o primeiro nome como artista principal, e "&" não divide (preserva "Years & Years").

**Enriquecer (uma faixa por vez).** Cada linha da Biblioteca tem o botão **Enriquecer** (ou **Atualizar dados**), que consulta o YouTube para aquela música, baixa miniatura e metadados e grava tags e capa dentro do MP3. Exige internet, não roda durante um download nem junto de outro enriquecimento e avisa se o YouTube pedir verificação anti-bot. O enriquecimento em lote existe no servidor (`/api/library/enrich`), mas está fora da interface até validarmos o uso individual. Novos downloads já saem com tags e capa. A regravação é verificada (duração e MD5 do áudio idênticos) e troca o arquivo de forma atômica; em qualquer falha o MP3 original é mantido. Arquivos ausentes ou inválidos ficam indisponíveis após atualizar a biblioteca. A análise usa FFprobe em segundo plano, com tempo limite e cache por tamanho/data do arquivo.

## Dados locais e privacidade

| Informação | Local |
| --- | --- |
| MP3s concluídos | `~/Música/SeletorMusical/ID_DO_VIDEO.mp3` |
| Temporários de download | `~/Música/SeletorMusical/.partial/` |
| Histórico e catálogo SQLite | `~/.local/share/seletor-musical/history.sqlite3` |
| Lista carregada | `localStorage` do navegador, por origem/perfil |

A tela de histórico mostra os 200 registros encerrados mais recentes; o banco completo é preservado. A biblioteca tem paginação de 50 faixas e entrega áudio por identificador cadastrado, sem aceitar caminhos arbitrários do navegador.

O projeto não implementa telemetria ou envio de estatísticas aos mantenedores. Consultas, downloads e miniaturas podem se conectar a serviços externos. Detalhes sobre armazenamento, rede, logs, cópia de segurança e exclusão estão em [PRIVACY.md](PRIVACY.md).

## Limitações e solução de problemas

- **Bloqueios do YouTube:** restrições anti-bot, idade, região ou vídeos privados podem impedir consultas e downloads. A janela de verificação permite abrir o YouTube e tentar novamente, mas confirmar no navegador não transfere a sessão ao yt-dlp. Não há suporte a login ou cookies; esperar não garante desbloqueio.
- **Runtime JavaScript:** o projeto usa `yt-dlp[default]` com EJS e habilita Node explicitamente. Consulte o [guia oficial do yt-dlp](https://github.com/yt-dlp/yt-dlp/wiki/EJS).
- **Dependências ausentes:** FFmpeg, FFprobe e Node são verificados antes de aceitar downloads; as falhas aparecem na interface.
- **Progresso:** tamanhos e tempos podem ser estimados; a tela atualiza a cada segundo e fases muito curtas podem não aparecer.
- **Queda abrupta:** podem sobrar temporários em `.partial`. Eles não fazem parte da biblioteca.
- **Área de transferência:** se a cópia automática for bloqueada, uma janela oferece o texto para copiar manualmente.

Para atualizar yt-dlp e os componentes junto às demais dependências permitidas pelo projeto:

```bash
.venv/bin/python -m pip install --upgrade -r requirements.txt
.venv/bin/python -m pip freeze > requirements.lock.txt
```

Execute os testes após atualizar dependências. O arquivo fixado registra o ambiente de referência e deve acompanhar a mudança.

## Desenvolvimento e testes

Leia [CONTRIBUTING.md](CONTRIBUTING.md) para preparar o ambiente, executar os testes e propor alterações. A validação anterior desta versão incluiu 21 testes de backend, testes JavaScript, build e testes no Chromium com áudio sintético local. Isso não garante disponibilidade futura do YouTube.

O download real autorizado encontrou bloqueio anti-bot; a geração de MP3 e o cancelamento foram validados também com mídia sintética local. Nenhum teste exige fornecer cookies ou credenciais.

## Próximos passos

- Fila de reprodução, próxima/anterior, sequência, embaralhar e repetir.
- Favoritos, playlists e organização pessoal.
- Adaptação e validação das versões para Windows e macOS.

O planejamento da biblioteca está em [PLANO-BIBLIOTECA.md](PLANO-BIBLIOTECA.md). As mudanças já entregues estão no [CHANGELOG.md](CHANGELOG.md).

## Documentos do projeto

- [Contribuição](CONTRIBUTING.md)
- [Privacidade](PRIVACY.md)
- [Segurança](SECURITY.md)
- [Código de conduta](CODE_OF_CONDUCT.md)
- [Licença MIT](LICENSE)
- [Dependências e referências de terceiros](THIRD_PARTY_NOTICES.md)

## Referências e protótipo

`web/`, `servidor.py`, `iniciar.sh`, `instalar.sh` e `LEIA-ME.md` foram preservados como referência do protótipo na porta 8765. As instruções desses arquivos não substituem as desta versão.

A referência funcional [dsymbol/yt-dlp-gui](https://github.com/dsymbol/yt-dlp-gui) foi consultada, incluindo sua [licença Unlicense](https://github.com/dsymbol/yt-dlp-gui/blob/main/LICENSE). Nenhum código foi copiado desse repositório e a interface PySide6 não foi incorporada. As dependências mantêm suas próprias licenças.
