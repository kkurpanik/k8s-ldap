## BigKube (Q/A, Production, etc)

Two parts to deploying CAM/Consume/Day2 etc, on Kubernetes:
1.  Generating the environment specific kubernetes files from the jinja templates
2.  Running the deploy script to apply the app (ie: consume) to your kubeneretes cluster

Follow the instructions laid out below.

**Note:** See configuration files in the `config` directory for extra control.

### Generating the K8 files from Jinja templates

The files located in `k8-templates/` are Python Jinja templating files.  The
templates, along with the configuration files (see: the `config/` directory)
are used to generate the kubernetes deployment templates.

Use the `./gen_k8.py` tool to generate the kubernetes templates for your
environment:

Example (for Consume):
```
$ ./gen_k8.py -n dev-consume -s hostpath -cf config/service_latest.json config/secrets.json config/storage.yml
```

#### Usage

Run `./gen_k8.py -h` for full usage information:

```
$ ./gen_k8.py -h
usage: gen_k8.py [-h] -n NAMESPACE -s {hostpath,nfs,bluemix} [-f FQDN]
                 [-i INPUT_DIR] [-o OUTPUT_DIR] [-d] [-q] [-c CONTEXT]
                 [-cf CONTEXT_FILES [CONTEXT_FILES ...]]

Generate Kubernetes files from Jinja templates

optional arguments:
  -h, --help            show this help message and exit
  -n NAMESPACE, --namespace NAMESPACE
                        Kubernetes namespace
  -s {hostpath,nfs,bluemix}, --storage-type {hostpath,nfs,bluemix}
                        Kubernetes storage type. Use "hostpath" for Minikube.
  -f FQDN, --fqdn FQDN  Application FQDN override. Used to compute
                        API_GATEWAY_URL & UI_HOST
  -i INPUT_DIR, --input_dir INPUT_DIR
                        K8 template input directory. Default is
                        "./k8-templates/"
  -o OUTPUT_DIR, --output_dir OUTPUT_DIR
                        Generated file output directory. Default is
                        "./k8-generated/". Contents WILL BE WIPED.
  -d, --dev_settings    Development settings (open NodePorts, etc)
  -q, --qa_settings     QA settings (open NodePorts, etc)
  -c CONTEXT, --context CONTEXT
                        Jinja context (key/value pars): -c a=1 -c b=2...
                        Override with JINJA__<key> ENV variables.
  -cf CONTEXT_FILES [CONTEXT_FILES ...], --context_files CONTEXT_FILES [CONTEXT_FILES ...]
                        Jinja context from JSON/YML files.
```

#### Setting credentials for docker image pulls

To deploy, you need to use your personal artifactory credentials to access the docker images on our Artifactory server.
You can generate an Artifactory API key at: [Artifactory Profile](https://na.artifactory.swg-devops.com/artifactory/webapp/#/profile)

*Note:* You need to be added as a member to the `afaas-ibmcb-read` bluegroup, and log into the Artifactory Web UI
before you can successfully pull docker images.

Set these environment variables.
```
$ export JINJA__ARTIFACTORY_USER="<yourArtifactoryUID>"
$ export JINJA__ARTIFACTORY_PASSWORD="<yourArtifactoryAPIKey>"
```

### Deploying the application

Use the `./deploy.py` tool to deploy the application to your k8 cluster

Example (for consume):
```
$ ./deploy.py -k ~/.kube/config -n dev-consume
```

#### Usage

Run `./deploy.py -h` for full usage information:

```
$ ./deploy.py -h
usage: deploy.py [-h] -k KUBECONFIG -n NAMESPACE [-t TEMPLATE_DIR] [-m] [-v]

Deploys a K8 application

optional arguments:
  -h, --help            show this help message and exit
  -k KUBECONFIG, --kubeconfig KUBECONFIG
                        Kubernetes config file. If running locally:
                        "~/.kube/config"
  -n NAMESPACE, --namespace NAMESPACE
                        Kubernetes namespace
  -t TEMPLATE_DIR, --template-dir TEMPLATE_DIR
                        Directory containing the kubernetes files. Default is
                        "./k8-generated/"
  -m, --minikube        Set if deploying to minikube.
  -v, --version-checks  Set to enable version checks.
```
