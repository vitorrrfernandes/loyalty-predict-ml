# Auditoria: Loyalty Predict (Vitor) × referência TeoMeWhy

- **Data:** 2026-11-10
- **Referência:** `TeoMeWhy/loyalty-predict`, commit `346e3bd` ("feat: api com predicao para fiel"), clonada em `/tmp/loyalty-predict-ref` (sem alterações)
- **Etapa atual:** o campo veio como `[PREENCHA]`. Pelo código, você está em **"App de inferência"**: a API tem `/health_check` pronto e `/predict` ainda é um esboço.
- **Como foi feito:** leitura de todos os `.sql`/`.py` dos dois projetos, inspeção dos bancos locais em modo somente-leitura e execução do Makefile, do `train.py` e da API sobre uma **cópia** dos dados e do MLflow (fora do projeto). Nenhum arquivo do seu projeto foi alterado além deste relatório: o `git status` está idêntico ao do início e os `.db` mantêm as datas originais.

---

## 1. Resumo geral

**Está OK**
- O pipeline roda de ponta a ponta com as versões fixadas: `make etl`, `make predict`, `train.py`, `target.sql`, a API e os scripts exploratórios executaram sem erro.
- A **lógica das Feature Stores está correta e sem vazamento temporal**. Toda FS usa só dados `< {date}`, e `dtRef = {date} − 1`. Recalculei `life_cycle`, `fs_transacional` e `fs_life_cycle` com o SQL atual para 2024-06-01 e 2025-09-01, e o resultado bateu 100% com o que está salvo. No `fs_education` a diferença foi de 1 a 2 clientes (348 recalculados contra 347 salvos), o que é esperado: a base de origem foi baixada de novo depois.
- O alvo (`flFiel` = estar `02-FIEL` em D+28, excluindo zumbis) é igual ao da referência e coerente com o objetivo. A OOT (2025-09-01) está separada no tempo: os rótulos do treino vão até 2025-08-29.
- Seus nomes próprios (rótulos `03-Turista`/`05-Zumbi`, colunas `qtdeTransacoesVida`, `qtdDiasUltimaAtividade` etc.) estão **consistentes em todos os arquivos**. O `fs_all` tem as 93 features que o modelo espera.
- Em 4 pontos, **você corrigiu bugs que existem na referência** (ver seção 5).
- `.gitignore` cobre `.env`, `kaggle.json`, `*.db`, `*.csv`, `*.pkl`, `mlartifacts/` e `mlruns/`. **Nenhum dado ou credencial aparece em nenhum commit do histórico.**
- Lint: `pyflakes` sem nenhum aviso; `py_compile` OK nos 9 arquivos.

**Falta (etapas do curso)**
- `/predict` e `/predict_many` da API, e a integração com o ecossistema TMW (seção 3).

**Está errado ou merece correção**
- 🔴 **Nenhum problema crítico.** Nada quebra a execução, não há vazamento de informação futura nas features e o alvo está correto.
- 🟡 **5 problemas importantes.** Os mais relevantes:
  - um **buraco de datas** na FS que zera `descLifeCycleD28` na escoragem atual;
  - **o mesmo cliente aparece em treino e teste**, o que deixa a AUC de teste otimista;
  - **930 linhas da ABT** com `descLifeCycleD28` nulo por artefato do backfill.
- 🔵 **16 melhorias** de reprodutibilidade, organização e documentação.

---

## 2. Problemas por gravidade

### 🔴 Crítico

**Nenhum encontrado.** O que foi verificado para chegar a essa conclusão:
- **Filtros de data:** todos usam `< '{date}'`. As janelas D7/D14/D28/D56 usam `>= date('{date}', '-N day')`.
- **`fs_life_cycle`:** só olha `dtRef < {date}`.
- **Alvo:** é o ciclo de vida em `dtRef + 28`.
- **Bivariada e `to_remove`:** calculadas só com `X_train`.
- **Imputação e one-hot:** ficam dentro do `Pipeline`, ajustados só no treino.

### 🟡 Importante

