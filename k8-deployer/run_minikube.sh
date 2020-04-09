#!/bin/bash

check_initial_user() {
    if (grep -Eq "PREAUTH_INITIAL_USER.*\"\"" < config/secrets.json); then
      if [ -z "${JINJA__PREAUTH_INITIAL_USER:-}" ] ; then
        echo -e "\\033[33mPREAUTH_INITIAL_USER not set -- consider adding your BlueID to config/secrets.json\\033[39m"
      fi
    fi
}

check_etchosts() {
    if ! (grep -Eq "^[^#]?[[:blank:]]*$1[[:blank:]]+$KUBENAME" < /etc/hosts); then
        echo -e "\\033[33mMissing /etc/hosts entry for $KUBENAME:\\n$1\\t\\t$KUBENAME\\033[39m\\n\\n"
        if (grep -Eq "$KUBENAME" < /etc/hosts); then
           echo -e "\\033[31mInvalid entry for $KUBENAME found in /etc/hosts.  Please remove and re-run.\\033[39m"
           exit 1
        fi

        # Update /etc/hosts (some environments don't have sudo)
        echo -e "\\033[33mAdding entry.  Enter your password if prompted.\\033[39m"
        if hash sudo 2>/dev/null; then # see if sudo exists
          echo -e "$1\\t\\t$KUBENAME" | sudo tee -a /etc/hosts
        else # try without sudo
          echo -e "$1\\t\\t$KUBENAME" | tee -a /etc/hosts
        fi

        # shellcheck disable=SC2181
        if [ $? -ne 0 ]; then
          echo -e "\\033[31mFailed to add entry to /etc/hosts.  Please manually add the entry and re-run.\\033[39m"
          exit 1
        fi
    fi
}

check_secrets_docker_cfg() {
      if [ -z "${JINJA__ARTIFACTORY_USER:-}" ] ; then
        echo -e "\\033[31mJINJA__ARTIFACTORY_USER not set -- add your Artifactory credentials as environment variables.\\033[39m"
        exit 1
      fi
      if [ -z "${JINJA__ARTIFACTORY_PASSWORD:-}" ] ; then
        echo -e "\\033[31mJINJA__ARTIFACTORY_PASSWORD not set -- add your Artifactory credentials as environment variables.\\033[39m"
        exit 1
      fi
}

check_minikube() {
    # Assert that minikube is up
    if ! OUTPUT=$(minikube status); then
        echo -e "\\033[33m'minikube status':\\n$OUTPUT\\033[39m\\n"
        echo -e "\\033[31mMinikube does not appear to be running, try 'minikube start'?\\033[39m"
        exit 1
    fi
}


check_tiller(){
    # Assert the helm
    helm version
    if [ $? -ne 0 ]; then
        echo -e "\\033[31mHelm does not appeared as installed, Please install Helm\\033[39m"
        exit 1
    fi
    # Assert tiller
    tillername=`kubectl get pods --all-namespaces -o json  | jq -r '.items[] | select( .status.conditions[] | select((.type == "Ready") and (.status == "True")))| select(.metadata.labels.name == "tiller") | .metadata.labels.name'`
    if [ "$tillername" != "tiller" ]; then
        echo -e "\\033[31mTiller does not appear to be running, Please enable tiller\\033[39m"
        exit 1
    fi
}

