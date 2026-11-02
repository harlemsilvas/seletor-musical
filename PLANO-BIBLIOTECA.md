# Etapa 3 — Biblioteca local e player

Status: etapa 3A implementada. Etapas 3B e 3C continuam como planejamento.

## Objetivo e experiência

Adicionar as abas Selecionar, Downloads e Biblioteca, mantendo um player fixo na parte inferior. O usuário consulta e seleciona vídeos, baixa os autorizados e encontra os MP3s concluídos na Biblioteca. Ao tocar uma faixa, pode navegar entre abas sem interromper o áudio.

A reprodução funciona sem internet, com o servidor local aberto. Fechar a aba ou encerrar o servidor interrompe a reprodução. Downloads continuam seguindo as regras atuais. O bloqueio anti-bot e a janela de verificação permanecem como estão; uma política de espera será considerada em trabalho separado, sem prometer desbloqueio por tempo decorrido.

## Solução leve

- Reutilizar FastAPI, React/Vite, SQLite, FFprobe e a pasta ~/Música/SeletorMusical.
- Usar um único elemento HTML audio persistente, controlado pelo React, com preload de metadados. Não criar um player para cada linha nem carregar todos os MP3s na memória.
- Servir áudio por identificador cadastrado na biblioteca. FileResponse da versão instalada do Starlette suporta Range, permitindo avançar/retroceder sem transferir o arquivo inteiro de novo. Validar respostas 206/416 e HEAD.
- Manter MP3s no local atual e com os nomes existentes; biblioteca é catálogo, não cópia adicional dos arquivos.
- Reproduzir o MP3 pronto, sem executar yt-dlp ou converter novamente durante a reprodução.
- Nenhum serviço adicional, Docker ou dependência pesada de player.

## Catálogo e metadados

Criar uma tabela library_tracks no SQLite atual, com migração versionada e preservação do histórico. Uma faixa é independente das várias tentativas de download do mesmo vídeo; não derivar a biblioteca apenas dos 200 registros exibidos pela tela de histórico.

Campos iniciais: identificador interno, video_id opcional, nome relativo do arquivo, título, canal, artista/álbum opcionais, duração, tamanho, data de inclusão, data de modificação e disponibilidade do arquivo. Metadados ausentes ficam vazios; canal do YouTube não deve ser identificado automaticamente como artista.

Transmitir os metadados disponíveis da seleção ao backend e complementar com metadados reais do yt-dlp/FFprobe. O título passado pelo frontend serve como referência, não como nome de arquivo nem caminho. Capas locais ficam para uma etapa posterior, com placeholder na primeira entrega.

Após a publicação bem-sucedida do MP3, registrar/atualizar a faixa no catálogo. Uma falha do catálogo não pode apagar o MP3 nem marcar a conversão como fracassada; uma sincronização posterior repara a entrada. Reconciliar também downloads publicados antes de um encerramento abrupto.

## Entregas funcionais

### 3A — Biblioteca mínima e reprodução de uma faixa

- Listar MP3s concluídos, pesquisar por título/canal e ordenar por nome ou inclusão.
- Adicionar novas faixas à biblioteca após conclusão do download, sem iniciar reprodução automaticamente.
- Botão Atualizar biblioteca: reconciliar a pasta fixa de downloads e o histórico completo, sem duplicar entradas. Ignorar .partial e arquivos incompletos.
- Para MP3s antigos encontrados nessa pasta sem histórico, usar tags quando disponíveis e nome do arquivo como fallback. Não consultar o YouTube para simplesmente catalogar ou tocar arquivos.
- Executar leitura de metadados em segundo plano, com uma verificação por vez, cache por tamanho/data e limite de tempo do FFprobe.
- Player fixo com título, tocar/pausar, posição/duração, barra para avançar e volume.
- Detectar arquivo ausente ou inválido, informar a falha e manter as demais faixas utilizáveis.

Aceite: tocar e avançar em um MP3 local com a internet desconectada, trocar de aba sem interromper o áudio e ver uma nova faixa concluída aparecer na biblioteca. Usar áudio sintético para validar sem depender do desbloqueio do YouTube.

### 3B — Fila de reprodução

- Ações Tocar agora e Adicionar à fila.
- Próxima/anterior, sequência automática ao terminar e remoção de faixas da fila de reprodução.
- Embaralhar e repetir, com tratamento de fila vazia e faixa única.
- Manter a fila de reprodução separada da fila de downloads, com nomes claros na interface.
- Salvar volume, fila e posição no navegador. Ao reabrir, restaurar o estado pausado e iniciar apenas após interação do usuário.
- Tratar erro de reprodução e bloqueio de autoplay sem travar os controles; não repetir indefinidamente uma faixa inválida.

Aceite: sequência de três áudios locais, troca de faixa, remoção da faixa atual, repetição e restauração após recarregar a página.

### 3C — Organização pessoal

- Favoritos e playlists locais salvos no SQLite.
- Editar nome de exibição, artista e álbum sem renomear ou regravar o MP3.
- Capas armazenadas localmente quando disponíveis; falhas de capa não impedem reprodução.
- Avaliar teclas de mídia/Media Session conforme suporte do navegador.

Excluir arquivos físicos e importar pastas externas ficam fora destas entregas iniciais. Se forem solicitados depois, terão fluxo próprio, com escolha explícita e proteção dos arquivos.

## API proposta

- GET /api/library: lista paginada, busca e ordenação.
- POST /api/library/sync: inicia reconciliação da pasta fixa, com proteção de origem e acompanhamento do estado.
- GET /api/library/{track_id}/audio e HEAD: entrega de um MP3 cadastrado, com suporte a Range.
- Depois: endpoints de favoritos e playlists.

O navegador nunca envia um caminho para tocar arquivos. O backend busca pelo ID e verifica que o arquivo resolvido permanece dentro da pasta autorizada, inclusive diante de links simbólicos. Não montar a pasta inteira como diretório público. Manter Host, origens locais e proteção contra requisições de outras origens; servir áudio apenas para a interface local. Tornar media-src 'self' explícito na política CSP.

## Validação

- Migração do banco existente sem perda de histórico; catálogo idempotente e sem duplicação de mídia.
- Concluídos entram na biblioteca; pendentes, cancelados e .partial não entram.
- Recuperação de arquivo publicado sem catálogo e detecção de MP3 removido externamente.
- Bloqueio de IDs inválidos, tentativas de travessia de diretório e links simbólicos para fora da pasta.
- Range parcial, Range inválido, HEAD, MIME audio/mpeg e ausência de arquivo.
- Player no Chromium e Firefox: tocar/pausar, seek, volume, fim da faixa, erro, navegação entre abas e largura de tela pequena.
- Biblioteca maior: paginação e indexação sem bloquear downloads ou consultas, sem sondar todos os arquivos a cada segundo.
- Teste offline com servidor local em execução. Nenhum novo download real necessário para validar o player.

## Referências

- Elemento audio e controles nativos: https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/audio
- FileResponse e Range: https://www.starlette.io/responses/#fileresponse (suporte também confirmado no código da versão instalada).

Entrega atual: 3A. Validar o uso antes de seguir para 3B e 3C.