#### I1. Buraco de datas na Feature Store zera `descLifeCycleD28` na escoragem atual
- **Arquivos:** `src/analytics/pipeline_analytics.py:6-55` (todas as etapas usam `dt_start = dt_stop = now`) e `src/analytics/fs_life_cycle.sql:10-15` (busca o `life_cycle` de `{date} − 29 dias`).
- **Problema:** o `life_cycle` salvo não tem as datas **2026-10-05 a 2026-10-28** nem **2026-10-30 a 2026-11-03**. O `fs_education` tem os mesmos buracos. Como o pipeline só calcula "hoje", qualquer dia sem execução vira buraco.
- **Consequência:** em `fs_all` e `score_fiel` de 2026-11-05, o `descLifeCycleD28` está **nulo para 100% dos 3.796 clientes** e é imputado como `Nao-Usuario`. O mesmo vai acontecer em qualquer execução até 28 dias depois do buraco.
- **Impacto medido (na cópia):** preenchi o buraco e escorei de novo. Com o modelo atual (v1), a diferença foi pequena: |Δscore| médio de 0,0004, máximo de 0,0096, Spearman 0,997 e 95 dos 100 primeiros iguais. Ainda assim, é um dado errado entrando no modelo, e um modelo que dependa mais dessa feature sofreria mais.
- **Referência:** tem o mesmo desenho (só `now`) e, portanto, a mesma fragilidade.
- **Correção:**
  1. Preencher o buraco, rodando a partir de `src/analytics`. Isso altera `data/analytics/database.db`.
     ```bash
     python exec_query.py --table life_cycle      --db_origin loyalty-system     --start 2026-10-05 --stop <hoje>
     python exec_query.py --table fs_transacional --db_origin loyalty-system     --start 2026-10-05 --stop <hoje>
     python exec_query.py --table fs_education    --db_origin education-platform --start 2026-10-05 --stop <hoje>
     python exec_query.py --table fs_life_cycle   --db_origin analytics          --start 2026-10-05 --stop <hoje>
     cd ../.. && make etl predict
     ```
  2. Definitivo: no `pipeline_analytics.py`, calcular `dt_start` como (maior `dtRef` da tabela + 2 dias) até `now`, para o pipeline se recuperar sozinho quando pular dias. O modo `append` já é idempotente porque apaga o `dtRef` antes de inserir.

#### I2. O mesmo cliente aparece no treino e no teste (validação otimista)
- **Arquivo:** `src/analytics/train.py:42-48` (`train_test_split` por linha) e `:143-151` (`GridSearchCV(cv=3)` por linha).
- **Problema:** a ABT tem até 2 linhas por cliente (2.603 dos 3.042 clientes aparecem 2 vezes). O split aleatório por linha coloca **82,7% das linhas de teste com o mesmo cliente presente no treino**. Na OOT, isso cai para 2,0%. O CV do GridSearch tem o mesmo problema, o que favorece hiperparâmetros que "decoram" o cliente.
- **Consequência:** a AUC de teste (0,89) está inflada. A queda para a OOT (0,82) **não é só "mudança de comportamento"**, como diz o `README.md:24`: parte dela é essa sobreposição. A OOT é a métrica honesta.
- **Por que 🟡 e não 🔴:** é um vazamento entre partições da validação, não uma feature com informação do futuro. O modelo em si e a OOT não são contaminados; o que fica errado é a leitura da métrica de teste.
- **Referência:** tem o mesmo problema.
- **Correção:** split e CV agrupados por cliente. Testei este código com as suas versões e ele roda.
  ```python
  groups = df_train_test["IdCliente"]
  gss = model_selection.GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
  idx_train, idx_test = next(gss.split(X, y, groups=groups))
  X_train, X_test = X.iloc[idx_train], X.iloc[idx_test]
  y_train, y_test = y.iloc[idx_train], y.iloc[idx_test]

  grid = model_selection.GridSearchCV(
      model, param_grid=params, scoring="roc_auc", refit=True, verbose=3, n_jobs=8,
      cv=model_selection.StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=42),
  )
  model_pipeline.fit(X_train, y_train, Algoritmo__groups=groups.iloc[idx_train])
  ```

