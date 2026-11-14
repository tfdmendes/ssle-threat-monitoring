# Ativar e testar a ingestion no Wazuh, a partir da Kali

Os ficheiros estão em `/home/tfdmendes/ssle-threat-monitoring`. **Tu executas
os comandos deste guia.** A preparação dos ficheiros não instalou agentes,
não aplicou regras nem alterou a aplicação em execução.

Vamos verificar este percurso:

```text
POST /ingest -> JSON no stdout -> log CRI no nó K3s -> agente Wazuh
            -> decoder -> regras -> alerts.json -> Filebeat -> indexer -> dashboard
```

O decoder extrai os campos do JSON. A regra `100201`, de nível 3, identifica uma
rejeição. A regra `100202`, de nível 10, identifica dez rejeições da mesma origem
em 30 segundos, por agente. Não vamos ativar bloqueio automático neste ensaio.

## 1. Confirmar os serviços e preparar a sessão

Executa na **Kali**, com o utilizador `tfdmendes`, e mantém este terminal aberto.
As variáveis `project`, `image` e `backup` são reutilizadas nos passos seguintes.

```bash
# Use Bash for all commands in this guide
bash

# Select the source directory and the new image tag
project=/home/tfdmendes/ssle-threat-monitoring
image=ssle-ingestion:wazuh-f2a0194b4dd5
cd "$project"

# Check the lab containers, application pods and existing agents
incus list --columns=n,s,4 --format=csv
incus exec k3s-master -- k3s kubectl --namespace ssle get pods,services --output=wide
incus exec wazuh-container -- /var/ossec/bin/agent_control -l
incus exec wazuh-container -- dpkg-query -W wazuh-manager
```

Na preparação, os nós eram `k3s-master` e `k3s-node1`. O manager era
`wazuh-container`, em `10.255.255.40`, com versão `4.14.10-1`. Só o agente do
Apache estava registado. Confirma diferenças antes de instalar ou substituir
configurações. `incus exec` executa o comando depois de `--` dentro do contentor.
`--namespace ssle` limita a operação ao nosso namespace Kubernetes.

## 2. Guardar o estado anterior

Este passo cria um backup do Deployment na Kali e guarda os nossos ficheiros
de regras no próprio manager, se já existirem. Não exporta chaves nem certificados.
Executa uma vez antes da primeira ativação, para não substituir o backup inicial.

```bash
# Restrict access to files created by this shell
umask 077
backup=/home/tfdmendes/ssle-monitoring-backups/wazuh-ingestion-$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$backup"

# Save the current ingestion deployment for recovery
incus exec k3s-master -- k3s kubectl --namespace ssle get deployment ssle-ingestion --output=yaml > "$backup/ingestion-deployment.yaml"
printf '%s\n' "$backup" > /home/tfdmendes/ssle-monitoring-backups/latest-wazuh-ingestion.txt

# Preserve previous versions of our two manager files, if present
incus exec wazuh-container -- sh -c '
  mkdir -p /root/ssle-ingestion-before
  for kind in decoders rules; do
    file="/var/ossec/etc/$kind/ssle_ingestion.xml"
    if [ -e "$file" ]; then
      cp --preserve=mode,ownership,timestamps "$file" "/root/ssle-ingestion-before/$kind-ssle_ingestion.xml"
    fi
  done
'

# Keep this path for the recovery procedure
printf 'Backup: %s\n' "$backup"
```

`umask 077` restringe o acesso aos novos ficheiros ao teu utilizador.
`--output=yaml` guarda o estado do Deployment. A recuperação está no passo 10.

## 3. Descarregar e verificar o agente

Vamos instalar o **wazuh-agent 4.14.10-1 ARM64** nos dois nós. O agente acompanha
os logs do nó e envia-os ao manager. Precisamos dele nos dois nós porque o pod
pode ser colocado em qualquer um deles. A versão coincide com a do manager.

