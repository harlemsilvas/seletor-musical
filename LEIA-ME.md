# Minha seleção musical — Debian / Linux

Página local para importar listas do yt-dlp, pesquisar músicas e copiar suas URLs.
Não baixa músicas nem extrai uma playlist diretamente pelo navegador.

## Instalação

Extraia o ZIP e, no terminal dentro da pasta minhas-musicas, execute:

    bash instalar.sh

Não use sudo. Requer Python 3, já disponível no seu Debian.
Não exige pip, ambiente virtual, Docker ou Node.js.
Instala em ~/.local/share/minhas-musicas e configura um serviço systemd do usuário.
O serviço inicia agora e automaticamente ao entrar na sua sessão Linux.
Se systemd do usuário não estiver disponível, o instalador informa como iniciar manualmente.

Acesse e salve nos favoritos:

    http://localhost:8765

O endereço funciona enquanto o serviço e o computador estiverem ligados.
O servidor aceita conexões somente do próprio computador (127.0.0.1).

## Sem instalar

Na pasta extraída:

    bash iniciar.sh

Deixe esse terminal aberto. Acesse http://localhost:8765. Ctrl+C encerra.
Não execute o modo manual enquanto o serviço instalado estiver em execução.

## Lista de músicas

Com seu ambiente virtual do yt-dlp ativo, gere o arquivo:

    python -m yt_dlp --ignore-config --yes-playlist --flat-playlist --skip-download --playlist-end 50 --dump-json "https://youtu.be/D0_GWTy9FEM?list=RDD0_GWTy9FEM" > ~/musicas.jsonl

Na página, clique em Abrir arquivo e selecione musicas.jsonl.
Você também pode colar URLs ou linhas no formato Nome | URL.
Uma lista somente com URLs não contém os nomes: gere JSON para trazer os títulos.
O botão Copiar URL copia o link individual sem parâmetros de playlist.
A consulta do YouTube, a reprodução e os downloads exigem internet.
A página e a lista importada podem ser consultadas offline.
Mixes são dinâmicos e podem diferir da lista exibida no navegador.

A seleção é armazenada no navegador, por endereço e perfil. A lista salva na
versão hospedada não é transferida automaticamente para localhost: importe novamente.
Limpar dados do navegador apaga a seleção; guarde o arquivo JSONL como cópia.
Se a cópia automática for bloqueada pelo navegador, será mostrado o texto para copiar.

## Gerenciar serviço

    systemctl --user status minhas-musicas.service
    systemctl --user stop minhas-musicas.service
    systemctl --user start minhas-musicas.service
    journalctl --user -u minhas-musicas.service -n 30

Para desativar a inicialização automática:

    systemctl --user disable --now minhas-musicas.service

Para remover, depois de desativar:

    rm ~/.config/systemd/user/minhas-musicas.service
    systemctl --user daemon-reload

Os arquivos do aplicativo ficam em ~/.local/share/minhas-musicas; você pode
excluir essa pasta pelo gerenciador de arquivos quando não precisar mais dela.

## Porta ocupada

Se aparecer erro de porta 8765 em uso, verifique se o serviço já está ativo.
Não encerre outros programas sem identificá-los.