#### I3. 930 linhas da ABT (16,5%) com `descLifeCycleD28` nulo por artefato do backfill
- **Arquivos:** `src/analytics/target.sql:17` (cohort a partir de `2024-03-01`) e `README.md:89-92` (backfill de todas as tabelas a partir de `2024-03-01`).
- **Problema:** o `life_cycle` começa em `dtRef = 2024-02-29`, mas as transações começam em **2024-01-27**. Para os `dtRef` de 2024-03-01 a 2024-03-28, o snapshot de D−28 não existe. Por isso o `descLifeCycleD28` está nulo em **99%** dessas 930 linhas, contra 56,5% no resto do treino. Essas linhas viram `Nao-Usuario` ("cliente novo") mesmo quando o cliente já existia. Os `pct*` (histórico de ciclos) também ficam com histórico curto nesse período.
- **Referência:** não documenta a data de início do backfill, então não dá para confirmar se tem o mesmo problema.
- **Correção (escolha uma):**
  - **(a) Mais simples:** começar o cohort em `2024-03-29` no `target.sql:17`.
  - **(b) Mais completa:** rodar o backfill do `life_cycle` desde `2024-02-01`, recalcular `fs_life_cycle` (no mínimo de 2024-03-01 a 2024-03-29; o ideal é tudo) e recriar a ABT.
  - Nos dois casos é preciso **retreinar**.

#### I4. `fs_education` conta episódios duplicados (`COUNT` sem `DISTINCT`)
- **Arquivo:** `src/analytics/fs_education.sql:6`, `COUNT(descSlugCursoEpisodio) AS qtdeEps`.
- **Problema:** `cursos_episodios_completos` tem registros repetidos do mesmo episódio para o mesmo usuário. Com os dados de hoje, 15 dos 5.484 pares usuário-curso ficam inflados e 8 chegam a `pctCursoCompleto > 1`. Esses pares não entram nem em `qtdeCursosCompletos` (`= 1`) nem em `qtdeCursosIncompletos` (`< 1`), então hoje há 1.516 cursos completos onde deveria haver 1.520.
- **Impacto:** pequeno, mas é um erro de agregação.
- **Referência:** **tem o mesmo bug** (`fs_education.sql:4`).
- **Correção:** `COUNT(DISTINCT descSlugCursoEpisodio)`. Depois é preciso recalcular `fs_education` em todo o período, recriar a ABT e retreinar. Dá para juntar com o próximo retreino.

#### I5. Cliente de teste da API com bug
- **Arquivo:** `src/api/import requests.py:4-5`.
- **Problemas:**
  - `resp.json` sem parênteses devolve o método, não o JSON.
  - O `POST` é enviado sem corpo; com o `/predict` da referência, isso retorna 400.
  - O nome do arquivo tem espaço, então não dá para importá-lo.
  - `requests` não está no `requirements.txt` (hoje só vem como dependência transitiva).
- **Correção:**
  ```python
  resp = requests.post("http://127.0.0.1:5001/predict", json={"data": {...}})
  print(resp.status_code, resp.json())
  ```
  Renomear para `src/api/test_api.py`.

### 🔵 Melhoria

