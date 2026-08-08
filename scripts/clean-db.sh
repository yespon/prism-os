#!/usr/bin/env bash
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
source "$REPO_ROOT/scripts/prismos-env.sh"

# ── Read config.yaml to determine database type ──────────────────────────────
DB_TYPE=$(python3 -c "
import yaml
with open('$PRISMOS_CONFIG_PATH', 'r') as f:
    cfg = yaml.safe_load(f)
db = cfg.get('database', {})
print(db.get('type', 'sqlite'))
" 2>/dev/null || echo "sqlite")

PRISMOS_DIR="$PRISMOS_HOME"

echo ""
echo "========================================"
echo "  Database Cleanup"
echo "  Detected type: $DB_TYPE"
echo "========================================"
echo ""

# ── PostgreSQL ───────────────────────────────────────────────────────────────
if [ "$DB_TYPE" = "postgres" ]; then
    echo "Reading PostgreSQL connection info from config.yaml..."

    TENANT_URL=$(python3 -c "
import yaml, urllib.parse
with open('$PRISMOS_CONFIG_PATH', 'r') as f:
    cfg = yaml.safe_load(f)
url = cfg['database']['url']
# parse: postgresql+asyncpg://user:pass@host:port/dbname
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
        parsed = urllib.parse.urlparse(url.replace('postgresql://', 'postgresql://') if '://' in url else url)
        print(f'host={parsed.hostname} port={parsed.port or 5432} user={parsed.username} dbname={parsed.path.lstrip(\"/\")} password={parsed.password}')
" 2>/dev/null)

    if [ -z "$TENANT_URL" ]; then
        echo "ERROR: Could not parse config.yaml database settings."
        exit 1
    fi

    eval "$TENANT_URL"
    TENANT_HOST=$host TENANT_PORT=$port TENANT_USER=$user TENANT_DB=$dbname TENANT_PASSWORD=$password

    eval "$AUTH_URL"
    AUTH_HOST=$host AUTH_PORT=$port AUTH_USER=$user AUTH_DB=$dbname AUTH_PASSWORD=$password

    echo ""
    echo "The following PostgreSQL databases will be dropped:"
    echo "  - $TENANT_DB (tenant data)"
    echo "  - $AUTH_DB (auth data)"
    if [ -n "$CHECKPOINT_URL" ]; then
        eval "$CHECKPOINT_URL"
        CK_HOST=$host CK_PORT=$port CK_USER=$user CK_DB=$dbname CK_PASSWORD=$password
        echo "  - $CK_DB (checkpoints)"
    fi
    echo ""

    read -rp "Are you sure? Type 'yes' to confirm: " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Aborted."
        exit 0
    fi

    drop_db() {
        local host=$1 port=$2 user=$3 db=$4 password=$5
        export PGPASSWORD="$password"
        psql -h "$host" -p "$port" -U "$user" -d postgres -c "SELECT pg_terminate_backend(pg_stat_activity.pid) FROM pg_stat_activity WHERE pg_stat_activity.datname = '$db' AND pid <> pg_backend_pid()" > /dev/null 2>&1
        psql -h "$host" -p "$port" -U "$user" -d postgres -c "DROP DATABASE IF EXISTS \"$db\"" 2>&1 || {
            echo "WARNING: Could not drop $db (may not exist)"
        }
    }

    drop_db "$TENANT_HOST" "$TENANT_PORT" "$TENANT_USER" "$TENANT_DB" "$TENANT_PASSWORD"
    drop_db "$AUTH_HOST" "$AUTH_PORT" "$AUTH_USER" "$AUTH_DB" "$AUTH_PASSWORD"

    if [ -n "$CHECKPOINT_URL" ]; then
        drop_db "$CK_HOST" "$CK_PORT" "$CK_USER" "$CK_DB" "$CK_PASSWORD"
    fi

    unset PGPASSWORD

    echo ""
    echo "PostgreSQL databases dropped."
fi

# ── SQLite cleanup ───────────────────────────────────────────────────────────
if [ "$DB_TYPE" = "sqlite" ]; then
    FILES=(
        "$PRISMOS_DIR/tenant.db"
        "$PRISMOS_DIR/auth.db"
        "$PRISMOS_DIR/checkpoints.db"
    )

    EXISTING=()
    for f in "${FILES[@]}"; do
        if [ -f "$f" ]; then
            EXISTING+=("$f")
        fi
    done

    if [ ${#EXISTING[@]} -eq 0 ]; then
        echo "No SQLite database files found."
    else
        echo "The following SQLite database files will be deleted:"
        for f in "${EXISTING[@]}"; do
            echo "  - $f"
        done
        echo ""

        read -rp "Are you sure? Type 'yes' to confirm: " confirm
        if [ "$confirm" != "yes" ]; then
            echo "Aborted."
            exit 0
        fi

        for f in "${EXISTING[@]}"; do
            rm -f "$f"
            echo "Deleted: $f"
        done
        echo ""
        echo "SQLite database files deleted."
    fi
fi

# ── Check for leftover SQLite files ──────────────────────────────────────────
REMAINING=()
for f in "$PRISMOS_DIR/tenant.db" "$PRISMOS_DIR/auth.db" "$PRISMOS_DIR/checkpoints.db"; do
    if [ -f "$f" ]; then
        REMAINING+=("$f")
    fi
done

if [ ${#REMAINING[@]} -gt 0 ]; then
    echo ""
    echo "Found leftover SQLite files (possibly from previous runs):"
    for f in "${REMAINING[@]}"; do
        echo "  - $f"
    done
    read -rp "Delete these files? Type 'yes' to confirm: " confirm
    if [ "$confirm" = "yes" ]; then
        for f in "${REMAINING[@]}"; do
            rm -f "$f"
            echo "Deleted: $f"
        done
    else
        echo "Kept."
    fi
fi

echo ""
echo "Done."
