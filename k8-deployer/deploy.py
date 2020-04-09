#! /usr/bin/env python
# =COPYRIGHT=======================================================
# Licensed Materials - Property of IBM
#
# (c) Copyright IBM Corp. 2017, 2017 All Rights Reserved
#
# US Government Users Restricted Rights - Use, duplication or
# disclosure restricted by GSA ADP Schedule Contract with IBM Corp.
# =================================================================
'''
deploy.py -- CLI to apply kubernetes templates to a remote k8 cluster
'''

import argparse
import glob
import os
import re
import subprocess
import sys
import time
import yaml

from utils import all_resource_names, run_kubecmd, run_minikubecmd, run_localcmd
from prune_namespace import prune_namespace


def main():
    '''
    Deploy a kubernetes application from pre-generated kubernetes templates
    '''
    parser = argparse.ArgumentParser(
        description='Deploys a K8 application')
    parser.add_argument(
        '-k', '--kubeconfig', required=True,
        help='Kubernetes config file.  If running locally: "~/.kube/config"')
    parser.add_argument(
        '-n', '--namespace', required=True,
        help='Kubernetes namespace')
    parser.add_argument(
        '-t', '--template-dir', default='./k8-generated/',
        help='Directory containing the kubernetes files.'
             '  Default is "./k8-generated/"')
    parser.add_argument(
        '-m', '--minikube', action='store_true',
        help='Set if deploying to minikube.')
    parser.add_argument(
        '-d', '--dockeredge', action='store_true',
        help='Set if deploying to docker edge.')
    parser.add_argument(
        '-v', '--version-checks', action='store_true',
        help='Set to enable version checks.')

    args = parser.parse_args()
    if args.minikube:
        local_extras(args.template_dir, True)
    elif args.dockeredge:
        local_extras(args.template_dir, False)
    # Run the deploy
    deploy(args.kubeconfig, args.namespace,
           args.template_dir, args.version_checks)


def local_extras(template_dir, minikube=False):
    '''
    Special handling for Local environments
    '''
    # Need to precreate the hostpath directories if running local
    for template in glob.glob(os.path.join(template_dir, 'storage', '*')):
        with open(template, "r") as tfile:
            docs = yaml.load_all(tfile, Loader=yaml.SafeLoader)
            for doc in docs:
                if doc['kind'] == 'PersistentVolume':
                    if 'hostPath' not in doc['spec']:
                        raise AssertionError("local_extras: template (%s) "
                                             "not using hostpath." % template)
                    if minikube:
                        cmd = 'sudo mkdir -p %s' % doc['spec']['hostPath']['path']
                        run_minikubecmd(cmd)
                    elif not os.path.exists(doc['spec']['hostPath']['path']):
                        cmd = ['sudo', 'mkdir', '-p',
                               doc['spec']['hostPath']['path']]
                        run_localcmd(cmd)
                        cmd = ['sudo', 'chmod', '777',
                               doc['spec']['hostPath']['path']]
                        run_localcmd(cmd)


def validate(kubeconfig, namespace, template_dir, version_checks):
    '''
    Verify args
    '''
    if not os.path.isfile(kubeconfig):
        raise AssertionError(
            "kubeconfig file does not exist: %s" % kubeconfig)

    with open(os.path.join(template_dir, 'namespace.yaml'), "r") as n_file:
        doc = yaml.load(n_file, Loader=yaml.SafeLoader)
        name_in_file = doc['metadata']['name']
        if doc['metadata']['name'] != namespace:
            raise AssertionError(
                "Namespaces do not match!!  From file: %s" % name_in_file)

    # verify kubectl client/server versions
    versions = [x.split(':')[1].strip() for x in (subprocess.check_output(
        ['kubectl', 'version', '--short=true'],
        universal_newlines=True).strip().split('\n'))]
    if versions[0] != versions[1]:
        message = (
            "kubectl version mismatch -- Install matching client.\n"
            "Client :%s\n"
            "Server :%s\n" % (versions[0], versions[1]))
        if version_checks:
            raise AssertionError(message)
        else:
            print("\033[33mWarning: %s\033[39m" % message)


