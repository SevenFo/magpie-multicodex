if [[ -z "${BASH_VERSION:-}" ]]; then
  printf '%s\n' 'cxi: source cxi.bash in Bash, or cxi.zsh in zsh' >&2
  return 1
fi

source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/cxi-core.sh" || return $?

_cxi_complete() {
  local current="${COMP_WORDS[COMP_CWORD]}" previous="${COMP_WORDS[COMP_CWORD-1]}"
  local candidates='' candidate
  COMPREPLY=()
  if (( COMP_CWORD == 1 )); then
    candidates="new add ls run login path env rm remote help version $(_cxi_names)"
  elif [[ "${COMP_WORDS[1]}" == remote ]]; then
    if (( COMP_CWORD == 2 )); then
      candidates='start stop status ls pair enable disable'
    elif (( COMP_CWORD == 3 )) && [[ "${COMP_WORDS[2]}" != ls ]]; then
      candidates="$(_cxi_names)"
    fi
  elif [[ "$previous" == --from ]]; then
    candidates="default $(_cxi_names)"
  elif (( COMP_CWORD == 2 )); then
    case "${COMP_WORDS[1]}" in
      run|login|path|env|rm) candidates="$(_cxi_names)" ;;
    esac
  fi
  while IFS= read -r candidate; do
    [[ -n "$candidate" ]] && COMPREPLY+=("$candidate")
  done < <(compgen -W "$candidates" -- "$current")
  return 0
}

complete -F _cxi_complete cxi
return 0
