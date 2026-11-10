# %%
# Monitoramento: compara o score de cada dtRef com o ciclo de vida real 28 dias depois.
# Só entram os dtRef que já "venceram", ou seja, cujo life_cycle de dtRef + 28 já existe.

import pandas as pd
import sqlalchemy
from sklearn import metrics

con = sqlalchemy.create_engine("sqlite:///../../data/analytics/database.db")

query = """
SELECT t1.dtRef,
       t1.versaoModelo,
       t1.IdCliente,
       t1.predictFiel,
       CASE WHEN t2.descLifeCycle = '02-FIEL' THEN 1 ELSE 0 END AS flFiel

FROM score_fiel AS t1

INNER JOIN life_cycle AS t2
ON t1.IdCliente = t2.IdCliente
AND date(t1.dtRef, '+28 day') = t2.dtRef
"""

# %%
df = pd.read_sql(query, con)

if df.empty:
    primeiro = pd.read_sql("SELECT min(dtRef) AS dtRef FROM score_fiel", con)["dtRef"].iloc[0]
    print("Nenhum score com D+28 disponível ainda.")
    if primeiro:
        vence = pd.Timestamp(primeiro) + pd.Timedelta(days=28)
        print(f"O primeiro ({primeiro}) poderá ser conferido quando existir o life_cycle de {vence:%Y-%m-%d}.")

else:
    linhas = []
    for (dt_ref, versao), g in df.groupby(["dtRef", "versaoModelo"]):
        # a AUC só existe se houver fiéis e não fiéis no grupo
        auc = metrics.roc_auc_score(g["flFiel"], g["predictFiel"]) if g["flFiel"].nunique() == 2 else float("nan")
        linhas.append({
            "dtRef": dt_ref,
            "versaoModelo": versao,
            "clientes": len(g),
            "txFielReal": g["flFiel"].mean(),
            "scoreMedio": g["predictFiel"].mean(),
            "auc": auc,
        })
    print(pd.DataFrame(linhas).round(4).to_string(index=False))
# %%
