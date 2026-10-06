RDO COM O VÍDEO DO CANAL

🔷ABRA O TERMINAL DO VSCODe
🔷CRIE AMBIENTE VIRTUAL: python -m venv .venv
🔷ATIVE AMBIENTE VIRTUAL: .venv/scripts/activate
🔷INSTALE AS BIBLIOTECAS COM O AMBIENTE VIRTUAL ATIVO: pip install -r requirements.txt
🔷rode o RUN.PY para usar (lembre-se de personalizar sua ia no brain.json na primeira vez)

🔴🔴🔴🔴Se der O ERRO DE TEXTO VERMELHO no terminal, faça o seguinte:🔴🔴🔴🔴

1 - VA NA PESQUISA DO SEU WINDOWS 🔴🔴🔴🔴
2 - ABRA O POWERSHELL NO MODO ADMINISTRADOR 🔴🔴🔴🔴
3 - COLE O CODIGO: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser 🔴🔴🔴🔴
4 - MARQUE "SIM PARA TODOS" (PRA NÃO FICAR TE BLOQUEANDO EM QUALQUER CÓDIGO), APÓS ISSO FECHE O POWERSHELL E VOLTE A ATIVAÇÃO NORMAL DO AMBIENTE VENV 🔴🔴🔴🔴


🧠🧠🧠🧠ARQUIVO BRAIN.JSON🧠🧠🧠🧠:

🧠 Guia Rápido: Como configurar a sua IA

⚠️ A ÚNICA REGRA: Altere APENAS o texto que está DENTRO das aspas (" ").
Se você apagar uma única aspa, vírgula (,) ou chave ({}), o arquivo quebra e nada funciona!

1. O Básico (Obrigatório)
"name": Apague "NOME DA SUA IA" e escreva o nome que quer dar a ela.

"relationship": Apague "SEU NOME" e coloque o seu nome ou apelido.

2. A Personalidade (Opcional, mas recomendado)
Reescreva as frases dentro das aspas destes campos para mudar a "vibe" dela:

"role": O que ela é pra você (Ex: "Assistente sarcástica" ou "Minha amiga virtual").

"traits": A lista de características dela (Ex: "Debochada", "Fofa", "Impaciente").

"behavior": Como ela trata VOCÊ (Ex: "Me trata como um rei" ou "Sempre duvida de mim").

"response_style": Regras de como ela fala (Ex: "Usa gírias", "Sempre responde curto").

"VOCABULARIO": adicione a quantidade que quiser lembrando de deixar alguma descrição sobre o significado da palavra, como no "lagado, nerfado e tiltar"
3. O Resto do Arquivo?
NÃO MEXA. Deixe coisas como conversation_memory, emotional_analysis e visual_context vazias ou do jeito que estão. O sistema vai preencher isso sozinho enquanto vocês conversam.

Salva o arquivo e pronto. Divirta-se!

===============================XX------------------------------------XX==============================================

## DISCORD (passo a passo)

Só precisas disto se quiseres a IA no Discord. Sem isto, tudo o resto
continua a funcionar exactamente igual.

### 1. Criar o bot
1. Abre https://discord.com/developers/applications e carrega em
   **Create New Application**. Dá um nome (ex: "Haimiya") e confirma.
2. No menu da esquerda, clica em **Bot** e depois em **Reset Token**.
3. Copia o token que aparece (só aparece uma vez) e cola-o no `.env`:
   ```
   DISCORD_TOKEN=o-colei-aqui
   ```
   Nunca partilhes esta linha. Quem tiver o token consegue falar como a
   tua IA.
4. Ainda em **Bot**, liga **MESSAGE CONTENT INTENT**, **SERVER MEMBERS
   INTENT** e **VOICE STATE INTENT**. As três são obrigatórias: sem elas o
   bot não lê o que se escreve, não sabe quem é o dono e não acompanha a
   call. O **PRESENCE INTENT** é opcional.

### 2. Convidar o bot
1. OAuth2 > **URL Generator**.
2. Em **Scopes**, marca **bot**.
3. Em **Bot Permissions**, marca no mínimo: *View Channels*, *Send
   Messages*, *Send Messages in Threads*, *Connect*, *Speak*, *Use Voice
   Activity*.
4. Copia o URL gerado e abre-o no navegador. Escolhe o servidor, autoriza,
   e confirma que o bot aparece na lista de membros.

### 3. Ligar
Corre o `run.py` e escolhe a **opção 4** do menu. Se o `.env` não tiver
o token, o programa avisa e segue em frente só com a IA local.

### 4. Na call
- `!entrar` — o bot entra na call onde estás (ou pede o `discord_voice_channel_id`).
- `!sair` — sai da call.
- `!parar` — cala a IA e limpa a fila (só dono/admin).
- `!fila` — mostra quem está à espera de resposta.
- `!papeis` — mostra o teu papel e o que esse papel pode pedir.

### Quem pode pedir o quê
- **dono / admin** — tudo: controlar o PC, ver o ecrã, música, Photoshop,
  ficheiros, e mandar a IA calar-se a meio de uma frase.
- **comum** — conversar, pedir música, imagens, pesquisa e ajuda de jogos.

Define os teus IDs em `Arcana/armazen/brain.json`:
```json
"dono_ids": ["123456789012345678"],
"admin_ids": ["987654321098765432"],
"admin_papeis": ["Moderação", "Admin", "Administrador", "Dono", "Owner"]
```
Quem for dono do servidor é sempre tratado como dono, mesmo sem estar na lista.

### Confirmação de coisas perigosas
Apagar ficheiros, formatar, instalar, e **abrir ou fechar programas**
ficam à espera de um "sim" teu — do próprio dono também, porque o Whisper
por vezes inventa palavras. Se disseres outra coisa que não seja sim ou
não, a pergunta fica à espera.

### Ajustes
No `brain.json`, sempre com o prefixo `discord_`:
`discord_texto_livre` (responder sem menção — `true` por omissão),
`discord_menções`, `discord_dm_active`, `discord_server_active`,
`discord_disabled_guilds`, `discord_voice`, `discord_queue_max`.

⚠️ O bot **não se ouve a si próprio**: o `edge-tts` escreve para a call, e
a transcrição ignora o áudio do próprio bot.

===============================XX------------------------------------XX==============================================


SISTEMA DE OVERLAY ```
// OVERLAY SYSTEM v1.0
// Criado por: Exorcys
// Otimizado por: Christopher  
// Masterizado por: Nero
```