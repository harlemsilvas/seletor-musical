# Histórico de mudanças

Alterações ainda não associadas a uma versão publicada são registradas em **Não lançado**. A versão `0.1.0` no pacote do frontend é metadado de desenvolvimento, não uma declaração de release público.

## Não lançado

### Funcionalidades entregues

- Consulta de metadados com yt-dlp, importação de listas, filtro, seleção e cópia de URLs.
- Fila serial de MP3s com FFmpeg, progresso, cancelamento e histórico SQLite.
- Janela de orientação para verificação do YouTube, sem transferência de sessão ou cookies.
- Biblioteca local, indexação de MP3s, streaming por ID e player persistente entre abas.
- Testes de backend e navegador com mídia sintética local.

### Melhorias recentes

- Metadados do YouTube: artista inferido (origem registrada), ano, miniatura e capa; tags ID3v2.3 e capa 500x500 gravadas no MP3 em novos downloads, com verificação do áudio por MD5.
- Biblioteca: ordenar/filtrar/agrupar por artista, miniaturas e botão Enriquecer por faixa (`POST /api/library/{id}/enrich`). O lote (fila serial, cancelável, com parada em bloqueio anti-bot) fica no backend, sem botão na interface por ora.
- Endpoint de capa por ID de faixa; pasta de capas em dados do app.

- Nomes de arquivo ASCII (`titulo_ID.mp3`) e verificação de MP3 legível com ffprobe: não rebaixa o que já existe; substitui apenas arquivos danificados.
- `executar.sh` encerra instância anterior da própria aplicação antes de iniciar e recusa a porta 8766 se ocupada por outro programa.
- Catálogo guarda título original e nome de arquivo anterior; ferramenta `backend.rename_legacy` renomeia MP3s antigos em lote (simulação por padrão).
- Verificação de MP3 existente movida para a fila serial; itens já catalogados e inalterados são ignorados na hora.
- Migrações versionadas do SQLite em um único módulo.
- Varredura da biblioteca com uma conexão e sem gravações desnecessárias; consulta de downloads mais espaçada quando ociosa ou com a aba oculta.

### Documentação e repositório

- Revisão do README com instalação, uso, dados locais, limitações e estado das plataformas.
- Licença MIT e documentos de privacidade, contribuição, segurança e conduta.
- Avisos de terceiros, modelos de issues/pull requests e convenções de edição.
- Registro do desenvolvimento das versões para Windows e macOS, sem lançamento ou suporte validado nessas plataformas.

### Limitações conhecidas

- Bloqueios anti-bot do YouTube podem impedir consultas e downloads.
- Firefox, Windows e macOS ainda precisam de validação específica.
- Fila de reprodução, favoritos e playlists locais permanecem no planejamento.
