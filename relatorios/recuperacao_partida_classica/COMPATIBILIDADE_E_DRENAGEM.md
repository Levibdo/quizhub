# Recuperação do Quiz Clássico — compatibilidade e drenagem

## Identidade de partidas convidadas

Partidas convidadas novas recebem uma identidade aleatória criada pelo backend e
armazenada em cookie JWT assinado, `HttpOnly`, `SameSite=Lax` e `Secure` em
produção. O UUID presente na rota e no armazenamento local identifica a partida,
mas não autentica o jogador.

O logout da conta autenticada não remove esse cookie. Essa persistência é
intencional: a identidade pertence ao perfil local do navegador e permite fechar
e reabrir a aba durante uma partida convidada. Em equipamento compartilhado, o
operador deve encerrar a sessão do navegador ou limpar os dados do site para
remover também essa identidade. Uma ação adicional na interface não é necessária
para a correção de F5 e fica fora deste escopo.

## Limitação histórica

Partidas convidadas criadas antes desta correção possuem, quando informado, um
`visitante_id` gerado pelo frontend. Elas não possuem o cookie assinado novo. Esse
UUID legado não será aceito como credencial e nenhum vínculo será inferido ou
preenchido retroativamente. Consequentemente, uma partida convidada em andamento
no instante da troca do backend não poderá responder, avançar ou ser recuperada.

Partidas históricas permanecem preservadas para ranking e auditoria. Partidas de
usuários autenticados continuam recuperáveis pelo `usuario_id` proprietário.

## Plano de drenagem para implantação futura

1. Antes da janela, consultar em modo somente leitura partidas clássicas com
   `status = 'EM_ANDAMENTO'`, distinguindo jogadores autenticados daqueles com
   `usuario_id IS NULL`.
2. Não iniciar a troca enquanto existir atividade convidada recente. Considerar
   como janela mínima o tempo máximo normal de dez perguntas, acrescido de margem
   operacional definida pelo responsável pela implantação.
3. Publicar aviso de manutenção e bloquear a criação de novas partidas antes da
   parada do backend.
4. Repetir a consulta. Prosseguir somente quando não houver partida convidada
   ativa recente, ou mediante decisão humana explícita que aceite a interrupção.
5. Não alterar status, visitante, respostas ou prazos para forçar a drenagem.
6. Após a troca, validar uma partida convidada sintética: criação, cookie seguro,
   resposta, avanço e recuperação por F5.

### Critérios de interrupção

- criação de nova partida depois do início da manutenção;
- partida convidada com resposta recente;
- divergência entre contagens antes e depois da troca;
- ausência do cookie assinado na criação sintética;
- falha de propriedade, origem confiável ou recuperação.
