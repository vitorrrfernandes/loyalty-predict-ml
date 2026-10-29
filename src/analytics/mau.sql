WITH tb_daily AS (
    SELECT DISTINCT date(substr(DtCriacao,1,10)) AS dtDia,
    IdCliente 
    FROM transacoes 
),

tb_distinct_day AS (
SELECT DISTINCT dtDia AS dtRef
FROM tb_daily  
)

SELECT t1.dtRef, count( distinct IdCliente) AS mau
FROM tb_distinct_day AS t1
LEFT JOIN tb_daily AS t2
ON t2.dtDia <= t1.dtRef
AND julianday(t1.dtRef) - julianday(t2.dtDia) < 28

GROUP BY t1.dtRef
ORDER BY t1.dtRef DESC

LIMIT 100