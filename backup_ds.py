#!/usr/bin/env python2.6
# -*- coding: utf-8

import sys
sys.path.insert(1, '/home/erkki/.local/lib/python2.6/site-packages/ecdsa-0.13-py2.6.egg/')
sys.path.insert(1, '/home/erkki/.local/lib/python2.6/site-packages/requests-2.9.1-py2.6.egg')
sys.path.insert(1, '/home/erkki/.local/lib/python2.6/site-packages/paramiko-1.16.0-py2.6.egg')

import optparse
import getopt
import paramiko
import time
import re
import getpass
import os
from socket import gethostbyname, gaierror
from scp import SCPClient

parser = optparse.OptionParser(description='Get config from DS\'s and move them to 1.140', usage="usage: %prog [file with ds list]")
#parser.add_option( help='Path to file with list of ds', required=True)

(options, args) = parser.parse_args()
if len(args) != 1:
    parser.error("incorrect number of arguments")

list_file = os.path.abspath(args[0])
if not os.path.isfile(list_file):
    print('!!! file ' + list_file + ' does not exist')
    sys.exit()

user = getpass.getuser()
secret = getpass.getpass('Pssword for DS:')

while True:
    st = raw_input("Enter a for \"After\" or b for \"Before\"\n: ")
    if st == 'a' or st == 'b':
        break

name = time.strftime("%y%m%d_") + st + '_upgrade_'
#For debug uncomment
#paramiko.common.logging.basicConfig(level=paramiko.common.DEBUG)

def get_file_name(ds, user, secret):

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=ds, username=user, password=secret, port=22, look_for_keys=False, allow_agent=False)
    print("*** SSH esteblish with " + ds)
    channel = client.invoke_shell()

    channel.send("\n")
    channel.send("show bof\n \n \n \n")
    channel.send("logout\n")
    time.sleep(2)

    printout = ''
    while channel.recv_ready():
        printout += channel.recv(1024)
        time.sleep(0.2)

    client.close()

    prim_conf = re.findall(r'primary-config.*', printout).pop()
    res = re.findall(r'cf1:.*cfg', prim_conf).pop()
    print('*** Config file name ' + res)

    return res


def get_file(ds, user, secret, file_name):
    dest = name + file_name
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(ds, 22, user, secret)
    print("*** SCP connect esteblish " + ds)
    scp = SCPClient(client.get_transport())
    print('*** Get file ' + file_name + ' from ' + ds)
    scp.get(file_name, dest)
    return dest

def mv_to_140(ds, config):
    remote_dir = '/mnt/om_kie/Backups/DS/' + ds + '/' + time.strftime("%Y") + '/'
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('10.44.4.28', username='smdmud\\stscheck_script',  key_filename='/home/butko/script/ds_bkp/.id_script_dsa')

    scp = SCPClient(ssh.get_transport())
    print('*** Move file ' + config + ' to ' + remote_dir)
    scp.put(config , remote_dir )
    os.remove(config)


with open(list_file) as f:
    dss = f.readlines()


print(dss)

for DS in dss:
    DS = DS.strip()
    try:
        file_name = get_file_name(DS, user, secret).replace('cf1:\\', '')
        conf_file = get_file(DS, user, secret, file_name)
        mv_to_140(DS, conf_file)
    except gaierror:
        print('!!! ' + DS + ' Does not exist')

