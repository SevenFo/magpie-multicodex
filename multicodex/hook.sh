# Sourced by cxi.env inside _cxi_exec; preserve its arguments and lifecycle.
# MULTICODEX_STATE and MULTICODEX_BRIDGE are set by the managed cxi.env block.
# Do not source the state file: Magpie writes JSON, never executable shell code.
case "${1:-}" in
  login|logout|app-server|remote-control|completion|completions|mcp|features|--help|-h|--version|-V)
    return 0 ;;
esac
local _mcxi_status='' _mcxi_token='' _mcxi_arg=''
local -a _mcxi_args=()
{
  IFS= read -r -d '' _mcxi_status || {
    printf '%s\n' 'MultiCodex: could not prepare this instance; Codex was not started' >&2
    return 1
  }
  case "$_mcxi_status" in
    off) return 0 ;;
    ready) ;;
    *) printf '%s\n' 'MultiCodex: invalid bridge response' >&2; return 1 ;;
  esac
  IFS= read -r -d '' _mcxi_token || return 1
  while IFS= read -r -d '' _mcxi_arg; do
    _mcxi_args+=("$_mcxi_arg")
  done
} < <(python3 "$MULTICODEX_BRIDGE" args "$MULTICODEX_STATE")
[[ ${#_mcxi_args[@]} -ge 8 ]] || {
  printf '%s\n' 'MultiCodex: incomplete launch arguments' >&2
  return 1
}
export MULTICODEX_API_KEY="$_mcxi_token"
set -- "${_mcxi_args[@]}" "$@"
unset MULTICODEX_STATE MULTICODEX_BRIDGE _mcxi_status _mcxi_token _mcxi_arg _mcxi_args
