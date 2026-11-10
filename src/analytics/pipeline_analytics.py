# %%
from exec_query import exec_query

import datetime

import sqlalchemy

now = datetime.datetime.now().strftime("%Y-%m-%d")


def get_start(table, db_target):
    # retoma do dia seguinte ao último dtRef salvo, para não deixar buraco de datas
    # quando o pipeline fica dias sem rodar (o dia de hoje é sempre recalculado)
    engine = sqlalchemy.create_engine(f"sqlite:///../../data/{db_target}/database.db")
    try:
        with engine.connect() as con:
            last_dt_ref = con.execute(sqlalchemy.text(f"SELECT max(dtRef) FROM {table}")).scalar()
    except sqlalchemy.exc.OperationalError:
        # tabela ainda não existe: calcula só hoje
        return now

    if last_dt_ref is None:
        return now

    # o exec_query grava dtRef = data - 1 dia, então o próximo dtRef pede data = último dtRef + 2 dias
    next_start = datetime.datetime.strptime(last_dt_ref, "%Y-%m-%d") + datetime.timedelta(days=2)
    return min(next_start.strftime("%Y-%m-%d"), now)


steps = [
    {
        "table": "life_cycle",
        "db_origin": "loyalty-system",
        "db_target": "analytics",
        "dt_start": now,
        "dt_stop": now,
        "monthly": False,
        "mode": "append",
    },
    {
        "table": "fs_transacional",
        "db_origin": "loyalty-system",
        "db_target": "analytics",
        "dt_start": now,
        "dt_stop": now,
        "monthly": False,
        "mode": "append",
    },
    {
        "table": "fs_education",
        "db_origin": "education-platform",
        "db_target": "analytics",
        "dt_start": now,
        "dt_stop": now,
        "monthly": False,
        "mode": "append",
    },
    {
        "table": "fs_life_cycle",
        "db_origin": "analytics",
        "db_target": "analytics",
        "dt_start": now,
        "dt_stop": now,
        "monthly": False,
        "mode": "append",
    },
    {
        "table": "fs_all",
        "db_origin": "analytics",
        "db_target": "analytics",
        "dt_start": now,
        "dt_stop": now,
        "monthly": False,
        "mode": "replace",
    },
]

for s in steps:
    if s["mode"] == "append":
        s["dt_start"] = get_start(s["table"], s["db_target"])
    print(f"{s['table']}: {s['dt_start']} -> {s['dt_stop']}")
    exec_query(**s)
# %%
