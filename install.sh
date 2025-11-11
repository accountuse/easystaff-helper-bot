#!/usr/bin/env bash
set -Eeuo pipefail

# Prevent multiple instances from running simultaneously
exec 200>/var/lock/easystaff-installer.lock
flock -n 200 || { echo -e "\033[38;5;196m[ERR]\033[0m Another installer instance is already running." >&2; exit 1; }

# ------------- Colors and formatting -------------
is_tty() { [[ -t 1 ]]; }
if is_tty && [[ -z "${NO_COLOR:-}" ]]; then
  BOLD="\033[1m"; DIM="\033[2m"; RESET="\033[0m"
  FG_GREEN="\033[38;5;46m"; FG_BLUE="\033[38;5;33m"; FG_CYAN="\033[38;5;45m"
  FG_YELLOW="\033[38;5;220m"; FG_RED="\033[38;5;196m"; FG_GRAY="\033[38;5;244m"
else
  BOLD=""; DIM=""; RESET=""
  FG_GREEN=""; FG_BLUE=""; FG_CYAN=""
  FG_YELLOW=""; FG_RED=""; FG_GRAY=""
fi

timestamp(){ date +"%H:%M:%S"; }

title(){  echo -e "${BOLD}${FG_BLUE}========== $* ==========${RESET}"; }
section(){ echo -e "${BOLD}${FG_CYAN}--- $* ---${RESET}"; }
log(){    echo -e "${FG_GREEN}[OK]${RESET}   ${msg_prefix-}$*"; }
info(){   echo -e "${FG_BLUE}[INFO]${RESET} ${msg_prefix-}$*"; }
warn(){   echo -e "${FG_YELLOW}[WARN]${RESET} ${msg_prefix-}$*"; }
err(){    echo -e "${FG_RED}[ERR]${RESET}  ${msg_prefix-}$*" >&2; }
# msg_prefix="[${FG_GRAY}$(timestamp)${RESET}] "

# Confirmation prompt (y/yes/д/да; case and whitespace insensitive)
ask_yn(){
  local prompt="$1"; local default="${2:-y}"; local a
  while true; do
    read -rp "$(echo -e "${FG_BLUE}[?]${RESET} ${prompt} [y/n] (default: ${default}): ")" a < /dev/tty
    a="${a:-$default}"
    a="$(printf '%s' "$a" | tr '[:upper:]' '[:lower:]' | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"
    case "$a" in
      y|yes|д|да) return 0 ;;            # accept EN/RU yes-forms
      n|no|н|нет) return 1 ;;            # reject EN/RU no-forms
      *) warn "Answer not recognized. Enter y/n." ;;
    esac
  done
}

require_root(){ [[ $EUID -eq 0 ]] || { err "Run as root (sudo)."; exit 1; } }

