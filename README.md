# Loyalty Predict

Modelo de machine learning que prevê quais clientes de um programa de fidelidade vão estar no ciclo de vida **Fiel** daqui a 28 dias. O projeto vai do dado bruto ao modelo registrado no MLflow: engenharia de dados em SQL, feature store com snapshots diários, treino com validação out-of-time, escoragem da base, API de inferência e monitoramento.

> Projeto desenvolvido acompanhando o [Loyalty Predict](https://github.com/TeoMeWhy/loyalty-predict) do [Téo Me Why](https://github.com/TeoMeWhy). Os dados são públicos e vêm do sistema de pontos e da plataforma de cursos da comunidade dele.

## Problema

Em um programa de fidelidade, saber **antes** quem vai virar (ou continuar) cliente fiel permite direcionar ações de engajamento para as pessoas certas. A pergunta do modelo é:

> Dado o comportamento de um cliente até a data de referência, qual a probabilidade de ele estar no ciclo de vida **02-FIEL** 28 dias depois?

## Resultados

Modelo em produção: **`model_fiel` v2**, Random Forest (`n_estimators=500`, `min_samples_leaf=50`), marcado com o alias `champion` no MLflow.

| Base | Acurácia | AUC |
|---|---|---|
| Treino | 0.929 | 0.917 |
| Teste | 0.933 | 0.879 |
| Out-of-time (2025-09-01) | 0.893 | 0.832 |
| Baseline no teste ("ninguém é fiel") | 0.921 | 0.500 |

![Curva ROC](src/analytics/curva_roc.png)

- A taxa de clientes fiéis na base é de **~9%**, então a acurácia sozinha engana: chutar "não fiel" para todos já acerta 92% no teste. A métrica principal é a **AUC**.
- Treino e teste são separados **por cliente**: a ABT tem até 2 datas por cliente, e nenhum cliente aparece nos dois lados. A out-of-time é a última data da ABT, separada antes do treino; os rótulos do treino vão só até 2025-08-29.
- Variáveis mais importantes: `qtdeAtivacaoD28`, `qtdeFrequencia`, `pctAtivacaoMAU`, `qtdeAtivacaoD56`, `qtdeAtivacaoD14` e `pctFiel`.

### v1 × v2

A v1 separava treino e teste por linha, e 82,7% das linhas de teste eram de clientes que também estavam no treino. Isso deixava a AUC de teste otimista. A v2 separa por cliente (também no cross-validation do `GridSearchCV`), começa a ABT em 2024-03-29 (antes disso faltava o ciclo de vida de D-28) e amostra a ABT de forma reprodutível. As duas foram comparadas **na mesma out-of-time** com [compara_modelos.py](src/analytics/compara_modelos.py):

| Versão | Split treino/teste | AUC teste | AUC OOT | Acurácia OOT |
|---|---|---|---|---|
| v1 | por linha | 0.8918 (otimista) | 0.8225 | 0.8884 |
| v2 | por cliente | 0.8789 | **0.8317** | **0.8929** |

A AUC de teste caiu porque ficou honesta; a out-of-time, que é a medida que vale para decidir, melhorou.

## Arquitetura

```
Kaggle ──> get_data.py ──> data/loyalty-system  ·  data/education-platform
                                      │
                                      ▼
     pipeline_analytics.py (snapshots diários, retoma do último dtRef salvo)
     life_cycle · fs_transacional · fs_education · fs_life_cycle · fs_all
     │                                                               │
     ▼                                                               ▼
 target.sql + abt.py ──> abt_fiel ──> train.py ──> MLflow ──> predict_fiel.py ──> score_fiel ──> monitoramento.py
                                                     │  (versão com o alias champion)
                                                     └──> api_fiel.py (/predict, /predict_many)
```

1. **Coleta** ([get_data.py](src/engineering/get_data.py)): baixa as bases do Kaggle.
2. **Ciclo de vida** ([life_cycle.sql](src/analytics/life_cycle.sql)): classifica cada cliente em cada data de referência pela recência e frequência de transações: `01-Curioso`, `02-Fiel`, `02-Reconquistado`, `02-Reborn`, `03-Turista`, `04-Desencantada`, `05-Zumbi`. As regras estão no topo do arquivo.
3. **Feature store** (`fs_*.sql`): três tabelas de atributos calculadas sempre com dados *anteriores* à data de referência, para não vazar informação do futuro:
   - [fs_transacional.sql](src/analytics/fs_transacional.sql): ativações, transações, pontos e horário de uso em janelas de 7, 14, 28 e 56 dias.
   - [fs_life_cycle.sql](src/analytics/fs_life_cycle.sql): ciclo de vida atual, há 28 dias e a distribuição dos ciclos no histórico do cliente.
   - [fs_education.sql](src/analytics/fs_education.sql): cursos concluídos e engajamento na plataforma educacional.

   O [pipeline_analytics.py](src/analytics/pipeline_analytics.py) atualiza tudo a partir do dia seguinte ao último snapshot salvo, então dias sem execução não viram buraco.
4. **ABT** ([target.sql](src/analytics/target.sql) + [abt.py](src/analytics/abt.py)): junta as features com o alvo `flFiel` (ciclo de vida em D+28), sem clientes Zumbis, e amostra até 2 datas por cliente com semente fixa, para clientes antigos não dominarem a base e a ABT ser sempre a mesma.
5. **Treino** ([train.py](src/analytics/train.py)): pipeline `feature-engine` + scikit-learn com remoção de features sem poder de separação, imputação, one-hot encoding e Random Forest otimizado com `GridSearchCV` (AUC, 3 folds agrupados por cliente). Métricas, baseline, curva ROC e modelo vão para o MLflow.
6. **Registro e promoção**: cada treino vira uma versão do `model_fiel`. A produção usa a versão com o alias `champion`, então registrar uma versão nova não muda nada; promover é mover o alias.
7. **Escoragem** ([predict_fiel.py](src/analytics/predict_fiel.py)): escora os clientes ativos do snapshot mais recente e guarda o histórico em `score_fiel`, com a versão do modelo usada.
8. **API** ([api_fiel.py](src/api/api_fiel.py)): `/predict` para um cliente e `/predict_many` para vários, com a mesma versão `champion`.
9. **Monitoramento** ([monitoramento.py](src/analytics/monitoramento.py)): quando o score de uma data completa 28 dias, compara com o ciclo de vida real (AUC, taxa real de fiéis e score médio).

Análises de apoio: [DAU](src/analytics/dau.sql), [MAU](src/analytics/mau.sql), [relatório de ciclo de vida](src/analytics/report_ciclo_vida.sql) e uma [segmentação frequência × valor com KMeans](src/analytics/frequencia_valor.py).

## Tecnologias

Python · SQL (SQLite) · pandas · scikit-learn · feature-engine · MLflow · Flask · SQLAlchemy · matplotlib · Make

## Como executar

### 1. Ambiente

```bash
git clone https://github.com/vitorrrfernandes/loyalty-predict-ml.git
cd loyalty-predict-ml
make setup        # cria o ambiente conda em .conda/ e instala o requirements.txt
conda activate ./.conda
```

### 2. Credenciais do Kaggle

Crie o arquivo `src/.env` (ele está no `.gitignore`) com a sua chave da API do Kaggle:

```
KAGGLE_USERNAME=seu_usuario
KAGGLE_KEY=sua_chave
```

O `make collect` baixa as bases para `data/loyalty-system/` e `data/education-platform/`. A base analítica (`data/analytics/`) é criada pelo pipeline e passa de 1 GB.

### 3. MLflow

```bash
mlflow server --host 127.0.0.1 --port 5000
```

> No macOS, use `127.0.0.1` e não `localhost`: o AirPlay Receiver também escuta a porta 5000 e responde com erro 403. Para usar outro endereço, defina a variável `MLFLOW_TRACKING_URI`.

### 4. Primeira carga do histórico

Na primeira vez, calcule os snapshots diários desde o início dos dados. Pode levar mais de uma hora.

```bash
make collect
cd src/analytics
python exec_query.py --table life_cycle      --db_origin loyalty-system     --start 2024-03-01 --stop $(date +%F)
python exec_query.py --table fs_transacional --db_origin loyalty-system     --start 2024-03-01 --stop $(date +%F)
python exec_query.py --table fs_education    --db_origin education-platform --start 2024-03-01 --stop $(date +%F)
python exec_query.py --table fs_life_cycle   --db_origin analytics          --start 2024-03-01 --stop $(date +%F)
cd ../..
```

### 5. Treino e promoção

```bash
make abt          # recria a ABT (sempre a mesma amostra)
make train        # treina, loga no MLflow e imprime o id do run
```

Registre o run como nova versão do `model_fiel` (pela interface do MLflow ou com `mlflow.register_model("runs:/<id do run>/model", "model_fiel")`), compare as versões na mesma out-of-time com `cd src/analytics && python compara_modelos.py` e, se a nova for melhor, mova o alias `champion` para ela.

### 6. Dia a dia

```bash
make all          # setup + collect + etl + predict: baixa os dados, atualiza as feature stores e escora os clientes ativos
make monitor      # confere os scores que já completaram 28 dias
make api          # sobe a API em http://127.0.0.1:5001
```

Com a API no ar, `cd src/api && python test_api.py` envia linhas reais do `fs_all` para os dois endpoints:

```
POST /predict       {"data": {"IdCliente": "...", <features>}}   ->  {"IdCliente": "...", "score": 0.75}
POST /predict_many  {"data": [{...}, {...}]}                     ->  {"result": [{"IdCliente": "...", "score": 0.75}, ...]}
```

## Limitações

- O modelo dá a probabilidade de o cliente estar Fiel **exatamente 28 dias depois** da data de referência. Não é uma previsão dia a dia e não diz quando o cliente vai sair.
- Clientes Zumbis (mais de 28 dias sem transação) ficam fora do treino e, por isso, também da escoragem.
- O monitoramento só mostra resultados 28 dias depois da primeira escoragem guardada no histórico.
- A integração com o ecossistema TMW, última etapa do curso, ainda não foi feita.

## Estrutura

```
.
├── Makefile                      # setup, collect, etl, predict, abt, train, api, monitor
├── AUDITORIA.md                  # auditoria contra o projeto de referência e histórico das correções
├── docs/
│   └── Relatorio_Analise_Loyalty_Predict.docx   # relatório da fase de analytics (antes da modelagem)
├── src/engineering/
│   └── get_data.py               # baixa as bases do Kaggle
├── src/analytics/
│   ├── exec_query.py             # executa uma query SQL para um intervalo de datas e grava na base analítica
│   ├── pipeline_analytics.py     # atualiza as feature stores a partir do último snapshot
│   ├── *.sql                     # ciclo de vida, feature store, ABT e métricas
│   ├── abt.py                    # amostra a ABT de treino
│   ├── train.py                  # treino e avaliação
│   ├── compara_modelos.py        # compara as versões do model_fiel na mesma out-of-time
│   ├── predict_fiel.py           # escoragem em lote com a versão champion
│   ├── monitoramento.py          # score x ciclo de vida real em D+28
│   ├── predict.py                # escoragem exploratória da ABT
│   └── frequencia_valor.py       # segmentação exploratória
├── src/api/
│   ├── api_fiel.py               # API Flask: /predict e /predict_many
│   └── test_api.py               # cliente de teste da API
├── LICENSE
├── requirements.txt
└── README.md
```

## Créditos

Este projeto foi construído acompanhando as aulas ao vivo do **Loyalty Predict**, do [Téo Me Why](https://github.com/TeoMeWhy). O projeto original, que serviu de referência para o pipeline, as regras de ciclo de vida e o modelo, está em [github.com/TeoMeWhy/loyalty-predict](https://github.com/TeoMeWhy/loyalty-predict).

Assim como o original, este repositório é distribuído sob a licença [GPL-3.0](LICENSE).

## Autor

**Vitor Fernandes** · [GitHub](https://github.com/vitorrrfernandes)
