# Backlog

## Attack-defense tree for the report

- [ ] Complete the architecture's attack-defense tree when preparing the report

Deferred on 2026-11-12. Continue the Prometheus integration before returning to this task.

Use the initial tree discussed in the project chat as a starting point. Model a remote attacker against the final architecture, expand the forged-reading and availability branches, and distinguish existing controls from proposed defenses. Connect each scenario to monitoring signals and collected experimental evidence.



- [ ] Retirar do k3s-master o pod do analytics, e deixar meramente o control plane – acho que é uma divisão de responsabilidades melhor do a que temos atualmente


# DoS

- [ ] Para a questão do rate limiting acho que é pertinente não usar necessariamente o IP como única identidade, porque vários sensores legítimos podem partilhar IP através de NAT. Mas como os distinguiríamos? Não sei
  - Adicionar NGINX a um mesmo POD com o Ingestion, e fazer o Ingestion ouvir apenas o 127.0.0.1
- [ ] Deteção através do prometheus. Podemos calcular a taxa global de pedidos (`sum(rate(ingestion_requests_total[1m]))`) e latência p95, ou seja, o tempo avaixo do qual terminam aproximadamente 95% dos pedidos, e combinando estas 2 métricas com a CPU Usage, memória e erros HTTP 5xx, conseguimos perceber se o pedido dos aumentos está efetivamente a degradar o serviço
- [ ] Caching? Guardar uma resposta do `GET /average` para evitar consultas repetidas? Mas como é que faríamos para saber quando é que a cache está dirty?