# ------------- .env file operations -------------
env_get(){
  local file="$1" key="$2"
  local line val
  line="$(grep -E "^${key}=" "$file" | tail -n1 || true)" || true
  [[ -z "$line" ]] && { echo ""; return 0; }
  val="${line#${key}=}"
  val="${val%$'\r'}"
  val="${val%\"}"; val="${val#\"}"
  val="${val%\'}"; val="${val#\'}"
  val="${val#"${val%%[![:space:]]*}"}"
  val="${val%"${val##*[![:space:]]}"}"
  echo "$val"
}

set_env_kv(){
  local file="$1" key="$2" val="$3"
  if grep -qE "^${key}=" "$file"; then
    sed -i -E "s|^${key}=.*|${key}=${val}|g" "$file"
  else
    echo "${key}=${val}" >> "$file"
  fi
}

# ------------- Docker installation (production) -------------
detect_distro(){
  if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    echo "${ID:-unknown}:${VERSION_ID:-}:${VERSION_CODENAME:-}"
  else
    echo "unknown::"
  fi
}

docker_present(){ command -v docker >/dev/null 2>&1; }
compose_v2_present(){ docker compose version >/dev/null 2>&1; }
has_compose(){ compose_v2_present || command -v docker-compose >/dev/null 2>&1; }

# Global compose context
COMPOSE_FILE_PATH=""
COMPOSE_ARGS=()
SQL_IMPORT_FILE="easystaff-helper.sql"

run_compose(){
  if compose_v2_present; then docker compose "${COMPOSE_ARGS[@]}" "$@"
  elif command -v docker-compose >/dev/null 2>&1; then docker-compose "${COMPOSE_ARGS[@]}" "$@"
  else return 1; fi
}

install_docker_repo_ubuntu_debian(){
  local distro="$1" codename="$2"
  export DEBIAN_FRONTEND=noninteractive
  info "Adding official Docker repository for ${distro} ${codename:-...}"
  apt-get update -y
  apt-get install -y ca-certificates curl gnupg lsb-release
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${distro}/gpg" | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  if [[ -z "$codename" ]]; then codename="$(lsb_release -cs)"; fi
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/${distro} ${codename} stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
  log "Docker installed and started."
}

install_docker_repo_rhel_like(){
  local id="$1"
  info "Adding official Docker repository for ${id}"
  if command -v dnf >/dev/null 2>&1; then
    dnf -y remove docker docker-client docker-client-latest docker-common docker-latest docker-latest-logrotate docker-logrotate docker-engine || true
    dnf -y install dnf-plugins-core
    if [[ "$id" == "fedora" ]]; then
      dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
    else
      dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    fi
    dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  else
    yum -y remove docker docker-client docker-client-latest docker-common docker-latest docker-latest-logrotate docker-logrotate docker-engine || true
    yum -y install yum-utils
    yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    yum -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  fi
  systemctl enable --now docker
  log "Docker installed and started."
}

install_docker_production(){
  require_root
  title "Docker Installation"
  if docker_present && has_compose; then
    log "Docker and Compose already installed. Skipping."
  else
    IFS=: read -r id ver codename <<<"$(detect_distro)"
    info "Distribution: ${id:-unknown} ${ver:-} ${codename:-}"
    case "$id" in
      ubuntu) install_docker_repo_ubuntu_debian "ubuntu" "$codename" ;;
      debian) install_docker_repo_ubuntu_debian "debian" "" ;;
      rhel|centos|rocky|almalinux|ol|fedora) install_docker_repo_rhel_like "$id" ;;
      *) err "Unsupported distribution: $id. See: https://docs.docker.com/engine/install/"; exit 1 ;;
    esac
    local target_user="${SUDO_USER:-$USER}"
    if id -nG "$target_user" | grep -qw docker; then
      info "User $target_user already in docker group."
    else
      usermod -aG docker "$target_user" || true
      warn "User $target_user added to docker group. Re-login or run: newgrp docker"
    fi
  fi
  if [[ ! -f /etc/docker/daemon.json ]]; then
    info "Creating basic /etc/docker/daemon.json"
    cat >/etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" },
  "live-restore": true,
  "storage-driver": "overlay2"
}
JSON
    systemctl restart docker
    log "daemon.json applied."
  else
    info "Found /etc/docker/daemon.json — leaving unchanged."
  fi
  if compose_v2_present; then
    log "Docker Compose v2 available (docker compose)."
  else
    warn "Compose v2 not found. Install docker-compose-plugin if needed."
  fi
}

# ------------- Ensure docker daemon is running -------------
ensure_docker_running(){
  if ! systemctl is-active --quiet docker 2>/dev/null; then
    info "Starting docker service..."
    systemctl daemon-reload || true
    systemctl enable --now docker || {
      err "Failed to start docker.service. Check: journalctl -u docker -n 200 --no-pager"
      return 1
    }
  fi
  local t=0
  until docker info >/dev/null 2>&1; do
    sleep 1; ((t++))
    (( t > 30 )) && { err "Docker daemon did not come online in 30s. Check: journalctl -u docker"; return 1; }
  done
  log "Docker daemon is active."
}

# ------------- Compose file discovery and context -------------
find_compose_file(){
  # Respect COMPOSE_FILE env var (can be colon-separated list)
  if [[ -n "${COMPOSE_FILE:-}" ]]; then
    local first="${COMPOSE_FILE%%:*}"
    [[ -f "$first" ]] && { echo "$first"; return 0; }
  fi
  # Valid filenames by priority
  local candidates=(compose.yaml compose.yml docker-compose.yaml docker-compose.yml)
  for f in "${candidates[@]}"; do
    [[ -f "$f" ]] && { echo "$f"; return 0; }
  done
  return 1
}

