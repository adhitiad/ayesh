---
name: shell-scripting
description: "Penulisan script shell Bash & debugging. Trigger: /shell"
---

# Shell Scripting

## Best Practices
```bash
#!/bin/bash
set -euo pipefail

# Error handling
trap 'echo "Error on line $LINENO" >&2' ERR
```

## Variables
```bash
VAR="value"
VAR=$(command)
echo $VAR
echo ${VAR:-default}
echo ${VAR:+if_set}
echo ${VAR:=if_unset}
echo ${#VAR}           # length
echo ${VAR%pattern}    # remove suffix
echo ${VAR#pattern}    # remove prefix
```

## Conditionals
```bash
# File tests
if [ -f file ]; then
fi
if [ -d dir ]; then
fi
if [ -r file ]; then    # readable
fi
if [ -w file ]; then    # writable
fi
if [ -s file ]; then    # non-empty
fi

# String
if [ "$a" = "$b" ]; then
fi
if [ -z "$var" ]; then   # empty
fi
if [ -n "$var" ]; then   # not empty
fi

# Numeric
if [ $a -eq $b ]; then   # equal
if [ $a -ne $b ]; then   # not equal
if [ $a -gt $b ]; then   # greater than
if [ $a -lt $b ]; then   # less than

# Bash
if [[ "$var" =~ regex ]]; then
if [[ $a == $b ]]; then
```

## Loops
```bash
# For
for i in 1 2 3; do
    echo $i
done

for f in *.txt; do
    echo "$f"
done

for ((i=0; i<10; i++)); do
    echo $i
done

# While
while read line; do
    echo "$line"
done < file.txt

# Until
until ping -c1 host; do
    sleep 1
done
```

## Functions
```bash
my_func() {
    local arg="$1"
    echo "Processing: $arg"
    return 0
}

my_func "data"
```

## Error Handling
```bash
set -e    # exit on error
set -u    # error on unset variable
set -o pipefail

command || { echo "Failed"; exit 1; }
command && echo "Success"

# Trap
cleanup() {
    echo "Cleaning up..."
}
trap cleanup EXIT
```

## Common Patterns

### Menu
```bash
PS3="Pilih opsi: "
select opt in "Option 1" "Option 2" "Quit"; do
    case $opt in
        "Option 1") echo "Selected 1" ;;
        "Option 2") echo "Selected 2" ;;
        "Quit") break ;;
    esac
done
```

### Reading Input
```bash
echo -n "Username: "
read username
read -p "Password: " -s password
read -p "Path [/default]: " path
path=${path:-/default}
```

### Processing File
```bash
while IFS=, read -r col1 col2 col3; do
    echo "$col1 $col2 $col3"
done < data.csv
```

### Parallel Execution
```bash
cmd1 &
cmd2 &
cmd3 &
wait
echo "All done"
```

### Argument Parsing
```bash
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--file) FILE="$2"; shift 2 ;;
        -v) VERBOSE=1; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done
```

## Debugging
```bash
bash -x script.sh
set -x
set +x

shellcheck script.sh

echo "Debug: $var"
printf "Debug: %s\n" "$var"
```

## String Manipulation
```bash
string="Hello World"
echo ${string:0:5}     # substr
echo ${string^}        # capitalize
echo ${string,,}       # lowercase
echo ${string//o/0}    # replace
echo ${string// /_}    # replace spaces
```

## Arithmetic
```bash
echo $((1+2))
result=$((a+b))
((result++))
declare -i var=0
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Script tidak jalan | `bash -x`, cek shebang |
| Variable unset | `set -u`, gunakan `${var:-default}` |
| Special chars | Quote variabel: `"$var"` |
| Script lambat | Hindari subshell, gunakan builtins |
| Error handling | `set -euo pipefail`, `trap` |
