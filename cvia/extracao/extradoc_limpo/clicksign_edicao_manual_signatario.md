# Clicksign: assinatura não atualiza no CV após edição manual de signatário no painel

## Sintoma

O cliente reporta que eventos de assinatura (`Event::Sign`) da Clicksign voltam com erro HTTP 400 no endpoint do CV e a assinatura não atualiza no sistema.

## O que verificar antes de suspeitar de bug

Confira a configuração da integração:

- Integração ativa, em produção, com a chave de acesso válida.
- Webhook habilitado, apontando para `/api/v1/cv/clicksign-webhook`, com o segredo HMAC preenchido e o evento `sign` marcado.
- Verifique o log de envios: se parte dos eventos volta 200 e parte volta 400, já dá para descartar problema de chave, URL, segredo ou configuração — a falha está isolada a um tipo específico de situação, não à integração como um todo.

## Causa mais comum: edição manual de signatários no painel da Clicksign

Quando um contrato é enviado pelo CV, o CV cadastra os signatários com um vínculo interno que liga cada um deles à reserva. Se alguém entra no painel da Clicksign **depois** desse envio e edita/troca os signatários manualmente (remove os que o CV cadastrou e adiciona novos direto no painel), os novos signatários não têm esse vínculo com a reserva.

Quando a Clicksign avisa que essas pessoas assinaram, o CV recebe o evento, procura o registro correspondente pelo vínculo interno, não encontra e responde com erro 400. Assinantes que foram cadastrados pelo CV e assinaram antes da troca reconciliam normalmente — é por isso que o log mostra uma mistura de 200 e 400 para o mesmo documento.

Como o CV responde com erro, a Clicksign reenvia o mesmo aviso várias vezes (retentativa), então o log tende a acumular vários 400 repetidos com as mesmas chaves de documento — não são assinaturas novas, são retentativas do mesmo evento.

Outro sinal frequente: o documento aparece como fechado manualmente no histórico da Clicksign, em vez de finalizado automaticamente pelo fluxo padrão.

## Por que isso não é um erro do sistema

Editar ou trocar signatários no painel da Clicksign depois que o contrato já foi enviado pelo CV sempre rompe a conexão entre os dois. O retorno 400 é o comportamento esperado quando chega uma assinatura de alguém que o CV nunca cadastrou.

## Orientação ao cliente

1. Não alterar signatários nem o documento diretamente no painel da Clicksign depois do envio pelo CV. Qualquer ajuste de assinante deve ser feito cancelando o envelope e reenviando pela plataforma (CV), não editando no painel da Clicksign.
2. Para contratos que já ficaram com esse problema, cancelar e reenviar pelo CV para refazer o vínculo — só assim a assinatura volta a atualizar sozinha.

## Como confirmar a causa num caso específico

- No histórico do documento na Clicksign, procure uma ação de edição/troca de signatário feita por um usuário do painel, entre a data de envio original e a data das falhas.
- Compare os signatários que geraram 400 com os que estavam no envio original do CV: se forem diferentes (e-mails diferentes dos cadastrados pelo CV), a causa é a edição manual.
- Confirme se o documento foi fechado manualmente (e não pela finalização automática) — reforça o diagnóstico.
