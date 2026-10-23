# Sourced explicitly from the owned integration directory. No command acceptance.
# A binding is opt-in in the current shell: bindkey '^X^L' localflow-transform
# The installer adds a collision-checked binding in its owned rc block.

function localflow-transform() {
    emulate -L zsh
    setopt localoptions multibyte
    if [[ -z "$LOCALFLOW_TERMINAL_CLIENT" || ! -x "$LOCALFLOW_TERMINAL_CLIENT" ]]; then
        zle -M 'LocalFlow editor integration is unavailable'
        return 1
    fi
    if [[ "$CONTEXT" != start ]]; then
        zle -M 'LocalFlow needs the complete buffer at the primary prompt'
        return 1
    fi
    local original="$BUFFER" original_cursor="$CURSOR"
    local original_mark="$MARK" original_region="$REGION_ACTIVE"
    local reply_cursor reply_buffer
    # Process substitution carries text as data, never a command or paste.
    # read -d NUL keeps trailing newlines, unlike command substitution.
    {
        if ! IFS= read -r -d $'\0' reply_cursor ||
           ! IFS= read -r -d $'\0' reply_buffer; then
            zle -M 'LocalFlow cancelled or unavailable; buffer preserved'
            return 1
        fi
    } < <(print -rn -- "$original" | "$LOCALFLOW_TERMINAL_CLIENT" zle \
          --cursor "$original_cursor" --mark "$original_mark" \
          --region "$original_region" --tty "$TTY")
    if [[ "$BUFFER" != "$original" || "$CURSOR" != "$original_cursor" ||
          "$MARK" != "$original_mark" || "$REGION_ACTIVE" != "$original_region" ]]; then
        zle -M 'Buffer changed while LocalFlow was open; edit not applied'
        return 1
    fi
    if [[ "$reply_cursor" != <-> ]] || (( reply_cursor > ${#reply_buffer} )); then
        zle -M 'LocalFlow returned an invalid edit; buffer preserved'
        return 1
    fi
    BUFFER="$reply_buffer"
    CURSOR="$reply_cursor"
    REGION_ACTIVE=0
    if [[ "$BUFFER" != "$reply_buffer" || "$CURSOR" != "$reply_cursor" ]]; then
        zle -M 'LocalFlow buffer readback failed'
        return 1
    fi
    zle redisplay
}

zle -N localflow-transform

# Uninstall cannot edit a running shell. This optional command releases only
# the default bindings still owned by this widget, without restarting a session.
function localflow-terminal-unload() {
    emulate -L zsh
    local keymap
    for keymap in emacs viins; do
        if [[ "$(bindkey -M "$keymap" '^X^L')" == *' localflow-transform' ]]; then
            bindkey -M "$keymap" -r '^X^L'
        fi
    done
    zle -D localflow-transform
    if [[ -n "$LOCALFLOW_OWNED_CODEX_FUNCTION" &&
          "$functions[codex-localflow]" == "$LOCALFLOW_OWNED_CODEX_FUNCTION" ]]; then
        unfunction codex-localflow
    fi
    unfunction localflow-transform localflow-terminal-unload
    unset LOCALFLOW_TERMINAL_CLIENT LOCALFLOW_OWNED_CODEX_FUNCTION
}
