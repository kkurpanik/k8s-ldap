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
Generate K8 files from Jinja templates
'''

import argparse
import base64
import glob
import hashlib
import os
import shutil
import string
import random
import yaml

# External dependencies
import jinja2


def main():
    '''
    CLI generate K8 files from Jinja templates
    '''
    parser = argparse.ArgumentParser(
        description='Generate Kubernetes files from Jinja templates')
    # Required
    parser.add_argument(
        '-n', '--namespace', required=True,
        help='Kubernetes namespace')
    parser.add_argument(
        '-s', '--storage-type', required=True,
        choices=['hostpath', 'nfs', 'bluemix', 'glusterfs-storage'],
        help='Kubernetes storage type.  Use "hostpath" for Minikube.')

    # Options
    parser.add_argument(
        '-f', '--fqdn',
        help=('Application FQDN override.'
              ' Used to compute API_GATEWAY_URL & UI_HOST'))
    parser.add_argument(
        '-i', '--input_dir', default='./k8-templates/',
        help='K8 template input directory.  Default is "./k8-templates/"')
    parser.add_argument(
        '-o', '--output_dir', default='k8-generated/',
        help=('Generated file output directory.  Default is "./k8-generated/".'
              '  Contents WILL BE WIPED.'))
    parser.add_argument(
        '-d', '--dev_settings', action='store_true',
        help='Development settings (open NodePorts, etc)')
    parser.add_argument(
        '-q', '--qa_settings', action='store_true',
        help='QA settings (open NodePorts, etc)')
    parser.add_argument(
        '-c', '--context', action='append', default=None,
        type=lambda kv: kv.split("=", 1), dest='context',
        help=('Jinja context (key/value pars): -c a=1 -c b=2...'
              ' Override with JINJA__<key> ENV variables.'))
    parser.add_argument(
        '-cf', '--context_files', default=None,
        nargs='+',  # one or more
        help='Jinja context from JSON/YML files.')
    args = parser.parse_args()
    input_dir = os.path.abspath(args.input_dir)
    output_dir = os.path.abspath(args.output_dir)

    # Assertions
    if input_dir == output_dir:
        raise AssertionError("Input / Output directories must be different: %s"
                             % (output_dir))

    for _dir in [input_dir, output_dir]:
        if not os.path.isdir(_dir):
            raise AssertionError("Directory does not exist %s" % _dir)

    if args.fqdn and len(args.fqdn.split('.')) < 2:
        raise AssertionError("FQDN: %s is not fully qualified." % args.fqdn)

    # Initialize Context & Generate K8s from Jinja
    context = init_context(args)
    gen_jinja(context, input_dir, output_dir)


def _apply_env_overrides(context):
    '''
    Apply JINJA context overrides from ENV variables
    ENV:  JINJA__<key> = value
          JINJA__<key>__<subkey> = value
    '''
    for env_key, env_value in os.environ.items():
        if not env_key.startswith('JINJA__'):
            continue
        curr_context = context
        tokens = env_key[7:].split('__')
        for counter, key in enumerate(tokens):
            if counter+1 == len(tokens):
                curr_context[key] = env_value
                break
            else:
                if key not in curr_context:
                    curr_context[key] = {}
                curr_context = curr_context[key] # move curr_context pointer


def init_context(args):
    '''
    Initialize the JINJA context from input args
    '''
    context = {}
    # apply JINJA overrides
    _apply_env_overrides(context)

    # load context from args.context_files
    if args.context_files:
        for context_filename in args.context_files:
            # treat context files as jinja templates too
            env = _get_jinja_env(os.path.dirname(os.path.abspath(context_filename)))
            tmplt = env.get_template(os.path.basename(context_filename))
            context.update(yaml.load(tmplt.render(context), Loader=yaml.SafeLoader))  # JSON/YML supported
    # now overlay context from args.context (if any)
    if args.context:
        context.update(args.context)
    # add the well-known context now
    context['K8_NAMESPACE'] = args.namespace  # set the namespace
    context['K8_STORAGE_TYPE'] = args.storage_type  # set the storage type
    context['ENABLE_DEV_SETTINGS'] = args.dev_settings  # set dev settings
    context['ENABLE_QA_SETTINGS'] = args.qa_settings  # set qa settings

    # apply JINJA overrides
    _apply_env_overrides(context)

    # Set the UI_HOST if not already in the context
    if 'UI_HOST' not in context:
        # use fqdn if specified, otherwise use namespace
        hst = args.fqdn if args.fqdn else args.namespace + ".gravitant.net"
        context['UI_HOST'] = hst
    # Set the UI_URL if not already in the context
    if 'UI_URL' not in context:
        context['UI_URL'] = "https://%s" % context['UI_HOST']
    # Set the GATEWAY_HOST if not already in the context
    if 'GATEWAY_HOST' not in context:
        # Add "-api" to the UI_HOST to set the gateway host
        ui_host_split = context['UI_HOST'].split('.', 1)
        context['GATEWAY_HOST'] = ui_host_split[0] + "-api." + ui_host_split[1]
    if 'MUTUAL_AUTH_GATEWAY_HOST' not in context:
        # Add "-auth" to the UI_HOST to set the auth gateway host
        ui_host_split = context['UI_HOST'].split('.', 1)
        context['MUTUAL_AUTH_GATEWAY_HOST'] = ui_host_split[0] + "-auth." + ui_host_split[1]
    # Set the API_GATEWAY_URL if not already in the context
    if 'API_GATEWAY_URL' not in context:
        context['API_GATEWAY_URL'] = ("https://%s:443"
                                      "" % context['GATEWAY_HOST'])
    return context


def from_file(path):
    '''
    Returns contents of path as a big string.  Newlines are converted to \\n
    '''
    with open(path, "r") as sfile:
        return sfile.read().replace('\n', '\\n').replace('"', '\\"')\
                           .replace('\t', '\\t')


def from_file_base64(path):
    '''
    Returns contents of path as a big BASE64 encoded-string.
    Good for binary files in Kubernetes Secrets
    '''
    with open(path, "rb") as sfile:
        return base64.b64encode(sfile.read()).decode('ascii')


def base64_decode(b64_encoded_str):
    '''
    Base64 decodes 'b64_encoded_str' and returns result
    '''
    return base64.b64decode(b64_encoded_str.encode('ascii')).decode('ascii')


def base64_encode(str_to_be_encoded):
    '''
    Base64 encodes 'str_to_be_encoded' and returns Base64 encoded version
    '''
    return base64.b64encode(str_to_be_encoded.encode('ascii')).decode('ascii')


def random_str(length=20):
    '''
    Generates a random string of ASCII upper/lower letters and digits,
    with the specified length
    '''
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))


def sha256(str_to_hash):
    '''
    Generate SHA256 hash of input ASCII str
    '''
    return hashlib.sha256(str_to_hash.encode('ascii')).hexdigest()


def delete_dir_contents(path):
    '''
    Delete the contents of a directory, leaving the directory itself in tact
    '''
    files = glob.glob(os.path.join(path, '*'))
    for _file in files:
        if os.path.isfile(_file):
            os.remove(_file)
        else:
            shutil.rmtree(_file)


def _get_jinja_env(input_dir):
    '''
    Sets up the Jinja environment with all the common stuff (filters, etc)
    '''
    # Jinja ENV setup
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(input_dir),
        undefined=jinja2.StrictUndefined,
        trim_blocks=True, lstrip_blocks=True)

    # register helpers as functions
    env.globals['from_file'] = from_file
    env.globals['from_file_base64'] = from_file_base64
    env.globals['base64_decode'] = base64_decode
    env.globals['base64_encode'] = base64_encode
    env.globals['random_str'] = random_str
    env.globals['sha256'] = sha256

    # ...and as filters
    env.filters['from_file'] = from_file
    env.filters['from_file_base64'] = from_file_base64
    env.filters['base64_decode'] = base64_decode
    env.filters['base64_encode'] = base64_encode
    env.filters['sha256'] = sha256

    return env


def gen_jinja(context, input_dir, output_dir):
    '''
    Given the input_dir representing a directory or jinja tempates, render
    all templates into output_dir using the supplied context.
    '''
    # clear contents of generate directory
    delete_dir_contents(output_dir)

    # Jinja2 environment
    env = _get_jinja_env(input_dir)

    # Iterate all templates in the environment
    for template in env.list_templates(extensions=['yml', 'yaml', 'json', 'start']):
        tmp_out_full = os.path.join(output_dir, template)
        tmp_out_split = os.path.split(tmp_out_full)
        # create sub-dirs as needed
        if not os.path.exists(tmp_out_split[0]):
            os.makedirs(tmp_out_split[0])  # make sub-dir
        # write the jinja rendered output
        try:
            with open(tmp_out_full, "w") as out_file:
                out_file.write(env.get_template(template).render(context))
            # verify the JINJA rendered YML/JSON is valid by parsing it
            if any(tmp_out_full.endswith(x) for x in ['.yml', '.yaml', '.json']):
                with open(tmp_out_full, 'r') as out_file:
                    for _ in yaml.load_all(out_file, Loader=yaml.SafeLoader):
                        # making it this far proves the document is parseable
                        pass
        except:
            print("** Error with template: %s" % template)
            raise


if __name__ == "__main__":
    main()
