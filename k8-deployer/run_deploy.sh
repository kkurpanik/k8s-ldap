#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail
set -x

#
# Function to log messages (with date/time stamps)
#
function log() {
  if [ -z "${2:-}" ]; then
    echo -e "\\033[34m$(date) [$BASHPID]:\\033[32m $1\\033[39m" # stdout
  else
    echo >&2 -e "\\033[34m$(date) [$BASHPID]:\\033[31m $1 $2\\033[39m" # stderr
  fi
}

#
# Function to prove an ENV variable is defined
#
function check_env_var() {
  # $1 -- environment variable name to check
  if [ -z "${!1:-}" ]; then
    log ERROR "Required ENV variable: $1 not defined."
    exit 1
  fi
  log "  $1 == ${!1}"
}

#
# Function to prove an ENV is defined and refers to an existing Directory
#
function check_env_file() {
  # $1 -- environment variable name to check
  check_env_var "$1" # ensure this ENV variable is defined
  if [ ! -f "${!1}" ]; then # ensure it points to an actual file
    log ERROR "File for $1 (${!1}) does not exist."
    exit 1
  fi
}

#
# Closure function to run function specified by $1, against each of
# the remaining arguments in a loop
#
function for_each() {
  # $1 function
  # $2+ expanded array of stuff (which will be passed to $1 individually)
  for var in "${@:2}"; do # loop through every arg (except the first)
    $1 "$var"
  done
}

# ENV variable checks
for_each check_env_var APP_NAME NAMESPACE STORAGE
for_each check_env_file KUBECONFIG MANIFEST_FILE

# env | grep -a "^APP_NAME\|^KUBECONFIG\|^NAMESPACE\|^STORAGE\|^MANIFEST_FILE\|^JINJA__" > envs
# Pipe that to an "envs" file, and then run docker with:
#   docker run --rm --env-file envs devops-core deploy.sh

BASEDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Generate the templates
pushd "../devops-${APP_NAME,,}" > /dev/null
"$BASEDIR/gen_k8.py" ${QA_OPT:-} -n "$NAMESPACE" -s "${STORAGE}" \
   ${GATEWAY_KEY_OPT:-} \
   -cf config/secrets.json config/storage.yml "${MANIFEST_FILE}"

# Deploy it
"$BASEDIR/deploy.py" -k "$KUBECONFIG" -n "$NAMESPACE"
popd
