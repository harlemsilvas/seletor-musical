# Privacidade

Última revisão: 2 de novembro de 2026.

Este documento descreve a aplicação local atual do Seletor Musical. Não é uma descrição de serviço hospedado ou de versões futuras para outras plataformas.

## Dados mantidos no computador

- **Navegador:** a lista carregada é salva no `localStorage`, por origem e perfil. Pode conter títulos, canais, URLs, duração e endereço de miniaturas. A seleção das caixas e a reprodução atual ficam em memória.
- **SQLite:** `~/.local/share/seletor-musical/history.sqlite3` guarda histórico de downloads, URLs/identificadores, títulos, canais, estados, progresso, horários e catálogo dos arquivos locais. O catálogo inclui nome do arquivo, tamanho, data de modificação, duração e tags disponíveis, como artista e álbum.
- **Mídia:** os MP3s ficam em `~/Música/SeletorMusical`. Temporários ficam em `.partial` nessa pasta. O nome de exibição no catálogo pode ser diferente do nome físico do arquivo.
- **Terminal:** o servidor escreve mensagens de diagnóstico e falhas. O código evita registrar cookies, credenciais e saída bruta do yt-dlp. Tracebacks podem revelar caminhos e outros detalhes do ambiente; revise qualquer log antes de compartilhá-lo.

Não há envio implementado de telemetria, estatísticas de uso ou catálogo aos mantenedores. Os dados locais não recebem criptografia própria do aplicativo; sua proteção também depende das permissões e da segurança do computador.

## Conexões externas

- Consultas e downloads fazem requisições ao YouTube e à infraestrutura utilizada pelo yt-dlp para obter metadados e mídia. Esses serviços recebem os dados usuais de conexão, como IP e requisição do vídeo/lista.
- Miniaturas podem ser carregadas de servidores externos, inclusive ao restaurar uma lista salva no navegador. Por isso, abrir a interface com uma lista já salva pode gerar conexões para imagens.
- **Abrir no YouTube** e outros links externos abrem o serviço no navegador. Se você já estiver conectado nesse navegador, o serviço poderá usar a sessão existente segundo suas próprias regras. A aplicação local não importa essa sessão para o yt-dlp.
- A instalação e a atualização de dependências contatam os respectivos repositórios de pacotes.

O aplicativo não controla as práticas de privacidade desses serviços. A reprodução de MP3s locais usa o servidor no próprio computador e não precisa consultar o YouTube. O carregamento de miniaturas em outras partes da interface ainda pode usar internet.

## Cookies, conta e área de transferência

A versão atual não oferece login nem leitura/exportação de cookies do navegador. Não compartilhe cookies, senhas ou tokens em issues, logs ou pull requests.

Os botões de cópia escrevem as URLs escolhidas na área de transferência após sua ação. A aplicação não implementa leitura automática do conteúdo da área de transferência. Se a cópia for bloqueada, oferece texto para cópia manual.

## Acesso local

O servidor inicia em `127.0.0.1:8766`, com validação de Host/Origin e proteção das ações. Os arquivos de áudio são entregues por identificador do catálogo; a pasta inteira não é exposta como diretório público. Essas medidas não substituem a proteção do sistema operacional contra outros usuários ou programas locais. Não exponha o servidor à rede alterando a configuração de escuta sem revisar o modelo de segurança.

## Cópia de segurança e exclusão

Encerre o servidor antes de copiar ou remover o SQLite. Para preservar sua biblioteca, faça cópia do banco e dos MP3s. A lista do navegador é separada; guarde também os arquivos de importação que desejar manter.

- Limpar a lista ou os dados do site no navegador remove os dados locais correspondentes do navegador; não apaga os MP3s ou o SQLite.
- Remover o SQLite apaga histórico e catálogo armazenados nele. Ao iniciar novamente, a aplicação pode recriar o catálogo a partir dos MP3s da pasta, mas isso não restaura o histórico anterior.
- Para remover músicas, exclua os arquivos desejados pelo gerenciador de arquivos. Atualize a biblioteca depois. O player e o histórico não têm uma ação de exclusão física em massa.
- Após encerramento abrupto, podem restar temporários em `.partial`. Verifique que não há download ativo antes de limpar essa pasta.

Não anexe o banco, a pasta de músicas ou seu perfil do navegador para relatar problemas. Compartilhe apenas exemplos mínimos e informações revisadas. Para questões sensíveis, siga [SECURITY.md](SECURITY.md).