| # | Arquivo:linha | Problema | Sugestão |
|---|---|---|---|
| M1 | `src/analytics/target.sql:11` | `ORDER BY random()` não aceita semente no SQLite, então cada recriação da ABT sorteia linhas diferentes (recriei na cópia e saíram 517 datas em vez de 519). O treino não é reprodutível a partir do zero. A referência tem o mesmo problema. | Fazer a amostragem de 2 datas por cliente em pandas com `random_state`, ou nunca recriar a ABT sem versioná-la. |
| M2 | `src/analytics/train.py:76-78` | `features.remove(i)` altera a lista dentro da célula da bivariada. Se você rodar a célula de novo, `to_remove` vira `[]`, as features deixam de ser removidas e o `fill_0` muda. A execução depende da ordem das células. | Calcular `to_remove` sem mutar listas: `features_ok = [f for f in features if f not in to_remove]`. |
| M3 | `src/analytics/train.py:15` | `set_experiment(experiment_id=1)` quebra num MLflow novo, onde o ID 1 não existe. | `mlflow.set_experiment(experiment_name="exp_predict_fiel")`. |
| M4 | `train.py:14`, `predict.py:10`, `predict_fiel.py:9`, `api_fiel.py:5` | A URI do MLflow está fixa no código e inconsistente: `127.0.0.1` em uns, `localhost` em outros. | Ler de `os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000")` em todos. |
| M5 | MLflow / `README.md:17-19` | O modelo registrado (`model_fiel` v1, run `69f947f1`, de 27/10) é um RandomForest(250, leaf=50) **sem GridSearch**, ou seja, não é o resultado do `train.py` atual. O README mostra OOT AUC 0,813, mas a v1 tem 0,8178 e o `train.py` atual gera 0,8184. | Depois de I2 e I3, retreinar, registrar a nova versão e atualizar a tabela do README. |
| M6 | `README.md:43,58,83-101` | O README está desatualizado: cita `predict.py` como escoragem (o Makefile usa `predict_fiel.py`), sugere `.venv` (o Makefile usa `.conda`) e não menciona `Makefile`, `pipeline_analytics.py`, `fs_all` nem a API. | Atualizar a seção "Como executar" para `make setup / make all` e listar `predict_fiel.py` e a API. |
| M7 | `src/analytics/exec_query.py:28` | `date_range("2024-01-01", "2025-01-01", monthly=True)` roda no import (sobra de teste). Os `print` nas linhas 50 e 56 poluem a barra do `tqdm`. | Remover a linha 28; trocar os prints por `tqdm.write` ou removê-los. |
| M8 | `src/analytics/train.py:229-230` | A legenda da curva ROC mostra a AUC sem formatação (`0.9016453720180454`). | `f"Treino: {auc_train:.4f}"`, como já está feito na OOT. |
| M9 | `src/analytics/train.py` | Não há baseline. A referência tem o "fodase" (`train.py:197-203`); com 8,7% de alvo, acurácia sozinha engana. | Logar a AUC e a acurácia de um baseline constante para comparação. |
| M10 | `src/engineering/get_data.py:21` | No `kaggle==2.2.5`, se o servidor compactar o arquivo, o download vira `database.db.zip` e **não é extraído** (`unzip=False` é o padrão). Hoje funcionou, mas é frágil. | `api.dataset_download_file(d, 'database.db', path=path, unzip=True, force=True)`. |
| M11 | Raiz e `src/` | Arquivos soltos: `database.db` na raiz (73 MB, cópia antiga do loyalty-system), `src/analytics/model_fiel.pkl`, `src/analytics/s.sql`, `src/engineering/query.sql`, `data/loyalty-system/query.sql` e `*.session.sql` vazios. Também `src/kaggle.json`, que é redundante: o `src/.env` já tem `KAGGLE_USERNAME` e `KAGGLE_KEY`, e a lib do Kaggle não lê `kaggle.json` de `src/`. | Apagar ou mover para fora do repo. Menos cópias de credencial é melhor. |
| M12 | `.gitignore` | Não cobre `*.parquet` (você pediu para checar) nem `*.zip` (ver M10). | Adicionar `*.parquet`, `*.zip` e `.ruff_cache/`. |
| M13 | `src/analytics/frequencia_valor.sql:15-21` / `.py:53-59` | Os rótulos divergem do `life_cycle.sql` (`12-HYPERS`, `21-ESFORCADO`, `01-PREGUICOSO`) e há um erro de digitação: **`20s-POTENCIAL`**. O `.py` calcula o KMeans mas plota só os clusters da regra SQL; a referência plota os dois. O arquivo é só exploratório. | Usar os mesmos rótulos do `life_cycle.sql` e adicionar o gráfico com `hue="cluster_calc"`. |
| M14 | `Makefile` | Não há alvos para ABT, treino nem API (a referência também não tem). Rodar `etl` sem `collect` gera `dtRef` além do fim dos dados: as transações vão até 2026-11-06 e o ETL de hoje gerou `dtRef` 2026-11-09, o que infla a recência de todo mundo. | Adicionar `abt` (`sqlite3 … < target.sql`), `train` e `api`, e fazer `etl` depender de `collect`. |
| M15 | `src/analytics/predict_fiel.py:28` | `score_fiel` é sobrescrito (`replace`) a cada execução, então o histórico de scores se perde. A referência faz o mesmo. | Para monitorar, gravar em modo append, apagando antes o `dtRef` do dia. |
| M16 | Vários | Ruídos menores, iguais aos da referência: (a) `fs_transacional.sql:129-133`: 1.082 transações têm mais de um produto em `transacao_produto` e inflam levemente o denominador dos shares; (b) `fs_education.sql:17`: o total de episódios vem do catálogo atual (sem data), um pequeno "olhar o futuro" que é inerente ao dado; (c) `02-Reconquistado`/`02-Reborn` em D+28 contam como `flFiel = 0`, embora também sejam ganho de engajamento. Isso é escolha de desenho; vale discutir. | Apenas registrar ou discutir; não precisa de ação agora. |