```bash
# Download the official package and the published SHA-512 checksum
mkdir -p /tmp/ssle-wazuh-install
cd /tmp/ssle-wazuh-install
curl --fail --location --silent --show-error --output wazuh-agent_4.14.10-1_arm64.deb https://packages.wazuh.com/4.x/apt/pool/main/w/wazuh-agent/wazuh-agent_4.14.10-1_arm64.deb
curl --fail --location --silent --show-error --output wazuh-agent_4.14.10-1_arm64.deb.sha512 https://packages.wazuh.com/4.x/checksums/wazuh/4.14.10/wazuh-agent_4.14.10-1_arm64.deb.sha512

# Continue only if the checksum reports OK
sha512sum --check wazuh-agent_4.14.10-1_arm64.deb.sha512
```

`--fail` interrompe o curl em erros HTTP, `--location` segue redirecionamentos
e `--output` escolhe o ficheiro. `--silent --show-error` esconde o progresso e
mantém as mensagens de erro. Até aqui não instalámos software.

## 4. Instalar os agentes e configurar a recolha

O bloco instala o pacote de forma persistente e guarda a configuração inicial.
`WAZUH_MANAGER` aponta para o manager; `WAZUH_AGENT_NAME` atribui um nome único.
Se algum nó já tiver agente ou configurações próprias, inspeciona-o antes de
repetir esta instalação ou substituir o backup.

```bash
# Install the agent and copy our collection template to both nodes
for node in k3s-master k3s-node1; do
  incus file push /tmp/ssle-wazuh-install/wazuh-agent_4.14.10-1_arm64.deb "$node/tmp/wazuh-agent.deb"
  incus exec "$node" -- env WAZUH_MANAGER=10.255.255.40 WAZUH_AGENT_NAME="$node" dpkg --install /tmp/wazuh-agent.deb || break
  incus exec "$node" -- cp --preserve=mode,ownership,timestamps /var/ossec/etc/ossec.conf /var/ossec/etc/ossec.conf.before-ssle
  incus file push "$project/deploy/wazuh/ingestion-agent.conf" "$node/tmp/ingestion-agent.conf"
done
```

Confirma que os dois pacotes foram instalados sem erro. Acrescentamos agora
apenas o bloco `localfile`, preservando a restante configuração de cada agente.

```bash
# Add ingestion collection once and validate both agent configurations
for node in k3s-master k3s-node1; do
  incus exec "$node" -- python3 - <<'PY' || break
from pathlib import Path
from xml.etree import ElementTree

config = Path('/var/ossec/etc/ossec.conf')
text = config.read_text()
template = ElementTree.parse('/tmp/ingestion-agent.conf').getroot()
block = ElementTree.tostring(template.find('localfile'), encoding='unicode')
location = '/var/log/containers/ssle-ingestion-*_ssle_ingestion-*.log'
if location in text:
    raise SystemExit('Collection already exists; inspect it before changing it')
if '</ossec_config>' not in text:
    raise SystemExit('Expected ossec_config closing tag was not found')
config.write_text(text.replace('</ossec_config>', block + '\n</ossec_config>', 1))
print('Ingestion log collection added')
PY
  incus exec "$node" -- /var/ossec/bin/wazuh-agentd -t || break
  incus exec "$node" -- /var/ossec/bin/wazuh-logcollector -t || break
done
```

Nos executáveis Wazuh, `-t` valida a configuração e termina; não tem forma longa.
**Se houver um erro, não continues para o arranque.** Recupera a configuração
pelo passo 10. O agente recolhe apenas os logs da ingestion no namespace `ssle`.
O prefixo `ssle-ingestion: ` impede o Wazuh de interpretar mal o cabeçalho CRI.

```bash
# Enable automatic startup and start the validated agents
for node in k3s-master k3s-node1; do
  incus exec "$node" -- systemctl daemon-reload
  incus exec "$node" -- systemctl enable --now wazuh-agent || break
  incus exec "$node" -- systemctl is-active wazuh-agent
done

# Wait a few seconds and confirm that both agents become Active
incus exec wazuh-container -- /var/ossec/bin/agent_control -l
```

`enable --now` ativa o arranque automático e arranca o serviço. Não avances para
o ensaio enquanto os dois agentes não aparecerem como `Active` no manager.

## 5. Instalar o decoder e as regras

Criamos dois ficheiros próprios no manager, sem alterar as regras do Apache.
`install` coloca os ficheiros com proprietário e permissões explícitos. `0640`
permite escrita ao root e leitura ao grupo Wazuh.

