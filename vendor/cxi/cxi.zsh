if [[ -z "${ZSH_VERSION:-}" ]]; then
  printf '%s\n' 'cxi: source cxi.zsh in zsh, or cxi.bash in Bash' >&2
  return 1
fi

source "${${(%):-%x}:A:h}/cxi-core.sh" || return $?

_cxi() {
  emulate -L zsh
  local -a commands instances actions
  commands=(new add ls run login path env rm remote help version)
  actions=(start stop status ls pair enable disable)
  instances=("${(@f)$(_cxi_names)}")
  if (( CURRENT == 2 )); then
    _describe 'command' commands
    compadd -a instances
  elif [[ "$words[2]" == remote ]]; then
    if (( CURRENT == 3 )); then
      _describe 'remote action' actions
    elif (( CURRENT == 4 )) && [[ "$words[3]" != ls ]]; then
      compadd -a instances
    fi
  elif (( CURRENT == 3 )) && [[ "$words[2]" == (run|login|path|env|rm) ]]; then
    compadd -a instances
  elif [[ "${words[CURRENT-1]}" == --from ]]; then
    compadd default
    compadd -a instances
  fi
}

if (( $+functions[compdef] )); then
  compdef _cxi cxi
fi
return 0
