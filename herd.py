#!/usr/bin/env python
import tempfile
import sys
import os
import time
import eventlet
from eventlet.green import socket
from eventlet.green import subprocess


murder_client = eventlet.import_patched('murder_client')
bttrack = eventlet.import_patched('BitTornado.BT1.track')
makemetafile = eventlet.import_patched('BitTornado.BT1.makemetafile')

PORT = 8998
REMOTE_PATH = '/tmp/herd'
DATA_FILE = './data'

herd_root = os.path.dirname(__file__)
bittornado_tgz = os.path.join(herd_root, 'bittornado.tar.gz')
murderclient_py = os.path.join(herd_root, 'murder_client.py')

def run(local_file, remote_file, hosts):
    start = time.time()
    print "Spawning tracker..."
    eventlet.spawn(track)
    eventlet.sleep(1)
    local_host = (local_ip(), PORT)
    print "Creating torrent (host %s:%s)..." % local_host
    torrent_file = mktorrent(local_file, '%s:%s' % local_host)
    print "Seeding %s" % torrent_file
    eventlet.spawn(seed, torrent_file, local_file)
    print "Transferring"
    if not os.path.isfile(bittornado_tgz):
        cwd = os.getcwd()
        os.chdir(herd_root)
        args = ['sudo', 'tar', 'czf', 'bittornado.tar.gz', 'BitTornado']
        print "Executing", " ".join(args)
        subprocess.call(args)
        os.chdir(cwd)
    pool = eventlet.GreenPool(100)
    threads = []
    for host in hosts:
        threads.append(pool.spawn(transfer, host, torrent_file, remote_file))
    for thread in threads:
        thread.wait()
    os.unlink(torrent_file)
    try:
        os.unlink(DATA_FILE)
    except OSError:
        pass
    print "Finished, took %.2f seconds." % (time.time() - start)


def transfer(host, local_file, remote_target):
    rp = REMOTE_PATH
    file_name = os.path.basename(local_file)
    remote_file = '%s/%s' % (rp, file_name)
    print "Copying %s to %s:%s" % (local_file, host, remote_file)
    scp(host, local_file, remote_file)
    if ssh(host, 'test -d %s/BitTornado' % rp) != 0:
        ssh(host, "mkdir %s" % rp)
        scp(host, bittornado_tgz, '%s/bittornado.tar.gz' % rp)
        ssh(host, "cd %s; tar zxvf bittornado.tar.gz > /dev/null" % rp)
        scp(host, murderclient_py, '%s/murder_client.py' % rp)
    print 'python %s/murder_client.py peer %s %s' % (rp, remote_file, remote_target)
    result = ssh(host, 'python %s/murder_client.py peer %s %s' % (rp,
                    remote_file, remote_target))
    ssh(host, 'rm %s' % remote_file)
    if result == 0:
        print "%s complete" % host
    else:
        print "%s FAILED with code %s" % (host, result)


def ssh(host, command):
    return subprocess.call(['ssh', '-o UserKnownHostsFile=/dev/null',
                '-o StrictHostKeyChecking=no',
                host, command], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)


def scp(host, local_file, remote_file):
    return subprocess.call(['scp', '-o UserKnownHostsFile=/dev/null',
                '-o StrictHostKeyChecking=no',
                local_file, '%s:%s' % (host, remote_file)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def mktorrent(file_name, tracker):
    torrent_file = tempfile.mkstemp('.torrent')
    makemetafile.make_meta_file(file_name, "http://%s/announce" % tracker,
                    {'target': torrent_file[1], 'piece_size_pow2': 0})
    return torrent_file[1]


def track():
    bttrack.track(["--dfile", DATA_FILE, "--port", PORT])


def seed(torrent, local_file):
    murder_client.run(["--responsefile", torrent,
                        "--saveas", local_file])


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("10.1.0.0", 0))
    return s.getsockname()[0]


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit('ERROR: This command requires 3 command line options')

    if not os.path.exists(sys.argv[3]):
        sys.exit('ERROR: hosts file "%s" does not exist' % sys.argv[3])

    hosts = [line.strip() for line in open(sys.argv[3], 'r') if line[0] != '#']
    run(sys.argv[1], sys.argv[2], hosts)