> **Não renomeie colunas agora** (por exemplo, `qtdeTransacoesVida` → `qtdeTransacaoVida`), mesmo que fiquem mais parecidas com a referência. O modelo registrado guarda `feature_names_in_` e quebraria. Se quiser padronizar, faça isso junto com um retreino.

---

## 3. Etapas do curso ainda não implementadas (em ordem)

| # | Etapa | Status |
|---|---|---|
| 1 | Entendimento do negócio | ✅ README e `docs/Relatorio_Analise_Loyalty_Predict.docx` |
| 2 | Extração dos dados | ✅ `get_data.py` e `make collect` |
| 3 | Entendimento dos dados | ✅ `dau.sql`, `mau.sql`, `frequencia_valor.*`, `report_ciclo_vida.sql` |
| 4 | Definição das variáveis | ✅ `life_cycle.sql`, `target.sql` |
| 5 | Feature Stores | ✅ `fs_*.sql`, `fs_all.sql`, `pipeline_analytics.py` (ver I1, I3, I4) |
| 6 | Treinamento | ✅ `train.py` (ver I2) |
| 7 | Registro no MLflow | ✅ `model_fiel` v1, mas desatualizado em relação ao `train.py` (M5) |
| 8 | **App de inferência** | ⏳ **Em andamento.** Falta, em ordem: **(a)** lógica do `/predict` em `src/api/api_fiel.py:16-18` (hoje devolve `{}`); **(b)** endpoint `/predict_many` (hoje dá 404); **(c)** cliente de teste corrigido (I5). |
| 9 | Integração com o ecossistema TMW | ⏳ Não iniciado. **A referência também não tem código dessa etapa no repositório**: o último commit é a API. Acompanhe pela aula. |

**Atenção ao implementar o `/predict` (8a):** não copie `float(predict)` da referência (`api_fiel.py:25`). Testei com o **NumPy 2.5.2** do seu `requirements.txt` e `float(np.array([0.5]))` levanta `TypeError: only 0-dimensional arrays can be converted to Python scalars`. Como o `except` genérico da referência engole o erro e devolve `{"erro": ...}, 400`, o endpoint **sempre falharia** no seu ambiente. Use `float(predict[0])` e, no `except`, logue o erro (`app.logger.exception(err)`) em vez de escondê-lo.

---

## 4. Instalação, execução e lint

### 4.1 Ambiente
- **Venv criado fora do projeto**, em `/private/tmp/claude-501/-Users-vitorfernandes-Documents-mesa-loyalty-predict-main-vitor/085fb566-ae60-4336-9d77-7100ecd29e54/scratchpad/venv314`, com Python **3.14.4**. Seu `.conda` usa 3.14.7.
- `pip install -r requirements.txt`: **sucesso**, sem erros. `pip check`: "No broken requirements found".
- O modelo registrado foi salvo com `scikit-learn 1.9.0`, `pandas 3.0.5` e `mlflow 3.17.2`, exatamente as versões fixadas. Não há aviso de versão incompatível ao carregar.

### 4.2 Execução (na ordem do Makefile, sobre uma cópia dos dados e do MLflow)

| Etapa | Resultado |
|---|---|
| `setup` | ✅ (venv acima, em vez de `conda`) |
| `collect` | ⏭️ **Não executado**, porque baixar do Kaggle não era permitido. Os dados já estão no lugar: `data/loyalty-system/database.db` (transações de 2024-01-27 a 2026-11-06) e `data/education-platform/database.db`. Verifiquei estaticamente a compatibilidade com o `kaggle 2.2.5` (ver M10). |
| `etl` | ✅ 21,5 s. Gerou `life_cycle`, `fs_transacional`, `fs_education`, `fs_life_cycle` e `fs_all` para `dtRef` 2026-11-09. O `fs_all` saiu com `descLifeCycleD28` 100% nulo (I1). |
| `predict` | ✅ 3.796 scores em `score_fiel`, com um MLflow temporário em `127.0.0.1:5000` servindo a **cópia** do `mlflow.db` e de `mlartifacts`. O servidor já foi desligado. |
| `target.sql` (fora do Makefile) | ✅ 18,4 s; 5.645 linhas e taxa de alvo de 8,89%. O número de datas mudou de 519 para 517 por causa do `random()` (M1). |
| `train.py` (fora do Makefile) | ✅ 26,5 s. Treino: AUC 0,9016 e acurácia 0,929. **Teste: AUC 0,8946**, acurácia 0,931. **OOT: AUC 0,8184**, acurácia 0,889. Reproduz exatamente seus runs de 29/10. |
| API (`api_fiel.py`, via test client) | ✅ `GET /health_check` → 200. `POST /predict` → 200 com `{}` (não implementado). `POST /predict_many` → 404 (não existe). |
| Exploratórios | ✅ `dau.sql`, `mau.sql`, `frequencia_valor.sql`/`.py`, `report_ciclo_vida.sql`, `predict.py`, `s.sql` e `engineering/query.sql` rodaram sem erro. |

