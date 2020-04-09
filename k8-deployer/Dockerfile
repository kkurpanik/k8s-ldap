FROM python:3.6.4-alpine3.7

# Install needed alpine packages
RUN apk add --no-cache bash gzip curl

# Stage kubectl clients (latest patch version per major version):
#   v1.5  :  1.5.8
#   v1.6  :  1.6.13
#   v1.7  :  1.7.16
#   v1.8  :  1.8.11
#   v1.9  :  1.9.6
#   v1.10 :  1.10.0
# Strategy:
#   1) Download kubectl from upstream
#   2) Make kubectl executable, compress it with gzexe, remove temp file, and test the exe
#   3) move kubectl to /usr/local/bin with version'd name
RUN for VERSION in 1.5.8 1.6.13 1.7.16 1.8.11 1.9.6 1.10.0; do \
        set -o errexit; set -o pipefail; set -o nounset; \
        echo "Processing version: $VERSION"; \
        curl -SLO "https://dl.k8s.io/v$VERSION/kubernetes-client-linux-amd64.tar.gz"; \
        tar -xzf kubernetes-client-linux-amd64.tar.gz --strip-components=3 kubernetes/client/bin/kubectl; \
        chmod +x ./kubectl; gzexe ./kubectl; rm "./kubectl~"; ./kubectl -h > /dev/null; \
        mv ./kubectl "/usr/local/bin/kubectl_${VERSION%.*}"; rm "kubernetes-client-linux-amd64.tar.gz"; \
    done

# Pull in our python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install -r /tmp/requirements.txt

# Install the app
ENTRYPOINT ["/app/k8-deployer/unwrap_kubectl.sh", "--"]
CMD ./run_deploy.sh
WORKDIR /app/k8-deployer
COPY . .
