'''

@author: frank
'''
import errno
import subprocess
import zstacklib.utils.shell as shell
from zstacklib.utils import log

logcmd = True

logger = log.get_logger(__name__)

def lichbd_mkdir(path):
    shellcmd = shell.call_try('/opt/mds/lich/libexec/lich --mkdir %s' % (path))
    if shellcmd.return_code != 0:
        if shellcmd.return_code == errno.EEXIST:
            pass
        else:
            shell.raise_exp(shellcmd)

def lichbd_create_raw(path, size):
    shellcmd = shell.call_try('qemu-img create -f raw %s %s' % (path, size))
    if shellcmd.return_code != 0:
        if shellcmd.return_code == errno.EEXIST:
            pass
        else:
            shell.raise_exp(shellcmd)

def lichbd_copy(src_path, dst_path):
    shellcmd = None
    for i in range(5):
        shellcmd = shell.call_try('/opt/mds/lich/libexec/lich --copy %s %s' % (src_path, dst_path))
        if shellcmd.return_code == 0:
            return shellcmd
        else:
            if dst_path.startswith(":"):
                shell.call("rm -rf %s" % (dst_path.lstrip(":")))
            else:
                lichbd_unlink(dst_path)

    shell.raise_exp(shellcmd)

def lichbd_unlink(path):
    shellcmd = shell.call_try('/opt/mds/lich/libexec/lich --unlink %s' % path)
    if shellcmd.return_code != 0:
        if shellcmd.return_code == errno.ENOENT:
            pass
        else:
            shell.raise_exp(shellcmd)

def lichbd_file_size(path):
    shellcmd = shell.call_try("/opt/mds/lich/libexec/lich --stat %s|grep Size|awk '{print $2}'" % (path))
    if shellcmd.return_code != 0:
        shell.raise_exp(shellcmd)

    size = shellcmd.stdout.strip()
    return long(size)

def lichbd_cluster_stat():
    shellcmd = shell.call_try('lich.cluster --stat')
    if shellcmd.return_code != 0:
        shell.raise_exp(shellcmd)

    return shellcmd.stdout
