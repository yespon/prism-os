-- Create the three databases used by the application.
-- These names must match config.yaml's database section.
-- PostgreSQL Docker entrypoint runs scripts in /docker-entrypoint-initdb.d/
-- only on FIRST startup (when the data directory is empty).

-- Platform database (tenant data, user configs, MCP servers, skills, models)
CREATE DATABASE prismos_tenant_db;

-- Auth database (Better Auth identity tables: users, accounts, sessions)
CREATE DATABASE prismos_auth_db;

-- Checkpoint database (LangGraph state persistence)
CREATE DATABASE prismos_checkpoints;