def parse_details(describe, regex_list):
    '''
    Parses `kubectl describe` output, and returns list of regex matches
    '''
    compiled_list = [re.compile(x) for x in regex_list]
    result_list = len(compiled_list) * [None]  # preallocate
    for line in describe.splitlines():
        for index, element in enumerate(compiled_list):
            match = element.match(line)
            if match:
                result_list[index] = match.group(1)
    return result_list


def wait(fun, namespace, name, num_tries):
    '''
    Closure to wait until fun returns True
    '''
    result = None
    count = 0
    for count in range(num_tries):
        result = fun(namespace, name, count)
        if not result:
            if count == 0:
                print("\033[33mWaiting on %s(%s,%s)..." %
                      (fun, namespace, name))
            time.sleep(5)  # 5 sec sleep
            sys.stdout.write('.')
            sys.stdout.flush()
        else:
            break
    if count != 0:
        print('\033[39m')  # Write the newline / clear colors
    if not result:
        raise AssertionError("Condition not met %s(%s,%s)" %
                             (fun, namespace, name))


def is_deployment_online(namespace, deployment, _count):
    '''
    Return True/False reflecting whether a deployment is running
    '''
    # output is different depending on v1.5 or v1.7 clients:
    #   v1.5: Replicas:		1 updated | 1 total | 1 available | 0 unavailable
    #   v1.7: Replicas:		1 desired | 1 updated | 1 total | 1 available | 0 unavailable
    result = parse_details(run_kubecmd(namespace,
                                       ['describe', 'deployment', deployment]),
                           [r'^Replicas:.*(\d) total',
                            r'^Replicas:.*(\d) available'])
    # True if total == available (and is a valid non-zero number)
    return result[0] and int(result[0]) > 0 and result[0] == result[1]


def is_job_done(namespace, job, count):
    '''
    Return True/False reflecting whether a Job has completed.  If Job fails,
    an AssertionError is raised.
    '''
    # Pods Statuses:	1 Running / 0 Succeeded / 0 Failed
    result = parse_details(run_kubecmd(namespace,
                                       ['describe', 'job', job]),
                           [r'^Pods Statuses:.*(\d) Running',
                            r'^Pods Statuses:.*(\d) Succeeded',
                            r'^Pods Statuses:.*(\d) Failed'])

    if not result[0]:
        return True  # not able to find valid data -- keep polling

    num_running = int(result[0])
    num_succeed = int(result[1])
    num_failure = int(result[2])
    if num_running != 0:
        return False  # still running
    if num_running == 0 and num_succeed == 0 and num_failure == 0:
        if count > 120:  # 120 tries w/ 5sec sleep == 10min
            raise AssertionError("Job refuses to start after 10min.")
        return False  # hasn't even started yet
    if num_succeed == 0 and num_failure != 0:  # something failed
        raise AssertionError("Job %s failed.  Running: %s, Succeeded: %s, Failed: %s" %
                             (job, num_running, num_succeed, num_failure))
    return True  # job is done successfully


def wait_online(namespace, k8_template):
    '''
    For supported types, will attempt to wait for the applied resources
    to be online
    '''
    with open(k8_template, 'r') as k_file:
        parsed_template = yaml.safe_load_all(k_file)
        for doc in parsed_template:
            kind = doc['kind']
            if kind == 'Deployment':
                # 120 retries w/ 5-sec sleeps == 10 minutes
                wait(is_deployment_online, namespace,
                     doc['metadata']['name'], 120)
            elif kind == 'Job':
                # 3600 retries w/ 5-sec sleeps == 5 hours
                wait(is_job_done, namespace, doc['metadata']['name'], 3600)
            else:
                print("Don't know how to wait_online for type: %s" % kind)


