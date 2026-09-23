#!/bin/sh
# Runs outside the .app after the old MAW-bd process exits.
set -eu

old_pid=$1
current=$2
staged=$3
backup=$4
result=$5
skip_open=${6:-}

write_result() {
  printf '%s\n' "$1" > "$result"
}

count=0
while kill -0 "$old_pid" 2>/dev/null; do
  count=$((count + 1))
  if [ "$count" -ge 300 ]; then
    write_result 'error|等待旧版退出超时，更新未安装'
    exit 1
  fi
  sleep 0.2
done

if [ ! -d "$current" ] || [ ! -d "$staged" ] || [ -e "$backup" ]; then
  write_result 'error|更新文件状态异常，旧版未被替换'
  exit 1
fi
if ! /bin/mv "$current" "$backup"; then
  write_result 'error|无法备份旧版应用'
  exit 1
fi
if ! /bin/mv "$staged" "$current"; then
  /bin/mv "$backup" "$current" || true
  write_result 'error|安装新版失败，已尝试恢复旧版'
  if [ "$skip_open" != '--no-open' ]; then /usr/bin/open -a "$current" || true; fi
  exit 1
fi
write_result 'ok|更新已安装并重启'
if [ "$skip_open" != '--no-open' ]; then
  /usr/bin/open -a "$current" || write_result 'error|新版已安装，但自动重启失败'
fi
