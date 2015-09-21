__author__ = 'frank'

import zstacklib.utils.daemon as daemon
import zstacklib.utils.http as http
import zstacklib.utils.log as log
import zstacklib.utils.shell as shell
import zstacklib.utils.lichbd as lichbd
import zstacklib.utils.iptables as iptables
import zstacklib.utils.jsonobject as jsonobject
import zstacklib.utils.lock as lock
import zstacklib.utils.linux as linux
import zstacklib.utils.sizeunit as sizeunit
from zstacklib.utils import plugin
from zstacklib.utils.rollback import rollback, rollbackable
import os
import functools
import traceback
import pprint
import threading

logger = log.get_logger(__name__)

class AgentResponse(object):
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error if error else ''
        self.totalCapacity = None
        self.availableCapacity = None

class InitRsp(AgentResponse):
    def __init__(self):
        super(InitRsp, self).__init__()
        self.fsid = None

class DownloadRsp(AgentResponse):
    def __init__(self):
        super(DownloadRsp, self).__init__()
        self.size = None

def replyerror(func):
    @functools.wraps(func)
    def wrap(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            content = traceback.format_exc()
            err = '%s\n%s\nargs:%s' % (str(e), content, pprint.pformat([args, kwargs]))
            rsp = AgentResponse()
            rsp.success = False
            rsp.error = str(e)
            logger.warn(err)
            return jsonobject.dumps(rsp)
    return wrap

class CephAgent(object):
    INIT_PATH = "/ceph/backupstorage/init"
    DOWNLOAD_IMAGE_PATH = "/ceph/backupstorage/image/download"
    DELETE_IMAGE_PATH = "/ceph/backupstorage/image/delete"
    PING_PATH = "/ceph/backupstorage/ping"
    ECHO_PATH = "/ceph/backupstorage/echo"

    http_server = http.HttpServer(port=7761)
    http_server.logfile_path = log.get_logfile_path()

    def __init__(self):
        self.http_server.register_async_uri(self.INIT_PATH, self.init)
        self.http_server.register_async_uri(self.DOWNLOAD_IMAGE_PATH, self.download)
        self.http_server.register_async_uri(self.DELETE_IMAGE_PATH, self.delete)
        self.http_server.register_async_uri(self.PING_PATH, self.ping)
        self.http_server.register_sync_uri(self.ECHO_PATH, self.echo)

    def _set_capacity_to_response(self, rsp):
        #o = shell.call('ceph df -f json')
        #df = jsonobject.loads(o)

        #if df.stats.total_bytes__:
            #total = long(df.stats.total_bytes_)
        #elif df.stats.total_space__:
            #total = long(df.stats.total_space__) * 1024
        #else:
            #raise Exception('unknown ceph df output: %s' % o)

        #if df.stats.total_avail_bytes__:
            #avail = long(df.stats.total_avail_bytes_)
        #elif df.stats.total_avail__:
            #avail = long(df.stats.total_avail_) * 1024
        #else:
            #raise Exception('unknown ceph df output: %s' % o)

        total = 0
        used = 0

        o = lichbd.lichbd_cluster_stat()
        logger.debug("zz2 o: %s" % o)
        for l in o.split("\n"):
            if 'used:' in l:
                used = long(l.split("used:")[-1])
            if 'capacity:' in l:
                total = long(l.split("capacity:")[-1])

        logger.debug("zz2 total: %s, used: %s" % (total, used))

        rsp.totalCapacity = total
        rsp.availableCapacity = total - used

    @replyerror
    def echo(self, req):
        logger.debug('get echoed')
        return ''

    @replyerror
    def init(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        logger.debug("zz2 cmd: %s" % (cmd))

        lichbd.lichbd_mkdir("/lichbd")

        rsp = InitRsp()
        rsp.fsid = "96a91e6d-892a-41f4-8fd2-4a18c9002425"
        self._set_capacity_to_response(rsp)

        return jsonobject.dumps(rsp)

    def _parse_install_path(self, path):
        return path.lstrip('ceph:').lstrip('//').split('/')

    @replyerror
    @rollback
    def download(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        tmp_dir = "/opt/mds/data"

        pool, image_name = self._parse_install_path(cmd.installPath)
        tmp_image_name = 'tmp-%s' % image_name

        #shell.call('set -o pipefail; wget --no-check-certificate -q -O - %s | rbd import --image-format 2 - %s/%s' % (cmd.url, pool, tmp_image_name))

        local_tmp_file = os.path.join(tmp_dir, tmp_image_name)
        local_tmp_file_raw = os.path.join(tmp_dir, tmp_image_name + 'raw')
        lichbd_file = os.path.join("/lichbd", pool, image_name)

        shell.call('wget --no-check-certificate -q -O %s %s' % (local_tmp_file, cmd.url))

        lichbd.lichbd_mkdir("/lichbd")
        lichbd.lichbd_mkdir(os.path.dirname(lichbd_file))

        file_format = shell.call("set -o pipefail; qemu-img info %s | grep 'file format' | cut -d ':' -f 2" % (local_tmp_file))
        file_format = file_format.strip()

        if file_format not in ['qcow2', 'raw']:
            raise Exception('unknown image format: %s' % file_format)

        #need to convert2raw
        if file_format == 'qcow2':
            shell.call('qemu-img convert -f qcow2 -O raw %s %s' % (local_tmp_file, local_tmp_file_raw))

        src_path = ":%s" % (local_tmp_file_raw)
        dst_path = lichbd_file
        lichbd.lichbd_copy(src_path, dst_path)

        @rollbackable
        def _1():
            shell.call('rm -rf %s' % (local_tmp_file))
            lichbd.lichbd_unlink(lichbd_file)
            #shell.call('/opt/mds/lich/libexec/lich --unlink %s' % (lichbd_file))
        _1()


        shell.call('rm -rf %s' % (local_tmp_file))

        size = lichbd.lichbd_file_size(lichbd_file)

        rsp = DownloadRsp()
        rsp.size = size
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def ping(self, req):
        return jsonobject.dumps(AgentResponse())

    @replyerror
    def delete(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        pool, image_name = self._parse_install_path(cmd.installPath)
        lichbd_file = os.path.join("/lichbd", pool, image_name)
        lichdb.lichbd_unlink(lichbd_file)

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)


class CephDaemon(daemon.Daemon):
    def __init__(self, pidfile):
        super(CephDaemon, self).__init__(pidfile)

    def run(self):
        self.agent = CephAgent()
        self.agent.http_server.start()