init_compose_ctx(){
  if compose_v2_present; then :; elif ! command -v docker-compose >/dev/null 2>&1; then
    err "docker compose/docker-compose command unavailable. Install Compose v2 plugin or docker-compose."
    return 1
  fi
  if COMPOSE_FILE_PATH="$(find_compose_file)"; then
    COMPOSE_ARGS=(-f "$COMPOSE_FILE_PATH")
    info "Found Compose file: $COMPOSE_FILE_PATH"
    return 0
  else
    err "Compose file not found. Expected: compose.yaml|compose.yml|docker-compose.yaml|docker-compose.yml (or set COMPOSE_FILE)."
    return 1
  fi
}

# ------------- Compose and exec helpers -------------
compose_service_exists(){
  [[ -n "${COMPOSE_FILE_PATH:-}" ]] || init_compose_ctx || return 1
  local svc="$1"
  run_compose ps --services 2>/dev/null | grep -qx "$svc"
}

db_exec(){
  local target="$1"; shift
  if compose_service_exists "$target"; then
    run_compose exec -T "$target" "$@"
  else
    docker exec -i "$target" "$@"
  fi
}

# ------------- MariaDB: wait and import -------------
wait_for_mariadb(){
  local target="$1" root_pass="$2" timeout="${3:-180}"
  title "Waiting for MariaDB"
  info "Container/service: ${target}; timeout: ${timeout}s"
  local start_ts; start_ts=$(date +%s)
  while true; do
    if db_exec "$target" sh -lc "mariadb -N -uroot -p\"$root_pass\" -e 'SELECT 1' >/dev/null 2>&1"; then
      log "MariaDB is ready."
      return 0
    fi
    sleep 2
    local now; now=$(date +%s)
    (( now - start_ts > timeout )) && { err "MariaDB wait timeout."; return 1; }
  done
}

import_sql_into_db(){
  local env_file="$1"
  local sql_path="${2:-$SQL_IMPORT_FILE}"

  title "SQL Import"
  [[ -f "$sql_path" ]] || { warn "SQL file $sql_path not found. Skipping import."; return 0; }

  local db_target root_pass
  db_target="$(env_get "$env_file" "DB_HOST")"; db_target="${db_target:-easystaff-helper-db}"
  root_pass="$(env_get "$env_file" "MARIADB_ROOT_PASSWORD")"
  [[ -n "$root_pass" ]] || { err "MARIADB_ROOT_PASSWORD empty in $env_file. Cannot import."; return 1; }

  if compose_service_exists "$db_target"; then
    info "Found compose DB service: ${db_target}"
  else
    docker ps --format '{{.Names}}' | grep -qx "$db_target" || { err "Container '$db_target' not running."; return 1; }
    info "Found DB container: ${db_target}"
  fi

  wait_for_mariadb "$db_target" "$root_pass" 180 || return 1

  # Check if database already initialized (avoid duplicate import)
  if db_exec "$db_target" sh -lc "mariadb -N -uroot -p\"$root_pass\" -e \"SELECT 1 FROM mysql.user WHERE user='easystaff_helper' LIMIT 1;\" 2>/dev/null" | grep -q 1; then
    warn "Database already initialized (user 'easystaff_helper' exists)."
    if ! ask_yn "Re-import SQL (may cause duplication errors)?" "n"; then
      info "Import skipped."
      return 0
    fi
  fi

  info "Importing from file: ${sql_path}"
  if compose_service_exists "$db_target"; then
    run_compose exec -T "$db_target" sh -lc "mariadb -uroot -p\"$root_pass\"" < "$sql_path"
  else
    docker exec -i "$db_target" sh -lc "mariadb -uroot -p\"$root_pass\"" < "$sql_path"
  fi
  log "Import completed."
}

