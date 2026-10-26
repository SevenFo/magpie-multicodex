CXI_VERSION=1.1.0
: "${CXI_ROOT:=$HOME/.codex-instances}"

_cxi_error() { printf 'cxi: %s\n' "$*" >&2; return 1; }

_cxi_valid() {
  local name="${1:-}"
  case "$name" in
    ''|[!A-Za-z0-9]*|*[!A-Za-z0-9._-]*) _cxi_error "invalid instance name '$name'"; return 1 ;;
    default|new|add|ls|list|run|login|path|env|rm|delete|remote|help|version)
      _cxi_error "'$name' is reserved"; return 1 ;;
  esac
  [[ ${#name} -le 64 ]] || { _cxi_error 'instance names must be at most 64 characters'; return 1; }
}

_cxi_root() {
  local root="${CXI_ROOT:-$HOME/.codex-instances}"
  case "$root" in
    /*) ;;
    *) _cxi_error 'CXI_ROOT must be an absolute path'; return 1 ;;
  esac
  while [[ "$root" != / && "$root" == */ ]]; do root="${root%/}"; done
  [[ ! -L "$root" ]] || { _cxi_error 'CXI_ROOT must not be a symlink'; return 1; }
  if [[ -d "$root" ]]; then
    root=$(cd -- "$root" && pwd -P) || return 1
  else
    root="${root%/}"
  fi
  [[ -n "$root" && "$root" != / ]] || { _cxi_error 'CXI_ROOT must not be /'; return 1; }
  printf '%s\n' "$root"
}

_cxi_dir() {
  _cxi_valid "${1:-}" || return 1
  local root
  root=$(_cxi_root) || return 1
  local alias_file="$root/.aliases/$1" target=''
  if [[ -e "$alias_file" || -L "$alias_file" ]]; then
    [[ -f "$alias_file" && ! -L "$alias_file" ]] || { _cxi_error 'invalid instance alias'; return 1; }
    IFS= read -r target < "$alias_file" || return 1
    [[ "$target" == /* && "$target" != / && "$target" != *$'\n'* ]] || { _cxi_error 'invalid alias path'; return 1; }
    printf '%s\n' "$target"
    return
  fi
  printf '%s/%s\n' "$root" "$1"
}

_cxi_add() (
  [[ $# -eq 2 ]] || { _cxi_error 'usage: cxi add <name> <absolute CODEX_HOME>'; return 1; }
  _cxi_valid "$1" || return 1
  local name="$1" target="$2" root existing alias_file
  [[ "$target" == /* && -d "$target" && ! -L "$target" && "$target" != *$'\n'* ]] || {
    _cxi_error 'CODEX_HOME must be an existing absolute directory'; return 1;
  }
  target=$(cd -- "$target" && pwd -P) || return 1
  [[ "$target" != / ]] || return 1
  root=$(_cxi_root) || return 1
  if _cxi_exists "$name" >/dev/null 2>&1; then
    existing=$(_cxi_dir "$name") || return 1
    [[ "$existing" == "$target" ]] && return 0
    _cxi_error "instance '$name' already exists"; return 1
  fi
  mkdir -p -- "$root/.aliases" || return 1
  [[ ! -L "$root/.aliases" ]] || return 1
  chmod 700 "$root" "$root/.aliases" || return 1
  alias_file="$root/.aliases/$name"
  [[ ! -e "$alias_file" && ! -L "$alias_file" ]] || { _cxi_error 'alias already exists'; return 1; }
  (umask 077; set -C; printf '%s\n' "$target" > "$alias_file") || return 1
  printf "registered '%s' at %s\n" "$name" "$target"
)

_cxi_exists() {
  local directory
  directory=$(_cxi_dir "${1:-}") || return 1
  [[ ! -L "$directory" ]] || { _cxi_error "instance '$1' must not be a symlink"; return 1; }
  [[ -d "$directory" ]] || { _cxi_error "no such instance '${1:-}' (try: cxi ls)"; return 1; }
}

_cxi_names() (
  if [[ -n "${ZSH_VERSION:-}" ]]; then emulate -L zsh; setopt nonomatch; fi
  local root directory name
  root=$(_cxi_root) || return 1
  for directory in "$root"/*; do
    [[ -d "$directory" && ! -L "$directory" ]] || continue
    name="${directory##*/}"
    if _cxi_valid "$name" 2>/dev/null; then printf '%s\n' "$name"; fi
  done
  for directory in "$root"/.aliases/*; do
    [[ -f "$directory" && ! -L "$directory" ]] || continue
    name="${directory##*/}"
    if _cxi_valid "$name" 2>/dev/null; then printf '%s\n' "$name"; fi
  done
)