```bash
# Copy and install our decoder and rules
incus file push "$project/deploy/wazuh/ingestion-decoder.xml" wazuh-container/tmp/ingestion-decoder.xml
incus file push "$project/deploy/wazuh/ingestion-rules.xml" wazuh-container/tmp/ingestion-rules.xml
incus exec wazuh-container -- install --owner=root --group=wazuh --mode=0640 /tmp/ingestion-decoder.xml /var/ossec/etc/decoders/ssle_ingestion.xml
incus exec wazuh-container -- install --owner=root --group=wazuh --mode=0640 /tmp/ingestion-rules.xml /var/ossec/etc/rules/ssle_ingestion.xml

# Validate the complete manager ruleset before restarting it
incus exec wazuh-container -- /var/ossec/bin/wazuh-analysisd -t
```

**Só continua se a validação não mostrar erros.** Um erro de configuração pode
impedir o manager de arrancar. O restart seguinte recarrega as regras e interrompe
brevemente o processamento; os agentes devem voltar a ligar-se depois.

```bash
# Load the validated rules and check the indexing services
incus exec wazuh-container -- systemctl restart wazuh-manager
incus exec wazuh-container -- systemctl is-active wazuh-manager filebeat wazuh-indexer
```

## 6. Construir e importar a imagem da ingestion

O novo módulo só corre depois de substituirmos a imagem. Construímos no contentor
`docker` e importamos a imagem no containerd de cada nó. Não a publicamos num
registry. A tag nova já consta de `deploy/k8s/ingestion.yaml`.

```bash
# Transfer only the build inputs to the Docker container
cd "$project"
tar --create --file=/tmp/ssle-ingestion-build.tar ingestion.py instrumentation.py security_logging.py requirements.txt deploy/docker/ingestion/Dockerfile
incus file push /tmp/ssle-ingestion-build.tar docker/tmp/ssle-ingestion-build.tar
incus exec docker -- mkdir -p /root/ssle-ingestion-build
incus exec docker -- tar --extract --file=/tmp/ssle-ingestion-build.tar --directory=/root/ssle-ingestion-build

# Build and export the image
incus exec docker -- docker build --file=/root/ssle-ingestion-build/deploy/docker/ingestion/Dockerfile --tag "$image" /root/ssle-ingestion-build
incus exec docker -- docker save --output=/tmp/ssle-ingestion-image.tar "$image"
incus file pull docker/tmp/ssle-ingestion-image.tar /tmp/ssle-ingestion-image.tar

# Import the image into the namespace used by Kubernetes
for node in k3s-master k3s-node1; do
  incus file push /tmp/ssle-ingestion-image.tar "$node/tmp/ssle-ingestion-image.tar"
  incus exec "$node" -- k3s ctr --namespace k8s.io images import /tmp/ssle-ingestion-image.tar || break
done
```

`--file` seleciona o Dockerfile e `--tag` atribui o nome à imagem. O último
diretório do build é o contexto de construção. `--namespace k8s.io` seleciona
o espaço de imagens do Kubernetes no containerd. Confirma que ambos os imports
terminaram sem erro: o Deployment usa `imagePullPolicy: Never` e não fará downloads.

## 7. Aplicar a nova imagem

Este passo substitui o pod da ingestion. Não altera a base de dados nem os
restantes serviços. Pode haver pedidos com falhas transitórias durante a troca.

```bash
# Apply the prepared Deployment and its existing internal Service
incus file push "$project/deploy/k8s/ingestion.yaml" k3s-master/tmp/ssle-ingestion.yaml
incus exec k3s-master -- k3s kubectl --namespace ssle apply --filename=/tmp/ssle-ingestion.yaml

# Wait for completion and inspect the resulting pods
incus exec k3s-master -- k3s kubectl --namespace ssle rollout status deployment/ssle-ingestion --timeout=120s
incus exec k3s-master -- k3s kubectl --namespace ssle get pods --output=wide
```

`--filename` aplica o manifesto indicado. `--timeout=120s` limita a espera a dois
minutos; não desfaz automaticamente uma atualização que falhe. Para
`ErrImageNeverPull`, verifica a tag e o import no nó. Para `CrashLoopBackOff`,
consulta os logs antes de continuar.

