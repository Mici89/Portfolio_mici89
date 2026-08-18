CONNECT LOGISTICS_APP/Logistics_2026_TestOnly@//localhost:1521/FREEPDB1
SELECT 'tables' metric, COUNT(*) value FROM user_tables;
SELECT 'waybills' metric, COUNT(*) value FROM T_YD01;
SELECT 'packages' metric, COUNT(*) value FROM PACKAGE_ITEM;
SELECT 'tracking' metric, COUNT(*) value FROM PS_GJ;
SELECT ZT, COUNT(*) FROM T_YD01 GROUP BY ZT ORDER BY ZT;
