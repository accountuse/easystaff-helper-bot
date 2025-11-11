#!/usr/bin/env bash
set -Eeuo pipefail

# ---- colors ----
BOLD="\033[1m"; RED="\033[38;5;196m"; YEL="\033[38;5;220m"; GRN="\033[38;5;46m"; BLU="\033[38;5;33m"; RST="\033[0m"
log(){  echo -e "${GRN}[OK]${RST}   $*"; }          # success messages
info(){ echo -e "${BLU}[INFO]${RST} $*"; }         # informational messages
warn(){ echo -e "${YEL}[WARN]${RST} $*"; }         # warnings
err(){  echo -e "${RED}[ERR]${RST}  $*" >&2; }     # errors to stderr

# Require root privileges (sudo)
require_root(){ [[ $EUID -eq 0 ]] || { err "Run as root (sudo)."; exit 1; } }  # fail fast if not root [web:692]

# Detect distro id:version for package removal logic
detect_distro(){
  if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    echo "${ID:-unknown}:${VERSION_ID:-}"
  else
    echo "unknown:"
  fi
}

# Ask yes/no with default
ask_yn(){
  local p="$1" d="${2:-n}" a
  read -rp "$(echo -e "${BLU}[?]${RST} ${p} [y/n] (default: ${d}): ")" a
  a="${a:-$d}"
  a="$(printf '%s' "$a" | tr '[:upper:]' '[:lower:]' | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"
  case "$a" in y|yes|д|да) return 0 ;; *) return 1 ;; esac
}

# Stop Docker daemon and containerd units
stop_docker(){
  info "Stopping Docker daemon and containerd..."
  systemctl stop docker docker.socket containerd 2>/dev/null || true  # tolerate absence [web:692]
}

# Remove runtime Docker objects via CLI
purge_runtime_objects(){
  info "Removing containers/images/networks/volumes via docker CLI..."
  if command -v docker >/dev/null 2>&1; then
    # Containers
    docker ps -aq | xargs -r docker rm -f || true
    # Images
    docker images -aq | xargs -r docker rmi -f || true
    # Networks (unused)
    docker network prune -f || true
    # Volumes (all unused, including named if --all in newer APIs)
    docker volume prune -f || true  # remove unused local volumes [web:680][web:693]
    # Alternatively: docker system prune -a --volumes -f  # remove all unused objects [web:693]
  else
    warn "docker CLI not found — skipping CLI cleanup."
  fi
}

# Remove Docker packages on Debian/Ubuntu
purge_packages_debian(){
  info "Removing Docker packages (Ubuntu/Debian)..."
  apt-get purge -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin docker-ce-rootless-extras docker.io || true
  apt-get autoremove -y --purge || true
}

# Remove Docker packages on RHEL/CentOS/Fedora
purge_packages_rhel(){
  info "Removing Docker packages (RHEL/CentOS/Fedora)..."
  if command -v dnf >/dev/null 2>&1; then
    dnf remove -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin docker-ce-rootless-extras || true
  else
    yum remove -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin docker-ce-rootless-extras || true
  fi
}

# Remove Compose plugin leftovers and legacy docker-compose binary
purge_compose_leftovers(){
  if command -v apt-get >/dev/null 2>&1; then
    apt-get remove -y docker-compose-plugin || true
  elif command -v dnf >/devnull 2>&1; then
    dnf remove -y docker-compose-plugin || true
  else
    yum remove -y docker-compose-plugin || true
  fi
  # Legacy docker-compose in /usr/local/bin
  rm -f /usr/local/bin/docker-compose || true
}

# Remove Docker data directories (destructive)
purge_data_dirs(){
  warn "Removing Docker data directories (ALL images/volumes/layers will be lost)..."
  rm -rf /var/lib/docker || true
  rm -rf /var/lib/containerd || true
  rm -rf /etc/docker || true
  rm -rf /run/docker || true
  rm -f  /var/run/docker.sock || true
  log "Data directories removed. [OK]"
}

main(){
  require_root
  echo -e "${BOLD}${RED}WARNING:${RST} This operation will completely remove Docker, ALL containers, images, networks, and VOLUMES (including MariaDB data). This cannot be undone."
  ask_yn "Proceed with destroying the Docker environment?" "n" || { warn "Cancelled by user."; exit 0; }

  # Stop daemon and clean runtime objects first
  stop_docker
  purge_runtime_objects

  # Remove packages by distro family
  IFS=: read -r id ver <<<"$(detect_distro)"
  case "$id" in
    ubuntu|debian) purge_packages_debian ;;
    rhel|centos|rocky|almalinux|ol|fedora) purge_packages_rhel ;;
    *)
      warn "Unknown distro ($id). Will proceed with data cleanup without package removal."
      ;;
  esac

  # Remove Compose plugin and legacy docker-compose if present
  purge_compose_leftovers

  # Remove Docker data directories (destructive)
  purge_data_dirs

  info "Done. A system reboot is recommended: reboot"
  echo -e "${BOLD}Hint:${RST} To reinstall Docker, follow the official installation instructions for your OS."
}

main
