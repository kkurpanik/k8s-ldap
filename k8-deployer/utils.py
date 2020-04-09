'''
Utility functions
'''

import subprocess
import time

def run_localcmd(command_args):
    '''
    Runs a command loccally
    '''
    command_args = command_args if isinstance(command_args, (list, tuple)) else [command_args]
    subprocess.check_call(command_args)



def run_minikubecmd(command_args):
    '''
    Runs a command while inside a Minikube SSH session
    '''
    command_args = command_args if isinstance(command_args, (list, tuple)) else [command_args]
    subprocess.check_call(['minikube', 'ssh'] + command_args)


def run_kubecmd(namespace, command_args, retry_count=0):
    '''
    Runs kubectl CLI against a namespace
    '''
    try:
        return subprocess.check_output(
            ['kubectl', "--namespace=%s" % namespace] + command_args,
            universal_newlines=True).strip()
    except subprocess.CalledProcessError as cpe:
        # could use @retrying package, but don't want to pull in an outside pip dependency
        if retry_count > 2: # max retries
            raise cpe # done with retries
        print('Warning: kubectl CalledProcessError: %s, retrying in 5 seconds...' % cpe)
        time.sleep(5) # sleep 5-seconds
        return run_kubecmd(namespace, command_args, retry_count+1)



def all_resource_names(namespace, resource_type):
    '''
    Returns list of names of all resources of type "resource_type" in namespace
    '''
    resources = run_kubecmd(namespace, ['get', resource_type, '-o', 'name']).splitlines()
    return [resource.split('/', 1)[1] for resource in resources]
