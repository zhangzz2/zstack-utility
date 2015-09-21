__author__ = 'frank'

import zstacklib.utils.daemon as daemon
import zstacklib.utils.http as http
import zstacklib.utils.log as log
import zstacklib.utils.shell as shell
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
        self.userKey = None

class DownloadRsp(AgentResponse):
    def __init__(self):
        super(DownloadRsp, self).__init__()
        self.size = None

class CpRsp(AgentResponse):
    def __init__(self):
        super(CpRsp, self).__init__()
        self.size = None

class CreateSnapshotRsp(AgentResponse):
    def __init__(self):
        super(CreateSnapshotRsp, self).__init__()
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

    INIT_PATH = "/ceph/primarystorage/init"
    CREATE_VOLUME_PATH = "/ceph/primarystorage/volume/createempty"
    DELETE_PATH = "/ceph/primarystorage/delete"
    CLONE_PATH = "/ceph/primarystorage/volume/clone"
    FLATTEN_PATH = "/ceph/primarystorage/volume/flatten"
    SFTP_DOWNLOAD_PATH = "/ceph/primarystorage/sftpbackupstorage/download"
    SFTP_UPLOAD_PATH = "/ceph/primarystorage/sftpbackupstorage/upload"
    ECHO_PATH = "/ceph/primarystorage/echo"
    CREATE_SNAPSHOT_PATH = "/ceph/primarystorage/snapshot/create"
    DELETE_SNAPSHOT_PATH = "/ceph/primarystorage/snapshot/delete"
    PROTECT_SNAPSHOT_PATH = "/ceph/primarystorage/snapshot/protect"
    ROLLBACK_SNAPSHOT_PATH = "/ceph/primarystorage/snapshot/rollback"
    UNPROTECT_SNAPSHOT_PATH = "/ceph/primarystorage/snapshot/unprotect"
    CP_PATH = "/ceph/primarystorage/volume/cp"
    DELETE_POOL_PATH = "/ceph/primarystorage/deletepool"

    http_server = http.HttpServer(port=7762)
    http_server.logfile_path = log.get_logfile_path()

    def __init__(self):
        self.http_server.register_async_uri(self.INIT_PATH, self.init)
        self.http_server.register_async_uri(self.DELETE_PATH, self.delete)
        self.http_server.register_async_uri(self.CREATE_VOLUME_PATH, self.create)
        self.http_server.register_async_uri(self.CLONE_PATH, self.clone)
        self.http_server.register_async_uri(self.CREATE_SNAPSHOT_PATH, self.create_snapshot)
        self.http_server.register_async_uri(self.DELETE_SNAPSHOT_PATH, self.delete_snapshot)
        self.http_server.register_async_uri(self.PROTECT_SNAPSHOT_PATH, self.protect_snapshot)
        self.http_server.register_async_uri(self.UNPROTECT_SNAPSHOT_PATH, self.unprotect_snapshot)
        self.http_server.register_async_uri(self.ROLLBACK_SNAPSHOT_PATH, self.rollback_snapshot)
        self.http_server.register_async_uri(self.FLATTEN_PATH, self.flatten)
        self.http_server.register_async_uri(self.SFTP_DOWNLOAD_PATH, self.sftp_download)
        self.http_server.register_async_uri(self.SFTP_UPLOAD_PATH, self.sftp_upload)
        self.http_server.register_async_uri(self.CP_PATH, self.cp)
        self.http_server.register_async_uri(self.DELETE_POOL_PATH, self.delete_pool)
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

        total = 1024*1024*1024*1024
        used = 1024*1024

        o = shell.call('lich.cluster --stat')
        for l in o:
            if l.startswith("used:"):
                used = long(l.strip("used:").strip())

            if l.startswith("capacity:"):
                total = long(l.strip("capacity:").strip())

        logger.debug("zz2 total: %s, used: %s" % (total, used))

        rsp.totalCapacity = total
        rsp.availableCapacity = total - used

    def _get_file_size(self, path):
        lichbd_file = os.path.join("/lichbd", path)
        size = shell.call("/opt/mds/lich/libexec/lich --stat %s|grep Size|awk '{print $2}'" % (lichbd_file))
        size = size.strip()
        return long(size)

        #o = shell.call('rbd --format json info %s' % path)
        #o = jsonobject.loads(o)
        #return long(o.size_)

    @replyerror
    def delete_pool(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        for p in cmd.poolNames:
            shell.call('ceph osd pool delete %s %s --yes-i-really-really-mean-it' % (p, p))
        return jsonobject.dumps(AgentResponse())

    @replyerror
    def rollback_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        spath = self._normalize_install_path(cmd.snapshotPath)

        shell.call('rbd snap rollback %s' % spath)
        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def cp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        src_path = self._normalize_install_path(cmd.srcPath)
        dst_path = self._normalize_install_path(cmd.dstPath)

        shell.call('rbd cp %s %s' % (src_path, dst_path))

        rsp = CpRsp()
        rsp.size = self._get_file_size(dst_path)
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    def spath2src_normal(self, spath):
        #ceph://bak-t-95036217321343c2a8d64d32e085211e/382b3757a54045e5b7dbcfcdcfb07200@382b3757a54045e5b7dbcfcdcfb07200"
        image_name, sp_name = spath.split('@')
        return os.path.join("/lichbd", image_name)

    def spath2normal(self, spath):
        image_name, sp_name = spath.split('@')
        return os.path.join("/lichbd", image_name.split("/")[0], "snap_" + sp_name)
        
    @replyerror
    def create_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        spath = self._normalize_install_path(cmd.snapshotPath)

        logger.debug("zz2, spath: %s, cmd: %s\n" % (spath, cmd))

        src_path = self.spath2src_normal(spath)
        dst_path = self.spath2normal(spath)

        shell.call('/opt/mds/lich/libexec/lich --copy %s %s' % (src_path, dst_path))

        #do_create = True
        #if cmd.skipOnExisting:
            #image_name, sp_name = spath.split('@')
            #o = shell.call('rbd --format json snap ls %s' % image_name)
            #o = jsonobject.loads(o)
            #for s in o:
                #if s.name_ == sp_name:
                    #do_create = False

        #if do_create:
            #shell.call('rbd snap create %s' % spath)

        rsp = CreateSnapshotRsp()
        rsp.size = self._get_file_size(src_path)
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def delete_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        spath = self._normalize_install_path(cmd.snapshotPath)

        shell.call('rbd snap rm %s' % spath)

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def unprotect_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        spath = self._normalize_install_path(cmd.snapshotPath)

        shell.call('rbd snap unprotect %s' % spath)

        return jsonobject.dumps(AgentResponse())

    @replyerror
    def protect_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        spath = self._normalize_install_path(cmd.snapshotPath)

        shell.call('rbd snap protect %s' % spath, exception=not cmd.ignoreError)

        rsp = AgentResponse()
        return jsonobject.dumps(rsp)

    @replyerror
    def clone(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        src_path = self._normalize_install_path(cmd.srcPath)
        dst_path = self._normalize_install_path(cmd.dstPath)

        ##rbd clone bak-t-95036217321343c2a8d64d32e085211e/382b3757a54045e5b7dbcfcdcfb07200@382b3757a54045e5b7dbcfcdcfb07200 pri-v-r-2a3fbde17e87421d81269046594c34fc/335e4182706d4883b704b45dd902a673
        #shell.call('rbd clone %s %s' % (src_path, dst_path))

        #todo set snap to null

        src_path = self.spath2normal(src_path)
        dst_path = os.path.join("/lichbd", dst_path)

        try:
            shell.call('/opt/mds/lich/libexec/lich --mkdir %s' % (os.path.dirname(dst_path)))
        except Exception, e:
            logger.debug("zz2 err: %s" % e)
            pass

        shell.call('/opt/mds/lich/libexec/lich --copy %s %s' % (src_path, dst_path))

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def flatten(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        path = self._normalize_install_path(cmd.path)

        shell.call('rbd flatten %s' % path)

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def echo(self, req):
        logger.debug('get echoed')
        return ''

    @replyerror
    def init(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        logger.debug("zz2 cmd: %s" % (cmd))

        """
        [root@node69 ~]# ceph -f json auth get-or-create client.zstack mon 'allow r' osd 'allow *' --conf /opt/ceph/ceph.conf 

        [{"entity":"client.zstack","key":"AQDVyu9VXrozIhAAuT2yMARKBndq9g3W8KUQvw==","caps":{}}]You have new mail in /var/spool/mail/root
        [root@node69 ~]# ceph mon_status --conf /opt/ceph/ceph.conf 
        {"name":"0","rank":0,"state":"leader","election_epoch":2,"quorum":[0],"outside_quorum":[],"extra_probe_peers":[],"sync_provider":[],"monmap":{"epoch":1,"fsid":"96a91e6d-892a-41f4-8fd2-4a18c9002425","modified":"0.000000","created":"0.000000","mons":[{"rank":0,"name":"0","addr":"127.0.0.1:6789\/0"}]}}
        [root@node69 ~]# 
        """

        #o = shell.call('ceph mon_status')
        #mon_status = jsonobject.loads(o)
        #fsid = mon_status.monmap.fsid_

        #existing_pools = shell.call('ceph osd lspools')
        #for pool in cmd.pools:
            #if pool.predefined and pool.name not in existing_pools:
                #raise Exception('cannot find pool[%s] in the ceph cluster, you must create it manually' % pool.name)
            #elif pool.name not in existing_pools:
                #shell.call('ceph osd pool create %s 100' % pool.name)

        #o = shell.call("ceph -f json auth get-or-create client.zstack mon 'allow r' osd 'allow *' 2>/dev/null").strip(' \n\r\t')
        #o = jsonobject.loads(o)

        rsp = InitRsp()
        rsp.fsid = "96a91e6d-892a-41f4-8fd2-4a18c9002425"
        rsp.userKey = "AQDVyu9VXrozIhAAuT2yMARKBndq9g3W8KUQvw=="
        self._set_capacity_to_response(rsp)

        return jsonobject.dumps(rsp)

    def _normalize_install_path(self, path):
        return path.lstrip('ceph:').lstrip('//')

    def _parse_install_path(self, path):
        return self._normalize_install_path(path).split('/')

    @replyerror
    def create(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        path = self._normalize_install_path(cmd.installPath)
        size_M = sizeunit.Byte.toMegaByte(cmd.size) + 1

        shell.call('qemu-img create -f raw lichbd:%s --size %s' % (path, size_M))
        #shell.call('rbd create --size %s --image-format 2 %s' % (size_M, path))

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def sftp_upload(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        src_path = self._normalize_install_path(cmd.primaryStorageInstallPath)
        prikey_file = linux.write_to_temp_file(cmd.sshKey)

        bs_folder = os.path.dirname(cmd.backupStorageInstallPath)
        shell.call('ssh -o StrictHostKeyChecking=no -i %s root@%s "mkdir -p %s"' %
                   (prikey_file, cmd.hostname, bs_folder))

        try:
            shell.call("set -o pipefail; rbd export %s - | ssh -o StrictHostKeyChecking=no -i %s root@%s 'cat > %s'" %
                        (src_path, prikey_file, cmd.hostname, cmd.backupStorageInstallPath))
        finally:
            os.remove(prikey_file)

        return jsonobject.dumps(AgentResponse())


    @replyerror
    @rollback
    def sftp_download(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        hostname = cmd.hostname
        prikey = cmd.sshKey

        pool, image_name = self._parse_install_path(cmd.primaryStorageInstallPath)
        tmp_image_name = 'tmp-%s' % image_name

        prikey_file = linux.write_to_temp_file(prikey)

        @rollbackable
        def _0():
            tpath = "%s/%s" % (pool, tmp_image_name)
            shell.call('rbd info %s > /dev/null && rbd rm %s' % (tpath, tpath))
        _0()

        try:
            shell.call('set -o pipefail; ssh -o StrictHostKeyChecking=no -i %s root@%s "cat %s" | rbd import --image-format 2 - %s/%s' %
                        (prikey_file, hostname, cmd.backupStorageInstallPath, pool, tmp_image_name))
        finally:
            os.remove(prikey_file)

        @rollbackable
        def _1():
            shell.call('rbd rm %s/%s' % (pool, tmp_image_name))
        _1()

        file_format = shell.call("set -o pipefail; qemu-img info rbd:%s/%s | grep 'file format' | cut -d ':' -f 2" % (pool, tmp_image_name))
        file_format = file_format.strip()
        if file_format not in ['qcow2', 'raw']:
            raise Exception('unknown image format: %s' % file_format)

        if file_format == 'qcow2':
            conf_path = None
            try:
                with open('/etc/ceph/ceph.conf', 'r') as fd:
                    conf = fd.read()
                    conf = '%s\n%s\n' % (conf, 'rbd default format = 2')
                    conf_path = linux.write_to_temp_file(conf)

                shell.call('qemu-img convert -f qcow2 -O rbd rbd:%s/%s rbd:%s/%s:conf=%s' % (pool, tmp_image_name, pool, image_name, conf_path))
                shell.call('rbd rm %s/%s' % (pool, tmp_image_name))
            finally:
                if conf_path:
                    os.remove(conf_path)
        else:
            shell.call('rbd mv %s/%s %s/%s' % (pool, tmp_image_name, pool, image_name))

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def ping(self, req):
        return jsonobject.dumps(AgentResponse())

    @replyerror
    def delete(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        path = self._normalize_install_path(cmd.installPath)

        path = os.path.join("/lichbd", path)
        shell.call('/opt/mds/lich/libexec/lich --unlink %s' % path)
        #o = shell.call('rbd snap ls --format json %s' % path)
        #o = jsonobject.loads(o)
        #if len(o) > 0:
            #raise Exception('unable to delete %s; the volume still has snapshots' % cmd.installPath)

        #shell.call('rbd rm %s' % path)

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)


class CephDaemon(daemon.Daemon):
    def __init__(self, pidfile):
        super(CephDaemon, self).__init__(pidfile)

    def run(self):
        logger.debug("zz2 start ceph...")
        self.agent = CephAgent()
        self.agent.http_server.start()