Avisos que **não** vêm do seu código e podem ser ignorados: `FutureWarning` do sklearn 1.9 sobre `y_pred → y_proba` (vem do autolog do MLflow), `delayed should be used with Parallel` (MLflow e GridSearch) e o aviso de schema de inteiros do MLflow. Este último só importaria se você servisse o modelo via `pyfunc`; com `mlflow.sklearn.load_model` não há validação de schema.

### 4.3 Lint

| Ferramenta | Seu projeto | Referência |
|---|---|---|
| `python -m py_compile` | ✅ 9/9 arquivos | — |
| `pyflakes` | ✅ **0 avisos** | — |
| `ruff --select F,E,W,B,I` | 28 avisos, **nenhum de código** `F` (erro real). São 14 de import desordenado/espaço em branco (`--fix` resolve), 7 de linha longa, 5 `B018` (expressões soltas, normais em script com `# %%`) e `E402` no `get_data.py` (intencional: o `dotenv` precisa carregar antes do `kaggle`). | 44 avisos, incluindo **`F401 sklearn.tree` importado e não usado** e **2× `F841`** (`err` não usado na API). |

---

## 5. Erros encontrados na **referência** (não copie)

| # | Arquivo da referência | Erro | No seu projeto |
|---|---|---|---|
| R1 | `train.py:239` | `model_pipeline[-1].feature_importances_`: o último passo é um `GridSearchCV`, que **não tem** esse atributo (verificado), então dá `AttributeError`. | ✅ Corrigido: você usa `.best_estimator_` (`train.py:244`). |
| R2 | `train.py:111` | `fill_0 = ['github2025', 'python2025']` fixo. Se `github2025` cair no `to_remove`, o imputador falha. **Nos seus dados ela cai.** | ✅ Corrigido: o filtro em `train.py:103`. |
| R3 | `life_cycle.sql:50-51` | Usa `BETWEEN 15 AND 27` / `> 27`, o que contradiz o próprio comentário (linhas 6-7: "14 <= recência anterior <= 28" / "> 28") e a regra de `04-DESENCANTADA` (15-28). Quem volta depois de exatos 28 dias estava "Desencantada", mas é rotulado "Reborn". | ✅ O seu (`life_cycle.sql:44-45`, 15-28 / >28) está **correto**. Nos seus dados, 708 linhas têm intervalo de exatos 28 dias e você rotula corretamente como `02-Reconquistado`. |
| R4 | `exec_query.py:66,69` | `--mode` é lido do argparse mas **não é repassado** para `exec_query()` e não tem default. O modo `replace` por data também manteria só a última data. | ✅ Corrigido: `--mode` é repassado, e o `replace` faz `DROP` uma vez e depois `append`. |
| R5 | `Makefile:28-29, 38-39, 47-48` | `. .venv/bin/activate` sozinho numa linha de receita não vale para as linhas seguintes (cada linha roda em outro shell), então os scripts rodam com o Python do sistema. O `setup` (linha 21) roda `pipreqs --force`, que **sobrescreve o `requirements.txt` fixado** a cada setup. | ✅ Seu Makefile usa `$(PYTHON)` explícito e instala o `requirements.txt` fixado. |
| R6 | `api_fiel.py:25,27-28` | `float(predict)` dá `TypeError` no NumPy 2.5.2, e o `except` genérico esconde o erro (seção 3). | ⏳ Ainda não implementado no seu; use `float(predict[0])`. |
| R7 | `fs_education.sql:4`, `target.sql:11`, `train.py:54-59` | Mesmos problemas que I4, M1 e I2. | Ver I4, M1 e I2. |

