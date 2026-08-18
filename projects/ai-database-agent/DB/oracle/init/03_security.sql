-- Reconnect to the pluggable database as administrator; owner objects are exposed to two test users.
CONNECT SYSTEM/LocalSys_2026_TestOnly@//localhost:1521/FREEPDB1
DECLARE
  PROCEDURE ensure_user(p_user VARCHAR2, p_password VARCHAR2) IS
    n NUMBER;
  BEGIN
    SELECT COUNT(*) INTO n FROM dba_users WHERE username=UPPER(p_user);
    IF n=0 THEN EXECUTE IMMEDIATE 'CREATE USER '||p_user||' IDENTIFIED BY "'||p_password||'"'; END IF;
    EXECUTE IMMEDIATE 'GRANT CREATE SESSION TO '||p_user;
  END;
BEGIN
  ensure_user('AI_READER','Reader_2026_TestOnly');
  ensure_user('AI_WRITER','Writer_2026_TestOnly');
END;
/
BEGIN
  FOR t IN (SELECT table_name FROM all_tables WHERE owner='LOGISTICS_APP') LOOP
    EXECUTE IMMEDIATE 'GRANT SELECT ON LOGISTICS_APP.'||t.table_name||' TO AI_READER';
    EXECUTE IMMEDIATE 'GRANT SELECT, INSERT, UPDATE, DELETE ON LOGISTICS_APP.'||t.table_name||' TO AI_WRITER';
    EXECUTE IMMEDIATE 'CREATE OR REPLACE SYNONYM AI_READER.'||t.table_name||' FOR LOGISTICS_APP.'||t.table_name;
    EXECUTE IMMEDIATE 'CREATE OR REPLACE SYNONYM AI_WRITER.'||t.table_name||' FOR LOGISTICS_APP.'||t.table_name;
  END LOOP;
END;
/