deploy() {
    set +o errexit  # I'll check my own codes
    # Script for use by development to deploy the application on a local cluster
    echo -e "\\033[32mDeploying namespace: \\033[34m$1\\033[32m ...\\033[39m"

    # If minikube make sure he is around and ready for us
    if [ "$MINIKUBE" -eq 1 ]; then
        check_minikube
        LOCAL_IP=$(minikube ip)
        # shellcheck disable=SC2181
        if [ $? -ne 0 ]; then
            echo -e "\\033[33m'minikube ip':\\n$LOCAL_IP\\033[39m\\n"
            echo -e "\\033[31mUnable to determine 'minikube ip'.\\033[39m"
            exit 1
        fi
    else
        LOCAL_IP=127.0.0.1
    fi

    check_etchosts "$LOCAL_IP"  # verify /etc/hosts file entry
    check_secrets_docker_cfg
    check_initial_user

    # generate the k8 template files w/ DEV settings enabled
    set -o errexit
    python k8-deployer/gen_k8.py -n "$1" -s hostpath --dev_settings \
       -c "UI_HOST=$KUBENAME" \
       -c "UI_URL=https://$KUBENAME:$2" \
       -c "GATEWAY_HOST=$KUBENAME" \
       -c "MUTUAL_AUTH_GATEWAY_HOST=$KUBENAME" \
       -c "API_GATEWAY_URL=https://$KUBENAME:$3" \
       -cf config/service_latest.json config/secrets.json config/storage.yml

    # deploy to docker edge cluster
    if [ "$MINIKUBE" -eq 1 ]; then
        python k8-deployer/deploy.py -k "$KUBECONFIG" -n "$1" -m
    else
        python k8-deployer/deploy.py -k "$KUBECONFIG" -n "$1" -d
    fi


    echo -e ""
    echo -e "\\033[32mDeployment initiated.  It may take some time to complete. \\033[39m"
    echo -e "\\033[32mIf a first-time deployment, it will take ~15 minutes to download images. \\033[39m"
    echo -e ""
    echo -e "\\033[32mK8 Dashboard:\\t\\033[34m http://$KUBENAME:30000/#!/pod?namespace=$1 \\033[39m"
}

helm_deploy(){
    set +o errexit  # I'll check my own codes
    # Script for use by development to deploy the application on a local cluster
    echo -e "\\033[32mDeploying namespace: \\033[34m$1\\033[32m ...\\033[39m"

    # If minikube make sure he is around and ready for us
    if [ "$MINIKUBE" -eq 1 ]; then
        check_minikube
        LOCAL_IP=$(minikube ip)
        # shellcheck disable=SC2181
        if [ $? -ne 0 ]; then
            echo -e "\\033[33m'minikube ip':\\n$LOCAL_IP\\033[39m\\n"
            echo -e "\\033[31mUnable to determine 'minikube ip'.\\033[39m"
            exit 1
        fi
    else
        LOCAL_IP=127.0.0.1
    fi

    check_etchosts "$LOCAL_IP"  # verify /etc/hosts file entry
    check_secrets_docker_cfg
    check_tiller

    #Do helm lint test should pass
    helm lint ./charts/stable/$4

    if [ $? -ne 0 ]; then
        echo "Please fix the lint/yaml/rendering errors"
        exit 1
    fi

    #Install or Upgrade core application
    echo "Installing $1 application..."
    helm upgrade --install --wait --timeout 1800 --namespace "$1"  "$1" ./charts/stable/$4 \
    --set imageCredentials.registry=ibmcb-docker-local.artifactory.swg-devops.com,imageCredentials.username=${JINJA__ARTIFACTORY_USER},imageCredentials.password=${JINJA__ARTIFACTORY_PASSWORD},gatewayhost=${KUBENAME},mutualAuthGatewayHost=${KUBENAME},apiGatewayUrl=https://${KUBENAME}:$3,uiUrl=https://${KUBENAME}:$2,uiHost=${KUBENAME}

    echo -e ""
    echo -e "\\033[32mDeployment initiated.  It may take some time to complete. \\033[39m"
    echo -e "\\033[32mIf a first-time deployment, it will take ~15 minutes to download images. \\033[39m"
    echo -e ""
    echo -e "\\033[32m Dashboard:\\t\\033[34m http://$KUBENAME:30000/#!/pod?namespace=$1 \\033[39m"
}

