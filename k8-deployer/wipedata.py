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
Mounts all PVCs and `rm -rf` their contents
'''

import argparse
import os
import sys
import time

# External dependencies
from deploy import wait_online
from gen_k8 import gen_jinja
from utils import run_kubecmd, all_resource_names


def main():
    '''
    CLI to wipe (rm -rf) the contents of all PVCs in a namespace
    '''
    parser = argparse.ArgumentParser(
        description='CLI to wipe (rm -rf) all PVCs in a namespace')
    # Required
    required_group = parser.add_argument_group('required arguments')
    required_group.add_argument(
        '-k', '--kubeconfig', required=True,
        help='Kubernetes config file.  If running locally: "~/.kube/config"')
    required_group.add_argument(
        '-n', '--namespace', required=True,
        help='Kubernetes namespace')

    group = parser.add_argument_group(
        'Single PVC', 'Options for working on a single PVC.')
    group.add_argument(
        '-p', '--pvc', required=False,
        help='PVC name')
    group.add_argument(
        '-s', '--subpath', required=False,
        help='Optional subpath directory on the specified PVC')

    args = parser.parse_args()
    if args.subpath and not args.pvc:
        sys.exit('Error: -s (--subpath) is only valid with -p (--pvc)')

    kubeconfig = args.kubeconfig

    if not os.path.isfile(kubeconfig):
        raise AssertionError(
            "kubeconfig file does not exist: %s" % kubeconfig)

    os.environ['KUBECONFIG'] = kubeconfig # set the environment

    if args.pvc:
        print('Wiping: %s/%s (subpath: %s) in 10 seconds...'
              % (args.namespace, args.pvc, args.subpath))
        time.sleep(10)
        _wipe_pvc(args.pvc, args.subpath, args.namespace)
    else:
        print('WIPING ALL PVCS IN %s, in 10 seconds...' % args.namespace)
        time.sleep(10)
        _wipe_all_pvs(args.namespace) # wipe the PVCs


def _wipe_pvc(pvc, subpath, namespace,
              working_dir=os.path.dirname(os.path.abspath(__file__))):
    '''
    Spawn a job to `rm -rf` the PVC files, then wait for job to complete
    '''
    job_name = 'wipe-%s' % pvc
    context = {
        'JOB_NAME': job_name,
        'PVC_CLAIM_TO_DELETE': pvc
    }

    if subpath:
        context['SUBPATH'] = subpath # subpath wiping

    gen_jinja(context,
              os.path.join(working_dir, './utilities', 'pvc_recycler'),
              os.path.join(working_dir, './k8-generated', 'pvc_recycler'))
    template = os.path.join(working_dir, './k8-generated', 'pvc_recycler',
                            'pvc_recycler.yml')

    try:
        print('Starting job: %s' % job_name)
        print(run_kubecmd(namespace, ['apply', '-f', template]))
        print('Waiting for job: %s to complete.' % job_name)
        wait_online(namespace, template)
    finally:
        print('Deleting job: %s' % job_name)
        print(run_kubecmd(namespace, ['delete', 'job', job_name]))


def _wipe_all_pvs(namespace):
    '''
    Find all PVCs, and wipe their contents
    '''
    pvcs = all_resource_names(namespace, 'pvc')
    print('PVCs to wipe: %s' % pvcs)
    for pvc in pvcs:
        _wipe_pvc(pvc, None, namespace)


if __name__ == "__main__":
    main()