## 8. Testar uma rejeição e depois a repetição

Usamos o NodePort existente, `10.255.255.10:30501`. São vinte pedidos inválidos,
a um por segundo, para testar deteção; não é um teste de carga. A resposta
esperada é HTTP 400 e os pedidos devem ser rejeitados antes de chegarem ao storage.

```bash
# Read the number of stored readings before the test
incus exec k3s-master -- k3s kubectl --namespace ssle exec deployment/ssle-sensor -- python -c 'import requests; print(requests.get("http://ssle-storage:5002/stats", timeout=5).json())'

# Send one invalid reading from Kali and show its response
curl --silent --show-error --max-time 5 --output /tmp/ssle-single-response.json --write-out 'HTTP %{http_code}\n' --header 'Content-Type: application/json' --data '{"device_id":"lab-test","temperature":"invalid"}' http://10.255.255.10:30501/ingest
cat /tmp/ssle-single-response.json

# Confirm the structured rejection event in the pod log
incus exec k3s-master -- k3s kubectl --namespace ssle logs deployment/ssle-ingestion --since=2m
```

`--data` faz um POST e `--header` identifica JSON. `--max-time 5` limita o pedido
a cinco segundos. `--write-out` mostra o estado HTTP e `--output` guarda o corpo.
O log deve conter `ingestion_rejected` e `invalid_temperature`.

Espera alguns segundos pela recolha e procura a regra `100201` no manager:

```bash
# Show recent ingestion alerts without unrelated events
incus exec wazuh-container -- python3 - <<'PY'
from collections import deque
import json

with open('/var/ossec/logs/alerts/alerts.json') as stream:
    lines = deque(stream, maxlen=4000)
for line in lines:
    alert = json.loads(line)
    if str(alert.get('rule', {}).get('id')) in {'100201', '100202'}:
        print(json.dumps({
            'timestamp': alert.get('timestamp'),
            'rule': alert['rule']['id'],
            'level': alert['rule']['level'],
            'agent': alert.get('agent', {}).get('name'),
            'data': alert.get('data'),
        }, ensure_ascii=False))
PY
```

Confirma o timestamp para distinguir este ensaio dos anteriores. Se não aparecer
o alerta individual, segue o diagnóstico do passo 9 antes de enviar a sequência.

```bash
# Send twenty invalid readings at one-second intervals
for attempt in $(seq 1 20); do
  printf 'Request %s: ' "$attempt"
  curl --silent --show-error --max-time 5 --output /dev/null --write-out 'HTTP %{http_code}\n' --header 'Content-Type: application/json' --data '{"device_id":"lab-test","temperature":"invalid"}' http://10.255.255.10:30501/ingest
  sleep 1
done

# Confirm that legitimate sensor readings continued to reach storage
incus exec k3s-master -- k3s kubectl --namespace ssle exec deployment/ssle-sensor -- python -c 'import requests; print(requests.get("http://ssle-storage:5002/stats", timeout=5).json())'
```

Repete a consulta ao `alerts.json`: deve aparecer `100202`, com nível 10.
O contador de leituras guardadas deve aumentar devido ao sensor legítimo.
Esse aumento, por si só, não prova ausência total de falhas; consulta os logs
do sensor se houver erros no ensaio.