---

## Apêndice A: mapeamento (Etapa 1)

### A.1 Arquivos (sem contar `.git`, `.conda`, dados e caches)

| Situação | Arquivos |
|---|---|
| **Nos dois** | `.gitignore`, `Makefile`, `README.md`, `requirements.txt`, `data/.gitkeep`, `img/loyalty_predict_canva.png` (o seu é ignorado no git); `src/analytics/`: `dau.sql`, `mau.sql`, `exec_query.py`, `pipeline_analytics.py`, `life_cycle.sql`, `frequencia_valor.sql`, `frequencia_valor.py`, `fs_transacional.sql`, `fs_education.sql`, `fs_life_cycle.sql`, `fs_all.sql`, `target.sql`, `report_ciclo_vida.sql`, `train.py`, `predict_fiel.py`; `src/api/api_fiel.py`; `src/engineering/get_data.py` |
| **Só no seu** | `docs/Relatorio_Analise_Loyalty_Predict.docx`, `src/analytics/predict.py` (escora a ABT; exploratório), `src/analytics/curva_roc.png` (versionado), `src/analytics/s.sql`, `src/api/import requests.py`, `src/engineering/query.sql`. Ignorados pelo git: `src/.env`, `src/kaggle.json`, `src/analytics/model_fiel.pkl`, `database.db` (raiz), `mlflow.db`, `mlartifacts/`, `data/loyalty-system/query.sql`, `*.session.sql`, `.vscode/`, `.claude/` |
| **Só na referência** | `LICENSE` |
| Notebooks (`.ipynb`) | Nenhum nos dois. Os dois usam scripts com células `# %%`. |

**Git:** há bastante trabalho não commitado: `Makefile`, `fs_all.sql`, `pipeline_analytics.py`, `predict_fiel.py`, `src/api/` e `src/engineering/` estão sem rastreamento, e `requirements.txt`, `exec_query.py` e `report_ciclo_vida.sql` estão modificados. A alteração no `report_ciclo_vida.sql` **corrige um bug** da versão commitada: `cluster` estava no `SELECT` sem estar no `GROUP BY`.

### A.2 `requirements.txt`

| Pacote | Seu | Referência | Observação |
|---|---|---|---|
| flask | 3.1.3 | — | Necessário para a API. Na referência vem só como dependência do mlflow; listar explicitamente é melhor. |
| numpy | 2.5.2 | — | Explícito, o que é bom. Atenção ao `float(array)` (R6). |
| kaggle | 2.2.5 | 1.7.4.5 | Versão major nova; seu `get_data.py` é compatível (ver M10). |
| pandas | 3.0.5 | 2.3.3 | Versão major nova (Copy-on-Write, dtype string); tudo rodou. |
| scikit-learn | 1.9.0 | 1.7.2 | Igual à versão do modelo registrado. |
| mlflow | 3.17.2 | 3.4.0 | Igual à versão do `mlflow.db`. |
| feature-engine / matplotlib / python-dotenv / SQLAlchemy / tqdm | 1.9.4 / 3.11.1 / 1.2.4 / 2.0.52 / 4.70.1 | 1.9.3 / 3.10.7 / 1.1.1 / 2.0.44 / 4.67.1 | Diferenças minor ou patch. |
| seaborn | 0.13.2 | 0.13.2 | Igual. |
| mlflow_skinny, mlflow_tracing | — | 3.4.0 | Dependências transitivas do mlflow; não precisa listar. |
| requests | — | — | Usado em `import requests.py`; hoje só vem como transitiva. Adicione se o cliente de teste continuar. |

### A.3 Makefile

| Alvo | Seu | Referência |
|---|---|---|
| `setup` | conda em `./.conda` (Python 3.14) e `pip install -r requirements.txt` fixado | `rm -rf .venv`, venv, `pipreqs --force` (sobrescreve o requirements) e install |
| `collect` / `etl` / `predict` | Mesmos comandos, com `$(PYTHON)` explícito ✅ | `activate` numa linha separada, que não tem efeito (R5) |
| `run` | `collect etl` (só no seu) | — |
| `all` | `setup collect etl predict` | Igual |
| ABT / treino / API | Não existem | Não existem |