_cxi_new() (
  if [[ -n "${ZSH_VERSION:-}" ]]; then emulate -L zsh; setopt nonomatch; fi
  umask 077
  local name="${1:-}" from='' source_directory='' root directory stage='' lock='' asset
  [[ -n "$name" ]] || { _cxi_error 'usage: cxi new <name> [--from <name|default>]'; return 1; }
  shift
  if (( $# )); then
    [[ $# -eq 2 && "$1" == --from && -n "$2" ]] || {
      _cxi_error 'usage: cxi new <name> [--from <name|default>]'; return 1;
    }
    from="$2"
  fi
  _cxi_valid "$name" || return 1
  root=$(_cxi_root) || return 1
  [[ ! -e "$root/.aliases/$name" && ! -L "$root/.aliases/$name" ]] || { _cxi_error "instance '$name' already exists"; return 1; }
  if [[ -n "$from" ]]; then
    if [[ "$from" == default ]]; then
      source_directory="$HOME/.codex"
      [[ -d "$source_directory" ]] || { _cxi_error 'default configuration directory does not exist'; return 1; }
    else
      _cxi_exists "$from" || return 1
      source_directory=$(_cxi_dir "$from") || return 1
    fi
  fi
  mkdir -p -- "$root" && chmod 700 "$root" || return 1
  root=$(_cxi_root) || return 1
  directory="$root/$name"
  [[ ! -e "$directory" && ! -L "$directory" ]] || { _cxi_error "'$name' already exists"; return 1; }
  lock="$root/.cxi-create-$name.lock"
  mkdir -- "$lock" || { _cxi_error "another creation of '$name' is in progress"; return 1; }
  trap '[[ -z "$stage" ]] || command rm -rf -- "$stage"; rmdir -- "$lock"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM HUP
  stage=$(mktemp -d "$root/.cxi-new.XXXXXXXX") || return 1
  if [[ -n "$source_directory" ]]; then
    for asset in "$source_directory/config.toml" "$source_directory/AGENTS.md" "$source_directory"/*.config.toml; do
      [[ -f "$asset" ]] || continue
      cp -- "$asset" "$stage/${asset##*/}" && chmod 600 "$stage/${asset##*/}" || return 1
    done
    for asset in prompts skills; do
      if [[ -d "$source_directory/$asset" ]]; then
        cp -R -- "$source_directory/$asset" "$stage/$asset" || return 1
      fi
    done
  fi
  [[ ! -e "$directory" && ! -L "$directory" ]] || { _cxi_error "'$name' appeared during creation"; return 1; }
  mv -- "$stage" "$directory" || return 1
  stage=''
  printf "created '%s' at %s\nnext: cxi login %s\n" "$name" "$directory" "$name"
)

_cxi_exec() (
  if [[ -n "${ZSH_VERSION:-}" ]]; then emulate -L zsh; fi
  local name="$1" record="$2" directory
  shift 2
  _cxi_exists "$name" || return 1
  directory=$(_cxi_dir "$name") || return 1
  unset OPENAI_API_KEY OPENAI_BASE_URL CODEX_API_KEY CODEX_ACCESS_TOKEN CODEX_SQLITE_HOME CODEX_HOME
  if [[ -e "$directory/cxi.env" || -L "$directory/cxi.env" ]]; then
    [[ -f "$directory/cxi.env" && ! -L "$directory/cxi.env" ]] || {
      _cxi_error 'cxi.env must be a regular file, not a symlink'; return 1;
    }
    chmod 600 "$directory/cxi.env" || return 1
    source "$directory/cxi.env" || { _cxi_error "failed to load '$name/cxi.env'; not starting Codex"; return 1; }
  fi
  export CODEX_HOME="$directory"
  command -v codex >/dev/null 2>&1 || { _cxi_error 'codex is not on PATH'; return 127; }
  if [[ "$record" == 1 ]]; then
    [[ ! -L "$directory/.cxi_last_used" ]] || { _cxi_error 'last-started marker must not be a symlink'; return 1; }
    touch -- "$directory/.cxi_last_used" || return 1
  fi
  exec codex "$@"
)

_cxi_last_used() {
  local marker="$1/.cxi_last_used"
  if [[ -f "$marker" ]]; then
    if [[ "$(uname -s)" == Darwin ]]; then
      stat -f '%Sm' -t '%Y-%m-%d %H:%M' "$marker" 2>/dev/null
    else
      stat -c '%y' "$marker" 2>/dev/null | cut -c1-16
    fi
  else
    printf '%s\n' '-'
  fi
}

_cxi_list() {
  local name directory credentials environment last
  printf '%-20s %-12s %-6s %s\n' NAME AUTH-FILE ENV LAST-STARTED
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    directory=$(_cxi_dir "$name") || return 1
    credentials=no; environment=no
    [[ ! -f "$directory/auth.json" ]] || credentials=present
    [[ ! -s "$directory/cxi.env" ]] || environment=yes
    last=$(_cxi_last_used "$directory") || last='-'
    printf '%-20s %-12s %-6s %s\n' "$name" "$credentials" "$environment" "$last"
  done < <(_cxi_names)
  printf '%s\n' 'AUTH-FILE is not login status; use: cxi login <name> status'
}

_cxi_env() {
  local name="${1:-}" directory environment editor
  [[ $# -eq 1 ]] || { _cxi_error 'usage: cxi env <name>'; return 1; }
  _cxi_exists "$name" || return 1
  directory=$(_cxi_dir "$name") || return 1
  environment="$directory/cxi.env"
  [[ ! -L "$environment" ]] || { _cxi_error 'cxi.env must not be a symlink'; return 1; }
  if [[ ! -e "$environment" ]]; then
    (umask 077; set -C; printf '%s\n' '# Trusted shell code, sourced before launching Codex.' '# export OPENAI_API_KEY=...' '# export OPENAI_BASE_URL=https://...' > "$environment") || return 1
  fi
  [[ -f "$environment" ]] && chmod 600 "$environment" || return 1
  editor="${VISUAL:-${EDITOR:-vi}}"
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import os, shlex, sys; command = shlex.split(sys.argv[1]); command or sys.exit("cxi: empty editor"); os.execvp(command[0], command + [sys.argv[2]])' "$editor" "$environment"
  elif command -v "$editor" >/dev/null 2>&1; then
    "$editor" "$environment"
  else
    _cxi_error 'set EDITOR to an executable, or install Python 3 for editor commands with arguments'
  fi
}

_cxi_remove() {
  local name="${1:-}" force=0 directory answer=''
  [[ $# -ge 1 && $# -le 2 ]] || { _cxi_error 'usage: cxi rm <name> [-f]'; return 1; }
  if [[ $# -eq 2 ]]; then
    [[ "$2" == -f ]] || { _cxi_error 'usage: cxi rm <name> [-f]'; return 1; }
    force=1
  fi
  _cxi_exists "$name" || return 1
  directory=$(_cxi_dir "$name") || return 1
  local alias_file="$(_cxi_root)/.aliases/$name"
  if [[ -f "$alias_file" && ! -L "$alias_file" ]]; then
    command rm -- "$alias_file" || return 1
    printf "unregistered '%s'; files kept at %s\n" "$name" "$directory"
    return 0
  fi
  if [[ -S "$directory/app-server-control/app-server-control.sock" ]] &&
    _cxi_exec "$name" 0 app-server daemon version >/dev/null 2>&1; then
    _cxi_error "'$name' has a running daemon; stop it with 'cxi remote stop $name' first"
    return 1
  fi
  if [[ "$force" == 0 ]]; then
    printf "Delete '%s' (%s), including credentials and sessions? [y/N] " "$name" "$directory" >&2
    if ! IFS= read -r answer; then printf '\n' >&2; return 1; fi
    case "$answer" in y|Y) ;; *) printf '%s\n' cancelled; return 1 ;; esac
  fi
  [[ -d "$directory" && ! -L "$directory" ]] || return 1
  command rm -rf -- "$directory" || return 1
  printf "deleted '%s'\n" "$name"
}

_cxi_remote() {
  local action="${1:-}" name information
  [[ $# -gt 0 ]] && shift
  case "$action" in
    ls|list)
      [[ $# -eq 0 ]] || { _cxi_error 'usage: cxi remote ls'; return 1; }
      _cxi_root >/dev/null || return 1
      printf '%-20s %s\n' NAME DAEMON
      while IFS= read -r name; do
        [[ -n "$name" ]] || continue
        if information=$(_cxi_exec "$name" 0 app-server daemon version 2>&1); then
          printf '%-20s %s\n' "$name" reachable
        else
          printf '%-20s %s\n' "$name" 'not reachable / unsupported (use remote status for details)'
        fi
      done < <(_cxi_names)
      printf '%s\n' 'Daemon reachability does not prove remote control is enabled.'
      ;;
    status)
      [[ $# -eq 1 ]] || { _cxi_error 'usage: cxi remote status <name>'; return 1; }
      printf '%s\n' 'Read-only daemon check; this does not start a daemon or verify remote-control pairing.'
      _cxi_exec "$1" 0 app-server daemon version
      ;;
    start|stop|pair|enable|disable)
      [[ $# -ge 1 && -n "$1" ]] || { _cxi_error "usage: cxi remote $action <name> [codex options...]"; return 1; }
      name="$1"; shift
      case "$action" in
        start|stop|pair) _cxi_exec "$name" 1 remote-control "$action" "$@" ;;
        enable) _cxi_exec "$name" 1 app-server daemon enable-remote-control "$@" ;;
        disable) _cxi_exec "$name" 1 app-server daemon disable-remote-control "$@" ;;
      esac
      ;;
    *) _cxi_error 'usage: cxi remote <start|stop|status|ls|pair|enable|disable> [name] [codex options...]' ;;
  esac
}

_cxi_help() {
  cat <<'CXI_HELP'
cxi: isolated Codex homes (Bash 3.2+ / zsh)
  cxi new <name> [--from <name|default>]
  cxi add <name> <absolute CODEX_HOME>
  cxi ls
  cxi run <name> [codex args...]    or: cxi <name> [codex args...]
  cxi login <name> [login args...]  e.g. --device-auth, status
  cxi path <name>
  cxi env <name>
  cxi rm <name> [-f]
  cxi remote start|stop|pair|enable|disable <name> [codex options...]
  cxi remote status <name>         read-only daemon/version check
  cxi remote ls                    list reachable instance daemons
  cxi version
--remote <address> connects to a server; it does not launch a server.
remote start enables Codex's managed remote-control daemon, not a public TCP listener.
cxi.env is trusted executable shell code. This is configuration isolation, not a sandbox.
CXI_HELP
}

cxi() {
  if [[ -n "${ZSH_VERSION:-}" ]]; then emulate -L zsh; fi
  local action="${1:-help}" name
  [[ $# -eq 0 ]] || shift
  case "$action" in
    new) _cxi_new "$@" ;;
    add) _cxi_add "$@" ;;
    ls|list) [[ $# -eq 0 ]] && _cxi_root >/dev/null && _cxi_list || { _cxi_error 'usage: cxi ls (CXI_ROOT must be valid)'; return 1; } ;;
    run|login)
      [[ $# -ge 1 && -n "$1" ]] || { _cxi_error "usage: cxi $action <name> [codex args...]"; return 1; }
      name="$1"; shift
      if [[ "$action" == login ]]; then _cxi_exec "$name" 1 login "$@"; else _cxi_exec "$name" 1 "$@"; fi
      ;;
    path) [[ $# -eq 1 ]] || { _cxi_error 'usage: cxi path <name>'; return 1; }; _cxi_exists "$1" && _cxi_dir "$1" ;;
    env) _cxi_env "$@" ;;
    rm|delete) _cxi_remove "$@" ;;
    remote) _cxi_remote "$@" ;;
    help|-h|--help) [[ $# -eq 0 ]] || return 1; _cxi_help ;;
    version) [[ $# -eq 0 ]] || return 1; printf 'cxi %s\n' "$CXI_VERSION" ;;
    *) _cxi_exec "$action" 1 "$@" ;;
  esac
}

return 0
