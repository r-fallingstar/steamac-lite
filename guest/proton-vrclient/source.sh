#!/bin/bash
# Source checkout helpers; kept separate so interrupted/fresh checkouts can be tested locally.
prepare_proton_checkout() {
    local src=$1 repo=$2 commit=$3 current
    if [[ ! -e "$src/.git" ]]; then
        mkdir -p "$src"
        git -C "$src" init -q
    fi
    # Proton's submodule URLs are relative to origin, including on a cached checkout.
    if git -C "$src" remote get-url origin >/dev/null 2>&1; then
        git -C "$src" remote set-url origin "$repo"
    else
        git -C "$src" remote add origin "$repo"
    fi
    if ! git -C "$src" cat-file -e "$commit^{commit}" 2>/dev/null; then
        git -C "$src" fetch -q --depth 1 origin "$commit"
    fi
    current=$(git -C "$src" rev-parse HEAD 2>/dev/null || true)
    if [[ $current != "$commit" ]]; then
        [[ -z $(git -C "$src" status --porcelain) ]] || {
            echo "refusing to replace modified Proton source in $src" >&2
            return 1
        }
        git -C "$src" checkout -q --detach "$commit"
    fi
    git -C "$src" submodule sync --recursive
}

update_proton_submodules() {
    local src=$1
    git -C "$src" submodule update --init --recursive --depth 1 --jobs 8 ||
        git -C "$src" submodule update --init --recursive --jobs 8
    # Git can consider an interrupted checkout up to date even though its worktree
    # is empty. Restore only that case; never force-reset populated source trees.
    # foreach follows real gitlinks, not obsolete entries left in .gitmodules.
    git -C "$src" submodule foreach --quiet --recursive '
        if [ -z "$(find . -mindepth 1 -maxdepth 1 ! -name .git -print -quit)" ] &&
           [ -n "$(git ls-tree --name-only HEAD)" ]; then
            if ! git diff --cached --quiet HEAD --; then
                echo "Submodule $displaypath is empty with staged changes; inspect it before retrying." >&2
                exit 1
            fi
            echo "Restoring empty submodule worktree: $displaypath"
            git restore --source=HEAD --worktree -- . || exit 1
        fi
        if ! git diff --quiet --diff-filter=D --; then
            echo "Submodule $displaypath has missing tracked files. Not overwriting a populated worktree; inspect it before retrying." >&2
            exit 1
        fi
    '
}
