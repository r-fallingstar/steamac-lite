#!/bin/zsh
# Read-only startup diagnostics. Does not launch/stop an app or change security settings.
# Usage: /bin/zsh collect-startup.sh '/Applications/SteamAC Lite.app' [output-directory]
set -u
umask 077
app=${1:-/Applications/SteamAC Lite.app}
out=${2:-$HOME/Desktop/steamac-startup-$(date +%Y%m%d-%H%M%S)-$$}
if [[ ! -d "$app/Contents" || -e "$out" ]]; then
  print -u2 'App not found, or output directory already exists.'
  exit 1
fi
mkdir -p "$out" || exit 1

# Keep each reader bounded, including sample when task inspection is unavailable.
# The timer signals only the reader this wrapper starts, never the inspected app.
bounded() {
  /usr/bin/perl -e '
    use strict; use warnings;
    my $seconds = shift @ARGV;
    my $pid = fork(); defined $pid or die "fork: $!";
    if (!$pid) { exec @ARGV; die "exec: $!"; }
    $SIG{ALRM} = sub {
      print STDERR "Timed out after ${seconds}s\n";
      kill "KILL", $pid; waitpid $pid, 0; exit 124;
    };
    alarm $seconds;
    waitpid $pid, 0;
    my $status = $?; alarm 0;
    exit(($status & 127) ? 128 + ($status & 127) : $status >> 8);
  ' "$@"
}

capture() {
  local name=$1 seconds=$2
  shift 2
  local result
  bounded "$seconds" "$@" > "$out/$name" 2>&1
  result=$?
  print -r -- "exit_status=$result" >> "$out/$name"
}

{
  print -r -- 'steamac startup diagnostics (no app launched or stopped)'
  /bin/date -u '+UTC: %Y-%m-%dT%H:%M:%SZ'
  /usr/bin/sw_vers
  /usr/bin/uname -m
  /usr/sbin/sysctl hw.memsize hw.logicalcpu hw.model
  for key in CFBundleShortVersionString CFBundleVersion SteamacGitCommit LSUIElement; do
    print -n -r -- "$key: "
    /usr/libexec/PlistBuddy -c "Print :$key" "$app/Contents/Info.plist" 2>&1
  done
} > "$out/system.txt"
typeset -a pids
pids=( ${(f)"$(/usr/bin/pgrep -x -u "$UID" 'steamac-(vm|runtime)' 2>/dev/null)"} )
if (( ${#pids} == 0 )); then
  print -r -- 'No running steamac-vm or steamac-runtime found. If the app hangs, run this collector while it is unresponsive.' > "$out/processes.txt"
else
  for pid in "${pids[@]}"; do
    [[ "$pid" == <-> ]] || continue
    /bin/ps -p "$pid" -o pid=,ppid=,state=,rss=,%cpu=,etime=,comm= >> "$out/processes.txt"
    capture "sample-$pid.txt" 15 /usr/bin/sample "$pid" 3 10
  done
fi

capture bootstrap-stages.txt 15 /usr/bin/log show --last 10m --style compact \
  --predicate 'subsystem == "local.ryuu.steamac-lite.startup"'
# Restrict the system-log query to this app, rather than exporting all OS logs.
capture launch-policy.txt 15 /usr/bin/log show --last 10m --style compact --info \
  --predicate '(process == "syspolicyd" OR process == "amfid" OR process == "launchservicesd" OR process == "runningboardd" OR process == "taskgated-helper" OR process == "kernel") AND eventMessage CONTAINS[c] "steamac"'
capture signature.txt 30 /usr/bin/codesign --verify --deep --strict --verbose=2 "$app"
capture signing-info.txt 10 /usr/bin/codesign --display --verbose=2 "$app"
capture quarantine.txt 5 /usr/bin/xattr -p com.apple.quarantine "$app"

logfile="$HOME/Library/Logs/local.ryuu.steamac-lite/steamac-vm.log"
{
  if [[ -f "$logfile" ]]; then
    /usr/bin/stat -f 'launcher log: modified=%Sm bytes=%z' -t '%Y-%m-%dT%H:%M:%S%z' "$logfile"
    # Only launch banners; never copy the guest console, chat or account details.
    /usr/bin/tail -c 1048576 "$logfile" | /usr/bin/grep -F 'steamac Lite started (pid ' | /usr/bin/tail -5
  else
    print -r -- 'No launcher log found.'
  fi
} > "$out/launch-banners.txt"

# Redact home-directory paths before the results are shared. Other arbitrary
# personal strings may still appear in samples or OS logs; ask the user to review.
for file in "$out"/*.txt; do
  /usr/bin/perl -i -pe 's/\Q$ENV{HOME}\E/<HOME>/g; s{/Users/[^/\s"\x27]+}{/Users/<USER>}g' "$file"
done
print -r -- 'Completed. Review the text files before sharing; no files were sent.'
print -r -- "$out"
