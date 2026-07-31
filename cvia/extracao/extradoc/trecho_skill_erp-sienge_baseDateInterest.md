## Campos de data no Contrato de Vendas (Swagger `sales-contracts-v1.yaml`)

Consulta ao Swagger oficial (`https://api.sienge.com.br/docs/yaml-files/sales-contracts-v1.yaml`) confirma a existência e descrição dos seguintes campos:

### contractDate
- Descrição no Swagger: "Data do contrato" (formato YYYY-MM-DD)
- O Swagger não documenta nenhuma regra de origem para esse valor — a definição de qual data é enviada (data de criação da reserva, data de envio ao Sienge, ou "Data Contrato"/"Data de Contrato" configurada no CV) é **lógica interna do CV**, não está descrita na API do Sienge.
- Útil para confirmar o nome/formato do campo, mas não resolve dúvidas sobre prioridade entre "Data da Venda" (config. da integração) x data de criação x data de envio.

### Data Base de Juros (baseDateInterest)
Dentro do objeto de condição de pagamento (`PaymentConditionsInsert`), existem três campos de data distintos e independentes:

| Campo no Sienge | Descrição |
|---|---|
| `firstPayment` | Data do primeiro vencimento |
| `baseDate` | Data base |
| `baseDateInterest` | **Data base de juros** |

**Implicação para diagnóstico:** "Data Base de Juros" (`baseDateInterest`) é um campo enviado **por condição de pagamento/série da reserva**, não uma configuração global do empreendimento ou do formulário de integração. Por isso não aparece no Formulário de Configuração API SIENGE — é calculado/preenchido pelo CV a partir da condição de pagamento específica de cada reserva, podendo divergir do parâmetro genérico "data do primeiro vencimento" configurado no empreendimento.

Em chamados sobre divergência nesse campo: verificar a condição de pagamento (série) da reserva específica, não a configuração geral do empreendimento.
