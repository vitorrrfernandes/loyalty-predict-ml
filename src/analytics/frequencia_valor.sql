WITH tb_freq_valor AS 
(SELECT IdCliente, 
count(DISTINCT substr(DtCriacao,1,10)) AS freq,
sum(CASE WHEN qtdePontos > 0 THEN qtdePontos ELSE 0 END) AS qtdePontos
FROM transacoes 
WHERE DtCriacao < '2025-09-01'
AND DtCriacao >= date('2025-09-01', '-28 days')
GROUP BY IdCliente
order by freq DESC
),


tb_cluster AS (SELECT *,
    CASE
        WHEN freq <= 10 AND qtdePontos >= 1500 THEN '12-HYPERS'
        WHEN freq > 10 AND qtdePontos >= 1500 THEN '22-EFICIENTE'
        WHEN freq <= 10 AND qtdePontos >= 750 THEN '11-INDECISO'
        WHEN freq > 10 AND qtdePontos >= 750 THEN '21-ESFORCADO'
        WHEN freq < 5 THEN '00-LURKER'
        WHEN freq <= 10 THEN '01-PREGUICOSO'
        WHEN freq > 10 THEN '20s-POTENCIAL' END AS cluster
FROM tb_freq_valor

)

SELECT * FROM tb_cluster
