# Bash completion for rg2sing DiffSinger tools.
# Source this file: source /scripts/rg2sing_completion.bash
# Optional: export RG2SING_VOICES_ROOT=/models/UFR-V1.0/UFR-V1.0
_rg2sing_complete() {
    local cur prev root singer i command_name value
    local -a options
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev=''
    (( COMP_CWORD > 0 )) && prev="${COMP_WORDS[COMP_CWORD-1]}"
    root="${RG2SING_VOICES_ROOT:-/models/UFR-V1.0/UFR-V1.0}"
    command_name="${COMP_WORDS[0]##*/}"

    # Determine which singer was selected anywhere before cursor.
    singer=''
    for ((i=1; i<COMP_CWORD; i++)); do
        case "${COMP_WORDS[i]}" in
            --singer)
                if (( i+1 < COMP_CWORD )); then
                    singer="${COMP_WORDS[i+1]}"
                fi
                ;;
            --singer=*) singer="${COMP_WORDS[i]#--singer=}" ;;
        esac
    done

    # Handle both --flag VALUE and --flag=VALUE.
    local flag="$prev" prefix=''
    case "$cur" in
        --singer=*) flag='--singer'; prefix='--singer='; cur="${cur#--singer=}" ;;
        --speaker=*) flag='--speaker'; prefix='--speaker='; cur="${cur#--speaker=}" ;;
    esac

    case "$flag" in
        --singer)
            local path
            for path in "$root"/*/dsconfig.yaml; do
                [[ -f "$path" ]] || continue
                value="${path%/dsconfig.yaml}"
                value="${value##*/}"
                [[ "$value" == "$cur"* ]] && COMPREPLY+=("$prefix$value")
            done
            return 0
            ;;
        --speaker)
            # Parse the singer's YAML file, and only suggest existing .emb voice variants.
            # YAML parsing occurs at completion time, so newly installed singers appear automatically.
            local -a speakers
            local choice
            if [[ -n "$singer" && -f "$root/$singer/dsconfig.yaml" ]]; then
                mapfile -t speakers < <(python3 - "$root/$singer/dsconfig.yaml" <<'PY'
import sys
from pathlib import Path
try:
    import yaml
    cfg = Path(sys.argv[1])
    for name in (yaml.safe_load(cfg.read_text(encoding='utf-8')) or {}).get('speakers', []):
        if isinstance(name, str) and (cfg.parent / (name + '.emb')).is_file():
            # Renderer accepts the basename (e.g. millefeuille_v001.yura_opera).
            print(Path(name).name)
except (ImportError, OSError, ValueError, TypeError):
    pass
PY
)
                for choice in "${speakers[@]}"; do
                    [[ "$choice" == "$cur"* ]] && COMPREPLY+=("$prefix$choice")
                done
            fi
            return 0
            ;;
        --part)
            COMPREPLY=( $(compgen -W 'Soprani Alti Tenors Basses Soprani_divisi' -- "$cur") )
            return 0
            ;;
        --vocoder)
            COMPREPLY=( $(compgen -W 'nsf potluck tgm' -- "$cur") )
            return 0
            ;;
    esac

    # Non-option values (e.g. --work) should complete paths as usual.
    if [[ "$cur" == -* ]]; then
        case "$command_name" in
            chorale_full.py)
                options=(--work --part --singer --speaker --vocoder --steps --depth --allow-proposals --resume --help)
                ;;
            render_millefeuille_duration.py)
                options=(--singer --speaker --root --input --output --vocoder --steps --depth --pitch-mode --help)
                ;;
            test_all_voices.py)
                options=(--singer --speaker --root --input --output-dir --vocoders --steps --depth --dry-run --resume --help)
                ;;
        esac
        COMPREPLY=( $(compgen -W "${options[*]}" -- "$cur") )
    else
        case "$prev" in
            --work|--input|--output|--output-dir|--root)
                COMPREPLY=( $(compgen -f -- "$cur") )
                compopt -o filenames 2>/dev/null || :
                ;;
        esac
    fi
}
complete -F _rg2sing_complete chorale_full.py render_millefeuille_duration.py test_all_voices.py
