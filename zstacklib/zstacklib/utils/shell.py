'''

@author: frank
'''
import subprocess
import time
from zstacklib.utils import log

logcmd = True

logger = log.get_logger(__name__)

class ShellError(Exception):
    '''shell error'''
    
class ShellCmd(object):
    '''
    classdocs
    '''
    
    def __init__(self, cmd, workdir=None, pipe=True):
        '''
        Constructor
        '''
        self.cmd = cmd
        if pipe:
            self.process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, executable='/bin/sh', cwd=workdir)
        else:
            self.process = subprocess.Popen(cmd, shell=True, executable='/bin/sh', cwd=workdir)
            
        self.stdout = None
        self.stderr = None
        self.return_code = None
        
    def __call__(self, is_exception=True):
        if logcmd:
            logger.debug(self.cmd)
            
        (self.stdout, self.stderr) = self.process.communicate()
        if is_exception and self.process.returncode != 0:
            err = []
            err.append('failed to execute shell command: %s' % self.cmd)
            err.append('return code: %s' % self.process.returncode)
            err.append('stdout: %s' % self.stdout)
            err.append('stderr: %s' % self.stderr)
            raise ShellError('\n'.join(err))
            
        self.return_code = self.process.returncode
        return self.stdout

def call(cmd, exception=True, workdir=None):
    return ShellCmd(cmd, workdir)(exception)

def __call_shellcmd(cmd, exception=False, workdir=None):
    shellcmd =  ShellCmd(cmd, workdir)
    shellcmd(exception)
    return shellcmd

def call_try(cmd, exception=False, workdir=None, try_num = None):
    if try_num is None:
        try_num = 10

    shellcmd = None
    for i in range(try_num):
        shellcmd = __call_shellcmd(cmd, False, workdir)
        if shellcmd.return_code == 0:
            break

        time.sleep(1)

    return shellcmd
    #return shellcmd.stdout, shellcmd.stderr, shellcmd.return_code

def raise_exp(shellcmd):
    err = []
    err.append('failed to execute shell command: %s' % shellcmd.cmd)
    err.append('return code: %s' % shellcmd.process.returncode)
    err.append('stdout: %s' % shellcmd.stdout)
    err.append('stderr: %s' % shellcmd.stderr)
    raise ShellError('\n'.join(err))

def call_timeout():
    pass