def run_kubeapply(namespace, base_dir, file_or_dir,
                  ignore_not_exist=False, only_depend=False):
    '''
    Applies kube-config from a directory
    '''
    if ignore_not_exist and (
            not os.path.exists(os.path.join(base_dir, file_or_dir))):
        # ignore if file_or_dir not exists (and flag allows us)
        return

    # Load the optional '.depend.start' file and apply each reference in turn
    depend_start_path = os.path.join(base_dir, file_or_dir, '.depend.start')
    if os.path.exists(depend_start_path):
        with open(depend_start_path, "r") as d_file:
            files = yaml.load(d_file, Loader=yaml.SafeLoader)
            for f_name in files:
                k8_template = os.path.join(base_dir, file_or_dir, f_name)
                print(run_kubecmd(namespace,
                                  ['apply', '-f',
                                   k8_template]))
                wait_online(namespace, k8_template)
    else:
        # no .depend.start file, force only_depend to fals to process directory
        only_depend = False

    # Now Load the entire directory
    if not only_depend:
        print(run_kubecmd(namespace,
                          ['apply', '-f', os.path.join(base_dir, file_or_dir)]))


def wait_storage_online(namespace):
    '''
    Polls PVCs status and waits until all are bound
    '''
    not_bound = None
    count = 0
    for count in range(120):  # 120 retries w/ 5-sec sleeps == 10 minutes
        pvcs = run_kubecmd(namespace, ['get', 'pvc']).splitlines()[1:]
        not_bound = [s for s in pvcs if "Bound" not in s]
        if not_bound:
            if count == 0:
                print('\033[33mWaiting for all PersistentVolumeClaims '
                      '(PVCs) to be bound...')
            time.sleep(5)  # 5 sec sleep
            sys.stdout.write('.')
            sys.stdout.flush()
        else:
            break
    if count != 0:
        print('\033[39m')  # Write the newline / clear colors
    if not_bound:
        raise AssertionError("PVCs not 'Bound':\n%s" % (not_bound))


def delete_all_jobs(namespace, retry_count=0):
    '''
    deletes all jobs (Aborts if any are running)
    '''
    all_jobs = all_resource_names(namespace, 'Job')
    for job in all_jobs:
        done = False
        try:
            done = is_job_done(namespace, job, 0)
        except AssertionError:
            done = True
        except subprocess.CalledProcessError as cpe:
            if "not found" in cpe.output:
                done = True
            else:
                raise  # the original error

        if not done:
            if retry_count > 6:
                raise AssertionError(
                    'Running job: %s detected.  Aborting deployment.' % job)
            print('Warning: Running jobs detected: %s, retrying in 10 seconds...' % job)
            time.sleep(10)  # sleep 5-seconds
            delete_all_jobs(namespace, retry_count+1)  # recurse

    # if we made it this far, there are no running jobs (safe to delete)
    if all_jobs:
        # delete all jobs
        print('Deleting all jobs: ' + run_kubecmd(namespace,
                                                  ['delete', 'jobs', '--all']))


def deploy(kubeconfig, namespace, template_dir, version_checks):
    '''
    Runs the k8 deployment process
    '''
    # set the environment
    os.environ['KUBECONFIG'] = kubeconfig

    # run validations
    validate(kubeconfig, namespace, template_dir, version_checks)

    # delete all jobs (will abort if any are running)
    delete_all_jobs(namespace)

    # run through the deployment
    run_kubeapply(namespace, template_dir, 'namespace.yaml')

    # optional directories (in order)
    run_kubeapply(namespace, template_dir, 'secrets/',
                  ignore_not_exist=True)
    run_kubeapply(namespace, template_dir, 'storage/',
                  ignore_not_exist=True)

    # wait for storage to come online
    wait_storage_online(namespace)

    run_kubeapply(namespace, template_dir, 'configmaps/',
                  ignore_not_exist=True)
    run_kubeapply(namespace, template_dir, 'services/',
                  ignore_not_exist=True)
    run_kubeapply(namespace, template_dir, 'deployments/',
                  ignore_not_exist=True)
    run_kubeapply(namespace, template_dir, 'statefulsets/',
                  ignore_not_exist=True)
    run_kubeapply(namespace, template_dir, 'daemonsets/',
                  ignore_not_exist=True)
    run_kubeapply(namespace, template_dir, 'jobs/',
                  ignore_not_exist=True, only_depend=True)
    run_kubeapply(namespace, template_dir, 'cronjobs/',
                  ignore_not_exist=True, only_depend=True)
    # Now run everything at the base template_dir
    run_kubeapply(namespace, template_dir, '.')

    # Find leaked objects and delete them
    prune_namespace(namespace, template_dir)


if __name__ == "__main__":
    main()