# ------------- Restart after enabling DB -------------
restart_after_db_enabled(){
  title "Restarting Containers After DB Enabled"
  ensure_docker_running || return 1
  init_compose_ctx || return 1

  local services=()
  if compose_service_exists "bot"; then services+=("bot"); fi
  # Add other services if needed:
  # if compose_service_exists "mariadb"; then services+=("mariadb"); fi

  if ((${#services[@]}==0)); then
    warn "No services found for restart. Skipping."
    return 0
  fi

  info "Restarting: ${services[*]}"
  run_compose restart "${services[@]}"
  log "Restart completed."
}

show_how_to_run(){
  section "Tips"
  echo -e "- ${BOLD}If added user to docker group${RESET}: re-login or run: newgrp docker"
  echo -e "- ${BOLD}Start stack${RESET}:     docker compose up -d   # or docker-compose up -d"
  echo -e "- ${BOLD}Logs${RESET}:            docker compose logs -f"
  echo -e "- ${BOLD}Stop${RESET}:            docker compose down"
}

# ------------- Main -------------
main(){
  require_root

  # 0) Repository (clone/update into current directory, then cd into it) — runs before Docker install. [web:731]
  title "Repository Setup"
  ensure_git_installed
  sync_repo_in_pwd
  enter_repo_dir

  # Check if stack is already running
  local stack_running="no"
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "easystaff-helper-bot"; then
    stack_running="yes"
    warn "⚠️  Project containers are already running."
    if ! ask_yn "Continue with reinstall/reconfigure?" "n"; then
      echo "Cancelled."
      exit 0
    fi
  fi

  title "Easystaff Helper Installer"
  echo -e "${FG_GRAY}Interactive installer with automatic DB import (if enabled).${RESET}"

  echo -e "${BOLD}1)${RESET} Install"
  echo -e "${BOLD}2)${RESET} Exit"
  read -rp "$(echo -e "${FG_BLUE}[?]${RESET} Choose option: ")" choice < /dev/tty
  if [[ -z "${choice:-}" ]]; then choice="1"; fi # fallback to Install

  case "$choice" in
    1)
      install_docker_production
      ensure_docker_running || exit 1

      local env_file=".env"
      [[ -f "$env_file" ]] || { err "$env_file not found. Place .env next to script."; exit 1; }

      # Read USE_DB policy
      local use_db_state="unset"
      if grep -q "^USE_DB=true" "$env_file"; then
        use_db_state="true"
        info "USE_DB=true found in .env — import will proceed without confirmation."
      elif grep -q "^USE_DB=false" "$env_file"; then
        use_db_state="false"
        info "USE_DB=false found in .env — can enable DB with confirmation."
      fi

      # Initialize Compose context and start stack
      init_compose_ctx || { err "Compose file not found or docker compose/docker-compose unavailable."; exit 1; }
      title "Starting Compose"
      info "Bringing up stack (may take time on first run)..."
      ensure_docker_running || exit 1
      run_compose up -d
      log "Stack started."

      # Flag: DB enabled now
      local db_enabled_now="no"

      # Import policy
      if [[ "$use_db_state" == "true" ]]; then
        info "Import from ${SQL_IMPORT_FILE} without confirmation."
        import_sql_into_db "$env_file" "$SQL_IMPORT_FILE" || warn "Import failed."
        # DB was already enabled — restart not mandatory
      elif [[ "$use_db_state" == "false" ]]; then
        if ask_yn "Use database?" "y"; then
          set_env_kv "$env_file" "USE_DB" "true"
          info "USE_DB=true written. Importing from ${SQL_IMPORT_FILE}."
          import_sql_into_db "$env_file" "$SQL_IMPORT_FILE" || warn "Import failed."
          db_enabled_now="yes"
        else
          info "USE_DB=false unchanged. Import skipped."
        fi
      else
        if ask_yn "Use database?" "y"; then
          set_env_kv "$env_file" "USE_DB" "true"
          info "USE_DB=true written. Importing from ${SQL_IMPORT_FILE}."
          import_sql_into_db "$env_file" "$SQL_IMPORT_FILE" || warn "Import failed."
          db_enabled_now="yes"
        else
          set_env_kv "$env_file" "USE_DB" "false"
          info "USE_DB=false written. Import skipped."
        fi
      fi

      # Restart after enabling DB (only if just enabled)
      if [[ "$db_enabled_now" == "yes" ]]; then
        restart_after_db_enabled || warn "Service restart failed."
      fi

      show_how_to_run
      ;;
    2|q|quit|exit)
      echo "Exit."
      ;;
    *)
      err "Invalid choice."
      exit 1
      ;;
  esac
}

main
