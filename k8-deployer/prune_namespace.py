'''
Namespace cleaner -- to remove kubernetes objects from the namespace that
should not exist.
'''

import os
import yaml

from utils import all_resource_names, run_kubecmd

def _get_current_state(namespace):
    # dictionary where:
    #   key: kubernetes resource type (Kubernetes Kind)
    # value: list of names of resources in the namespace
    return {
        'ConfigMap': all_resource_names(namespace, 'ConfigMap'),
        'Deployment': all_resource_names(namespace, 'Deployment'),
        'Job': all_resource_names(namespace, 'Job'),
        'PersistentVolumeClaim': all_resource_names(namespace, 'PersistentVolumeClaim'),
        'Secret': [l for l in all_resource_names(namespace, 'Secret')
                   if not l.startswith('default-token')],
        'Service': [l for l in all_resource_names(namespace, 'Service')
                    if not l.startswith('glusterfs')]
    }


def _get_template_resources(template_dir):
    # dictionary where:
    #   key: kubernetes resource type
    # value: list of names of resources in the namespace
    result = {}
    for subdir, _dirs, files in os.walk(template_dir):
        for file in files:
            if file.endswith('.yaml') or file.endswith('.yml') or file.endswith('.json'):
                with open(os.path.join(subdir, file), 'r') as k_file:
                    docs = yaml.safe_load_all(k_file)
                    for doc in docs:
                        kind = doc['kind']
                        name = doc['metadata']['name']
                        if kind not in result:
                            result[kind] = []
                        result[kind].append(name)
    return result


def _diff(current, expected):
    '''
    Diffs the two dictionaries (SUBTRACT expected FROM current) -- to leave
    us with a dictionary containing things that should be deleted
    '''
    result = {}
    for key, val in current.items():
        if key in expected:
            result[key] = list(set(val) - set(expected[key]))
        else:
            result[key] = val
    result = {k:v for (k, v) in result.items() if v} # remove empties
    return result

def prune_namespace(namespace, template_dir, dry_run=False):
    '''
    Compare the k8-namespace to what is defined in template_dir, report
    on (and optionally auto_prune) objects that should not exist in the namespace
    '''
    if not os.path.isdir(template_dir):
        raise AssertionError("Path either does not exist, or is not a directory: %s"
                             % template_dir)
    current_state = _get_current_state(namespace)
    expected_state = _get_template_resources(template_dir)
    diff = _diff(current_state, expected_state)
    for res_type, resources in diff.items():
        if dry_run:
            print("\033[31mFound extraneous %s records: %s.  These should be "
                  " removed...\033[39m" % (res_type, resources))
        else:
            for resource in resources:
                print("\033[33mDeleting extraneous %s: %s ...\033[39m" % (res_type, resource))
                run_kubecmd(namespace, ['delete', res_type, resource])
