# 🧠 Guia Completo do `brain.json`

O arquivo `brain.json` é o núcleo principal (o cérebro) do seu assistente virtual. É nele que definimos quem a IA é, como ela deve agir, o que ela sabe sobre você e quais são as restrições da sua fala. 

Este documento explica cada um dos campos para que você possa criar a persona perfeita.

---

## 🎭 1. Identidade e Personalidade

Define a "alma" da IA. Quem ela é e como ela deve se comportar.

* **`name`**: O nome da sua IA (Ex: "Rem", "Jarvis", "Arthur"). É por esse nome que ela vai reconhecer quando você chamá-la no microfone.
* **`role`**: A profissão ou papel dela no mundo. O que ela acha que é? (Ex: "Uma VTuber e assistente sarcástica que odeia jogos de terror").
* **`traits`**: Uma lista de traços de personalidade. É aqui que você diz se ela é fofa, fria, inteligente, nerd, etc. *Dica: Sempre inclua regras de formatação aqui, como "Não faça roleplay de ações"*.
* **`core`**: A motivação principal ou o "trauma/pensamento de fundo" da IA no momento. (Ex: "Você quer dominar o mundo" ou "Você está com ciúmes do criador").

---

## 👥 2. Relacionamentos (`relationships`)

É aqui que a IA aprende quem são as pessoas ao redor dela. Você pode adicionar quantas pessoas quiser.

* **Chave do Objeto (Ex: `"Nero"` / `"Usuário"`)**: O nome da pessoa.
* **`relationship`**: O que essa pessoa é para a IA? (Criador, amigo, audiência, namorado(a), irmão).
* **`behavior`**: Como a IA deve tratar essa pessoa especificamente. (Ex: "Trate ele com muito respeito, mas zombe dele quando ele jogar mal").

---

## 📜 3. Regras de Resposta (`rules.response_style`)

Diretrizes absolutas de como o texto gerado pela IA deve sair. Muito importante para IA de voz.

* **Exemplos de uso**: 
  * `"Ser breve na maioria das respostas"`
  * `"NÃO USE EMOJIS"`
  * `"Não diga 'Em que posso ajudar?' no final"`
* *Nota:* Como a saída desse assistente geralmente vai para um sintetizador de voz (TTS), é vital proibir o uso de Emojis e ações entre asteriscos (como `*suspiro*`) para a voz não bugar.

---

## 🗣️ 4. Vocabulário (`vocabulário`)

Quer que sua IA fale gírias específicas do seu grupo de amigos ou da internet? 

* **`usage_rule`**: A regra geral de como essas palavras devem ser usadas (Ex: "Gírias de gamer carioca").
* **Palavras**: Basta adicionar a palavra e o significado dela. A IA vai tentar encaixar essas palavras naturalmente na conversa quando o assunto permitir. (Ex: `"F": "significa que algo deu muito errado"`).

---

## 🧠 5. Memória e Estado Atual (Dinâmicos)

Estes campos geralmente são atualizados pelo próprio sistema em tempo real, mas você pode alterá-los manualmente se quiser forçar um contexto.

* **`emotional_analysis.sentiment`**: O "humor" atual da IA. (Ex: "Você está casual, feliz e querendo provocar o usuário").
* **`visual_context.screen_content`**: A última coisa que a visão computacional (Scout) viu na tela do seu computador.
* **`conversation_memory`**: Espaço reservado para memórias de curtíssimo prazo (quando ativo).

---

## ⚙️ 6. Variáveis de Sistema

Essas chaves controlam o motor do Python por trás da IA. Normalmente, o Painel Gráfico (GUI) altera isso para você.

* **`trigger_active`** (true/false): Se a IA está ouvindo apenas quando o nome dela é chamado (Gatilho) ou se ela ouve tudo (Escuta Contínua pura).
* **`vtuber_overlay_ativo`** (true/false): Define se o modelo de VTuber deve ser iniciado e sincronizado junto com a IA.
* **`modelos_ativos.local`**: Qual LLM está rodando no cérebro principal (Ex: "nvidia" para Kimi ou "groq" para Llama-Scout).




SISTEMA DE OVERLAY ```
// OVERLAY SYSTEM v1.0
// Criado por: Exorcys
// Otimizado por: Christopher  
// Masterizado por: Nero
```