SELECT dtRef,
       descLifeCycle,
       count(*) AS qtdeCliente

FROM life_cycle

WHERE descLifeCycle <> '05-Zumbi'
AND dtRef = (SELECT MAX(dtRef) FROM life_cycle)

GROUP BY dtRef, descLifeCycle
ORDER BY dtRef, descLifeCycle
