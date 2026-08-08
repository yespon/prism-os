#!/usr/bin/env bash
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
source "$REPO_ROOT/scripts/prismos-env.sh"

DB_TYPE=$(python3 -c "
import yaml
with open('$PRISMOS_CONFIG_PATH', 'r') as f:
    cfg = yaml.safe_load(f)
db = cfg.get('database', {})
print(db.get('type', 'sqlite'))
" 2>/dev/null || echo "sqlite")

if [ "$DB_TYPE" != "postgres" ]; then
    echo "Database type is '$DB_TYPE', no manual creation needed (SQLite auto-creates files)."
    exit 0
fi

echo ""
echo "========================================"
echo "  Create PostgreSQL Databases"
echo "========================================"
echo ""

create_db() {
    local host=$1 port=$2 user=$3 db=$4 password=$5
    export PGPASSWORD="$password"
    exists=$(psql -h "$host" -p "$port" -U "$user" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$db'" 2>/dev/null)
    if [ "$exists" = "1" ]; then
        echo "  $db — already exists"
    else
        psql -h "$host" -p "$port" -U "$user" -d postgres -c "CREATE DATABASE \"$db\"" 2>&1
        echo "  $db — created"
    fi
}

TENANT_URL=$(python3 -c "
import yaml, urllib.parse
with open('$PRISMOS_CONFIG_PATH', 'r') as f:
    cfg = yaml.safe_load(f)
url = cfg['database']['url']
parsed = urllib.parse.urlparse(url.replace('postgresql+asyncpg', 'postgresql'))
print(f'host={parsed.hostname} port={parsed.port or 5432} user={parsed.username} dbname={parsed.path.lstrip(\"/\")} password={parsed.password}')
" 2>/dev/null)

AUTH_URL=$(python3 -c "
import yaml, urllib.parse
with open('$PRISMOS_CONFIG_PATH', 'r') as f:
    cfg = yaml.safe_load(f)
url = cfg['database']['auth']['url']
parsed = urllib.parse.urlparse(url.replace('postgresql+asyncpg', 'postgresql'))
print(f'host={parsed.hostname} port={parsed.port or 5432} user={parsed.username} dbname={parsed.path.lstrip(\"/\")} password={parsed.password}')
" 2>/dev/null)

CHECKPOINT_URL=$(python3 -c "
import yaml, urllib.parse
with open('$PRISMOS_CONFIG_PATH', 'r') as f:
    cfg = yaml.safe_load(f)
cp = cfg.get('checkpointer', {})
if cp.get('type') == 'postgres':
    url = cp.get('connection_string', '')
    if url:
        parsed = urllib.parse.urlparse(url)
        print(f'host={parsed.hostname} port={parsed.port or 5432} user={parsed.username} dbname={parsed.path.lstrip(\"/\")} password={parsed.password}')
" 2>/dev/null)

eval "$TENANT_URL"
create_db "$host" "$port" "$user" "$dbname" "$password"

eval "$AUTH_URL"
create_db "$host" "$port" "$user" "$dbname" "$password"

if [ -n "$CHECKPOINT_URL" ]; then
    eval "$CHECKPOINT_URL"
    create_db "$host" "$port" "$user" "$dbname" "$password"
fi

echo ""
echo "Tables will be auto-created by the gateway on startup."
echo "Done."