### A.4 Caminhos, bancos e tabelas
- **Caminhos:** `data/{loyalty-system, education-platform, analytics}/database.db`, iguais aos da referência. Todos relativos (rodar de `src/analytics`); nenhum caminho absoluto no código.
- **Tabelas:** `life_cycle`, `fs_transacional`, `fs_education`, `fs_life_cycle`, `fs_all`, `abt_fiel` e `score_fiel`, com os mesmos nomes da referência.
- **`.env`:** você usa `src/.env` (`get_data.py:5` carrega `'../.env'`); a referência usa `.env` na raiz. As variáveis são `KAGGLE_USERNAME` e `KAGGLE_KEY` (comparei só os nomes). Ambos são coerentes com o próprio código.

---

## Apêndice B: comparação arquivo por arquivo (Etapa 2)

Legenda: **=** equivalente; **≠ ok** implementado de forma diferente e correto; **≠ ✗** implementado errado; **⏳** ainda não implementado.

| Arquivo | Classificação | Detalhe |
|---|---|---|
| `dau.sql` | ≠ ok | Mesma métrica; ordena por DAU decrescente em vez de por data. |
| `mau.sql` | ≠ ok | Mesma janela de 28 dias (`<=` / `< 28`). Não tem a coluna `qtdeDias` da referência, útil para ver o período de aquecimento; tem `DESC LIMIT 100`. |
| `life_cycle.sql` | ≠ ok | Rótulos em formato de título, usados de forma consistente; fronteira 28 **correta** (R3); `COALESCE` de frequência e cluster só afeta zumbis, que ficam fora da ABT; coluna extra `dtPrimTransacao`, inofensiva. Reproduz o salvo em 100%. |
| `frequencia_valor.sql` | ≠ ✗ (leve) | Mesma lógica; rótulos divergentes e erro de digitação em `20s-POTENCIAL` (M13). |
| `frequencia_valor.py` | ≠ ok | Usa `Path(__file__)` (mais robusto); não plota o KMeans (M13). |
| `fs_transacional.sql` | ≠ ok | Lógica idêntica (janelas, `DISTINCT`, `LEFT JOIN`s); só nomes diferentes (`qtdeTransacoesVida`, `qtdTransacaoManha/Tarde/Noite`, `qtdeTransacaoDia*`), consistentes no seu pipeline. |
| `fs_education.sql` | = (com o bug da referência) | Lógica idêntica, incluindo o `COUNT` sem `DISTINCT` (I4); nome `qtdDiasUltimaAtividade`. |
| `fs_life_cycle.sql` | ≠ ok | Idêntico; `NULLIF` no `ratioFreqGrupo` é equivalente (no SQLite, divisão por zero já dá `NULL`). |
| `fs_all.sql` | = | Idêntico, com os seus nomes de coluna. |
| `target.sql` | ≠ ok | Idêntico; você nomeia `descLifeCycleAtual`/`D28` dentro da CTE (a referência deixa duas colunas com o mesmo nome). |
| `report_ciclo_vida.sql` | = | Igual à referência, já com a correção do `cluster`. |
| `exec_query.py` | ≠ ok (melhor) | Corrige R4; sobra de teste na linha 28 (M7). |
| `pipeline_analytics.py` | = | Idêntico (e com a mesma fragilidade, I1). |
| `train.py` | ≠ ok | RandomForest com grid (`n_estimators` × `min_samples_leaf`) em vez de AdaBoost (`n_estimators` × `learning_rate`), válido. Corrige R1 e R2. Sem baseline (M9). Split por linha (I2), igual à referência. |
| `predict_fiel.py` | = | Idêntico (só a URI). |
| `api_fiel.py` | ⏳ | `/health_check` OK; `/predict` é esboço; `/predict_many` não existe. |
| `get_data.py` | ≠ ok | `.env` em `src/`; usa `path=` em vez de `shutil.move`, compatível com o `kaggle 2.2.5` (M10). |

---

*Para refazer esta auditoria: a cópia usada na execução está em `/private/tmp/claude-501/-Users-vitorfernandes-Documents-mesa-loyalty-predict-main-vitor/085fb566-ae60-4336-9d77-7100ecd29e54/scratchpad/run` e os scripts de checagem estão em `/private/tmp/claude-501/-Users-vitorfernandes-Documents-mesa-loyalty-predict-main-vitor/085fb566-ae60-4336-9d77-7100ecd29e54/scratchpad/`. Os dois podem ser apagados.*
