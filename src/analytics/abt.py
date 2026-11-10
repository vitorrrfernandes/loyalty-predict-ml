# %%
import pandas as pd
import sqlalchemy

con = sqlalchemy.create_engine("sqlite:///../../data/analytics/database.db")


def import_query(path):
    with open(path) as open_file:
        return open_file.read()


# %%
# cohort completo (todas as datas de cada cliente fora do Zumbi), já com o alvo e as features
df = pd.read_sql(import_query("target.sql"), con)

# %%
# até 2 datas por cliente, sempre as mesmas: embaralha com semente fixa
# e fica com as 2 primeiras linhas de cada cliente
df_abt = (
    df.sample(frac=1, random_state=42)
    .groupby("IdCliente")
    .head(2)
    .sort_values(["IdCliente", "dtRef"])
    .reset_index(drop=True)
)

print(
    f"ABT: {df_abt.shape[0]} linhas | {df_abt['IdCliente'].nunique()} clientes | "
    f"{df_abt['dtRef'].nunique()} datas | Tx. alvo {100 * df_abt['flFiel'].mean():.2f}%"
)

# %%
df_abt.to_sql("abt_fiel", con, index=False, if_exists="replace")
# %%
