-- Ciclo de vida de cada cliente. O snapshot é gravado com dtRef = data de execução - 1 dia
-- e usa só transações anteriores à data de execução.
--
-- Medidas (em dias, contadas a partir da data de execução)
--   idade      = dias desde a primeira transação (qtdeDiasPrimTransacao)
--   recência   = dias desde a última transação (qtdeDiasUltmTransacao)
--   intervalo  = dias entre a penúltima e a última ativação
--                (qtdeDiasPenultimaAtivacao - qtdeDiasUltmTransacao), ou seja,
--                a recência que o cliente tinha logo antes de voltar
--
-- Regras, avaliadas nesta ordem (vale a primeira que bater)
--   01-CURIOSO        -> idade <= 7
--   02-FIEL           -> recência <= 7 e intervalo <= 14
--   03-Turista        -> recência entre 8 e 14
--   04-Desencantada   -> recência entre 15 e 28
--   05-Zumbi          -> recência > 28
--   02-Reconquistado  -> recência <= 7 e intervalo entre 15 e 28 (voltou depois de estar Desencantada)
--   02-Reborn         -> recência <= 7 e intervalo > 28 (voltou depois de estar Zumbi)
--
-- A fronteira de Reconquistado/Reborn é 28 dias, a mesma de Desencantada/Zumbi. Quem volta
-- depois de exatos 28 dias estava Desencantada, então é Reconquistado (o projeto original usa 27).

WITH tb_daily AS (
    SELECT DISTINCT
        IdCliente,
        substr(DtCriacao, 1, 10) AS DtDia
    FROM transacoes
    WHERE DtCriacao < date('{date}')
),

tb_idade AS (
    SELECT
        IdCliente,
        min(DtDia)                                               AS dtPrimTransacao,
        cast(max(julianday('{date}') - julianday(DtDia)) AS int)    AS qtdeDiasPrimTransacao,
        cast(min(julianday('{date}') - julianday(DtDia)) AS int)    AS qtdeDiasUltmTransacao
    FROM tb_daily
    GROUP BY IdCliente
),

tb_rn AS (
    SELECT
        *,
        row_number() OVER (PARTITION BY IdCliente ORDER BY dtDia DESC) AS rn
    FROM tb_daily
),

tb_penultima_ativacao AS (
    SELECT
        *,
        cast((julianday('{date}') - julianday(DtDia)) AS int) AS qtdeDiasPenultimaAtivacao
    FROM tb_rn
    WHERE rn = 2
),

tb_life_cycle AS (
    SELECT
        t1.*,
        t2.qtdeDiasPenultimaAtivacao,
        CASE
            WHEN qtdeDiasPrimTransacao <= 7                                                                    THEN '01-CURIOSO'
            WHEN qtdeDiasUltmTransacao <= 7 AND qtdeDiasPenultimaAtivacao - qtdeDiasUltmTransacao <= 14       THEN '02-FIEL'
            WHEN qtdeDiasUltmTransacao BETWEEN 8 AND 14                                                       THEN '03-Turista'
            WHEN qtdeDiasUltmTransacao BETWEEN 15 AND 28                                                      THEN '04-Desencantada'
            WHEN qtdeDiasUltmTransacao > 28                                                                   THEN '05-Zumbi'
            WHEN qtdeDiasUltmTransacao <= 7 AND qtdeDiasPenultimaAtivacao - qtdeDiasUltmTransacao BETWEEN 15 AND 28 THEN '02-Reconquistado'
            WHEN qtdeDiasUltmTransacao <= 7 AND qtdeDiasPenultimaAtivacao - qtdeDiasUltmTransacao > 28        THEN '02-Reborn'
        END AS descLifeCycle
    FROM tb_idade AS t1
    LEFT JOIN tb_penultima_ativacao AS t2
        ON t1.IdCliente = t2.IdCliente
),

tb_freq_valor AS (

    SELECT IdCliente,
        count(DISTINCT substr(DtCriacao,0,11)) AS qtdeFrequencia,
        sum(CASE WHEN QtdePontos > 0 THEN QtdePontos  ELSE 0 END) as qtdePontosPos

    FROM transacoes

    WHERE DtCriacao < date('{date}')
    AND DtCriacao >= date('{date}', '-28 days')

    GROUP BY idCliente
    ORDER BY qtdeFrequencia DESC

),

tb_cluster AS (

    SELECT *,
            CASE
                WHEN qtdeFrequencia <= 10 AND qtdePontosPos >= 1500 THEN '12-HYPER'
                WHEN qtdeFrequencia > 10 AND qtdePontosPos >= 1500 THEN '22-EFICIENTE'
                WHEN qtdeFrequencia <= 10 AND qtdePontosPos >= 750 THEN '11-INDECISO'
                WHEN qtdeFrequencia > 10 AND qtdePontosPos >= 750 THEN '21-ESFORÇADO'
                WHEN qtdeFrequencia < 5 THEN '00-LURKER'
                WHEN qtdeFrequencia <= 10 THEN '01-PREGUIÇOSO'
                WHEN qtdeFrequencia > 10 THEN '20-POTENCIAL'
            END AS cluster

    FROM tb_freq_valor

)


SELECT
       date('{date}', '-1 day')                  AS dtRef,
       t1.*,
       COALESCE(t2.qtdeFrequencia, 0)         AS qtdeFrequencia,
       COALESCE(t2.qtdePontosPos, 0)          AS qtdePontosPos,
       COALESCE(t2.cluster, '00-LURKER')      AS cluster
FROM tb_life_cycle AS t1

LEFT JOIN tb_cluster AS t2
ON t1.IdCliente = t2.IdCliente