Abre [o dashboard Wazuh](https://192.168.64.3:8443), entra com a tua conta e abre
**Threat hunting**. Seleciona os últimos 15 minutos e usa este filtro:

```text
rule.id: "100201" OR rule.id: "100202"
```

Confirma a hora, o agente, o nível e `data.srcip`. O `alerts.json` confirma
deteção pelo manager; o dashboard confirma também a indexação.

**Limite do ensaio:** o NodePort usa `externalTrafficPolicy: Cluster` e pode
traduzir o IP de origem. Regista o `srcip` observado: pode ser o de um nó em vez
do da Kali. Não atives bloqueio desse IP antes de resolver a preservação da origem
e escolher o ponto da rede onde aplicar o bloqueio.

## 9. Localizar uma falha

- Sem HTTP 400 ou sem JSON no pod: verifica o rollout e a imagem da ingestion
- Com JSON, mas sem `100201`: verifica o agente no nó do pod, a recolha e o decoder
- Com `100201`, mas sem `100202`: verifica origem, agente e dez eventos em 30 segundos
- Com alerta no manager, mas não no dashboard: verifica o tempo selecionado e a indexação

```bash
# Find the current ingestion node
incus exec k3s-master -- k3s kubectl --namespace ssle get pods --selector=app=ssle-ingestion --output=wide

# Read the agent state and recent agent logs
for node in k3s-master k3s-node1; do
  incus exec "$node" -- systemctl is-active wazuh-agent
  incus exec "$node" -- tail --lines=40 /var/ossec/logs/ossec.log
done

# Read manager errors and check Filebeat and the indexer
incus exec wazuh-container -- tail --lines=60 /var/ossec/logs/ossec.log
incus exec wazuh-container -- systemctl is-active filebeat wazuh-indexer
incus exec wazuh-container -- journalctl --unit=filebeat --lines=40 --no-pager
```

`--selector` limita a consulta à ingestion. `--lines` limita a saída.
`--unit=filebeat` seleciona esse serviço no journal e `--no-pager` evita um
visualizador interativo. Estes comandos apenas consultam o estado e os logs.

## 10. Recuperar o estado anterior

Executa apenas a parte correspondente ao que precisas de desfazer.
Este primeiro bloco recupera a imagem anterior através do Deployment guardado;
pode substituir o pod, mas não altera as leituras guardadas.

```bash
# Restore the saved ingestion deployment
backup=$(cat /home/tfdmendes/ssle-monitoring-backups/latest-wazuh-ingestion.txt)
incus file push "$backup/ingestion-deployment.yaml" k3s-master/tmp/ssle-ingestion-before.yaml
incus exec k3s-master -- k3s kubectl --namespace ssle apply --filename=/tmp/ssle-ingestion-before.yaml
incus exec k3s-master -- k3s kubectl --namespace ssle rollout status deployment/ssle-ingestion --timeout=120s
```

Para recuperar os nossos dois ficheiros do manager, restaura versões anteriores
se existiam; caso contrário, remove apenas os ficheiros que criámos.

```bash
# Restore or remove only our two manager configuration files
incus exec wazuh-container -- sh -c '
  for kind in decoders rules; do
    saved="/root/ssle-ingestion-before/$kind-ssle_ingestion.xml"
    target="/var/ossec/etc/$kind/ssle_ingestion.xml"
    if [ -f "$saved" ]; then
      cp --preserve=mode,ownership,timestamps "$saved" "$target"
    else
      rm --force -- "$target"
    fi
  done
'

# Validate the recovered manager configuration
incus exec wazuh-container -- /var/ossec/bin/wazuh-analysisd -t
```

Se a validação passar, carrega a configuração recuperada:

```bash
# Restart the manager after successful validation
incus exec wazuh-container -- systemctl restart wazuh-manager
```

Para parar a recolha nos nós e recuperar a configuração inicial:

```bash
# Stop the newly installed agents and restore their original configuration
for node in k3s-master k3s-node1; do
  incus exec "$node" -- systemctl disable --now wazuh-agent
  incus exec "$node" -- cp --preserve=mode,ownership,timestamps /var/ossec/etc/ossec.conf.before-ssle /var/ossec/etc/ossec.conf
done
```

Os pacotes ficam instalados, mas os agentes ficam parados e sem arranque
automático. Os registos dos agentes no manager não são removidos. Os backups e
os dados da aplicação também ficam preservados.

## Referências

- [Instalação do agente Linux](https://documentation.wazuh.com/current/installation-guide/wazuh-agent/wazuh-agent-package-linux.html)
- [Pacotes oficiais](https://documentation.wazuh.com/current/installation-guide/packages-list.html)
- [Recolha e out_format](https://documentation.wazuh.com/current/user-manual/reference/ossec-conf/localfile.html)
- [Decoder JSON](https://documentation.wazuh.com/current/user-manual/ruleset/decoders/json-decoder.html)
- [Regras e correlação](https://documentation.wazuh.com/current/user-manual/ruleset/ruleset-xml-syntax/rules.html)
