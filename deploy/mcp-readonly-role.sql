\set ON_ERROR_STOP on

\if :{?visionq_mcp_password}
\else
\echo 'Set -v visionq_mcp_password=... without using shell history or committed files.'
\quit
\endif

SELECT format(
    'CREATE ROLE visionq_mcp LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION',
    :'visionq_mcp_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'visionq_mcp')
\gexec

SELECT format(
    'ALTER ROLE visionq_mcp PASSWORD %L',
    :'visionq_mcp_password'
)
\gexec

ALTER ROLE visionq_mcp SET default_transaction_read_only = on;
ALTER ROLE visionq_mcp SET statement_timeout = '5s';
GRANT CONNECT ON DATABASE :"DBNAME" TO visionq_mcp;
REVOKE CREATE ON SCHEMA public FROM visionq_mcp;
GRANT USAGE ON SCHEMA public TO visionq_mcp;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO visionq_mcp;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO visionq_mcp;
