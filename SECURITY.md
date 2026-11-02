# Segurança

## Escopo e suporte

A versão em desenvolvimento é uma aplicação local, acessível em `127.0.0.1:8766`. Não há promessa de operação segura como serviço público, multiusuário ou exposto à internet. Não existe ainda uma política de manutenção de versões antigas; correções são destinadas à versão atual em desenvolvimento.

Windows e macOS ainda não foram validados. O protótipo da porta 8765 é mantido como referência e não recebe a mesma cobertura funcional da aplicação atual.

## Relatar uma vulnerabilidade

Não publique detalhes de exploração, dados pessoais, bancos, cookies ou credenciais em uma issue pública.

Se o projeto estiver no GitHub e o recurso **Report a vulnerability** estiver habilitado na aba **Security**, use esse canal privado. Nenhum e-mail de segurança ou outro contato privado oficial foi definido neste repositório até o momento. Se não houver canal privado disponível, abra apenas uma solicitação genérica de contato privado, sem detalhes técnicos sensíveis, e aguarde a indicação de um canal pelo mantenedor.

Em um relato privado, informe versão/revisão, sistema operacional, passos mínimos para reprodução, impacto e uma demonstração sem dados pessoais. Use áudio sintético e arquivos temporários quando possível. Não há prazo garantido de resposta ou programa de recompensa.

## Áreas de atenção

- Origem das requisições e validação de URLs.
- Comandos de subprocessos e cancelamento de descendentes.
- Acesso a arquivos fora da pasta autorizada e links simbólicos.
- Proteção de MP3s concluídos e integridade de migrações SQLite.
- Vazamento de credenciais, caminhos pessoais ou dados de navegação em logs.
- Dependências desatualizadas.

O projeto não precisa de cookies ou credenciais para executar seus testes. Não habilite acesso ao navegador para diagnosticar uma vulnerabilidade sem um escopo explícito. Consulte também [PRIVACY.md](PRIVACY.md).