delete() {
    echo -e "\\033[32mDeleting namespace: \\033[34m$1\\033[32m ...\\033[39m"
    set +o errexit
    # k8 1.13 -- need to delete deployments first, otherwise PVCs won't delete (stalls)
    kubectl delete deployments -n "$1" --all > /dev/null 2>&1
    # delete storage (really just need to delete the PV's which live outside the namespace)
    kubectl --namespace="$1" delete -f k8-generated/storage/
    kubectl delete namespace "$1"
    sleep 1

    # Wait until the namespace is gone
    first_time=true
    while kubectl get namespace "$1" > /dev/null
    do
      if [ "$first_time" = true ] ; then
        first_time=false
        echo -e "\\033[33mWaiting for namespace: \\033[34m$1\\033[33m to be removed...\\033[39m"
      else
        echo -en "\\033[33m.\\033[39m" # a single yellow dot, no newline
      fi
      sleep 10
    done

    set -o errexit
    echo ''
    echo -e "\\033[32mNamespace: \\033[34m$1\\033[32m has been removed.\\033[39m"
}

helm_delete() {
    echo -e "\\033[32mDeleting namespace: \\033[34m$1\\033[32m ...\\033[39m"
    set +o errexit
    # Delete jobs before update
    echo "Deleting jobs..."
    kubectl --kubeconfig=$KUBECONFIG --namespace=$NAMESPACE delete jobs --all --cascade=false

    # Delete helm deployments
    echo "Purging helm release..."
    helm delete "$1" --purge 2>/dev/null
    # Deleting Namespace
    echo "Deleting namespace..."
    kubectl delete namespace "$1" 2>/dev/null
    sleep 1

    # Wait until the namespace is gone
    first_time=true
    while kubectl get namespace "$1" 2> /dev/null
    do
      if [ "$first_time" = true ] ; then
        first_time=false
        echo -e "\\033[33mWaiting for namespace: \\033[34m$1\\033[33m to be removed...\\033[39m"
      else
        echo -en "\\033[33m.\\033[39m" # a single yellow dot, no newline
      fi
      sleep 10
    done
    set -o errexit
    echo ''
    echo -e "\\033[32mNamespace: \\033[34m$1\\033[32m has been removed.\\033[39m"  
}

help() {
  echo -e "usage: run-local.sh <namespace> [--helm] [--delete]"
  echo -e ""
  echo -e "Deploys the application into local kubernetes"
  echo -e ""
  echo -e "required arguments:"
  echo -e "  <namespace>  The Local namespace name (ie: dev-consume)"
  echo -e ""
  echo -e "optional arguments:"
  echo -e "  --delete     Deletes existing deployment."
  echo -e "  -h           Print this help message."
  echo -e " --helm        install via helm "
}

KUBECONFIG="$HOME/.kube/config" # set to local kube config
if hash cygpath 2>/dev/null; then
  # Windows/Cygwin support
  KUBECONFIG="$(cygpath -w ~)\\.kube\\config"
fi

NAMESPACE=$1
if [ "$NAMESPACE" == '-h' ]; then
    help
    exit 0
fi

UI_PORT=$2
GATEWAY_PORT=$3

MINIKUBE=0
KUBENAME="mydocker.edge"
CURR_CONTEXT=$(kubectl config current-context)
if [ "$CURR_CONTEXT" != "docker-for-desktop" ] && [ "$CURR_CONTEXT" != "docker-desktop" ]; then
    KUBENAME="myminikube.info"
    MINIKUBE=1
fi

set +o nounset
if [ -z "$4" ]; then
    set -o nounset
    deploy "$NAMESPACE" "$UI_PORT" "$GATEWAY_PORT"
elif [ "$4" == '--delete' ]; then
    delete "$NAMESPACE"
elif [ "$5" == '--helm' ]; then
    HELM_PACAKGE=$4
    if [ "$6" == '--delete' ]; then
      helm_delete "$NAMESPACE"
    else
      helm_deploy "$NAMESPACE" "$UI_PORT" "$GATEWAY_PORT" "$HELM_PACAKGE"
    fi
else
    help
    echo -e ""
    echo -e "\\033[31mUnknown arg: $4 \\033[39m"
    exit 1
fi
