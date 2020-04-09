#!/bin/bash
set -o errexit
set -o pipefail
set -o nounset

# Wrapper script to determine best kubectl client version to use and adds it
# to the PATH.  Available versions are gzexe compressed executables located in:
#   /usr/local/bin/kubectl_#.#

function set_version() {
  # $1 == MAJOR.MINOR kubectl version (ex: 1.5, 1.6, 1.7, ....)
  if [ -f "/usr/local/bin/kubectl_$1" ]; then
    # make default & decompress
    cp "/usr/local/bin/kubectl_$1" "/usr/local/bin/kubectl"
    gzexe -d "/usr/local/bin/kubectl" # decompress the script EXE
    rm "/usr/local/bin/kubectl~" # delete orig/temp file
  else
    "File does not exist for version $1: /usr/local/bin/kubectl_$1"
    exit 1
  fi
}

if [ -z "${KUBECONFIG:-}" ]; then
  echo >&2 -e "\\033[34m$(date) [$BASHPID]:\\033[31m ERROR: Required ENV variable: KUBECONFIG not defined. \\033[39m"
  exit 1
fi

if [ ! -e "$KUBECONFIG" ]; then
  echo >&2 -e "\\033[34m$(date) [$BASHPID]:\\033[31m ERROR: KUBECONFIG file: ($KUBECONFIG) does not exist. \\033[39m]"
  exit 1
fi

if [ ! -z "${FORCE_KUBECTL_VERSION:-}" ]; then
  # force override
  set_version "$FORCE_KUBECTL_VERSION"
else
  # Find the closest matching kubectl client and make it the default (in path)
  #   Ex: Server Version: v1.7.4-2+0e12de790169f6
  #       Should use /usr/local/bin/kubectl_1.7
  kubectl_server_version=$(/usr/local/bin/kubectl_1.9 version --short=true | grep -E "^Server Version:.*$")
  regex="Server Version: v([[:digit:]]+\\.[[:digit:]]+).*"
  if [[ $kubectl_server_version =~ $regex ]]; then
    maj_min_version="${BASH_REMATCH[1]}"  # (Example: '1.8')
    set_version "$maj_min_version"
  else
    echo "Unable to parse kubectl server version: $kubectl_server_version"
    exit 1
  fi
fi

exec "$@"
