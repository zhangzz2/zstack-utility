home="/root/zstack-repos"

#cd ${home}/zstack
#mvn -DskipTests clean install

#cd ${home}
#wget -c http://archive.apache.org/dist/tomcat/tomcat-7/v7.0.35/bin/apache-tomcat-7.0.35.zip

cd ${home}/zstack-utility/zstackbuild
ant -Dzstack_build_root=/root/zstack-repos all-in-one

zstack-ctl save_config
/etc/init.d/zstack-server stop 
/etc/init.d/zstack-dashboard stop

#rm -rf /usr/local/zstack
#bash ${home}/install-zstack.sh -a -f ${home}/zstack-utility/zstackbuild/target/zstack-all-in-one-0.9.0.tgz

bash ${home}/zstack-utility/install-zstack.sh -u -f ${home}/zstack-utility/zstackbuild/target/zstack-all-in-one-0.9.0.tgz

/etc/init.d/zstack-server start
/etc/init.d/zstack-dashboard start

#rm -rf /var/lib/zstack/virtualenv/cephp/lib/python2.6/site-packages/cephprimarystorage/cephagent.py*;cp /root/zstack-repos/zstack-utility/cephprimarystorage/cephprimarystorage/cephagent.py /var/lib/zstack/virtualenv/cephp/lib/python2.6/site-packages/cephprimarystorage/;rm -rf /var/lib/zstack/virtualenv/cephb/lib/python2.6/site-packages/cephbackupstorage/cephagent.py*;cp /root/zstack-repos/zstack-utility/cephbackupstorage/cephbackupstorage/cephagent.py /var/lib/zstack/virtualenv/cephb/lib/python2.6/site-packages/cephbackupstorage/cephagent.py; /etc/init.d/zstack-ceph-primarystorage restart;/etc/init.d/zstack-ceph-backupstorage restart
#rm -rf /var/lib/zstack/virtualenv/kvm/lib/python2.6/site-packages/kvmagent/plugins/vm_plugin.py*;cp /root/zstack-repos/zstack-utility/kvmagent/kvmagent/plugins/vm_plugin.py /var/lib/zstack/virtualenv/kvm/lib/python2.6/site-packages/kvmagent/plugins/vm_plugin.py;/etc/init.d/zstack-kvmagent restart;rm -rf /var/lib/zstack/virtualenv/cephp/lib/python2.6/site-packages/cephprimarystorage/cephagent.py*;cp /root/zstack-repos/zstack-utility/cephprimarystorage/cephprimarystorage/cephagent.py /var/lib/zstack/virtualenv/cephp/lib/python2.6/site-packages/cephprimarystorage/;rm -rf /var/lib/zstack/virtualenv/cephb/lib/python2.6/site-packages/cephbackupstorage/cephagent.py*;cp /root/zstack-repos/zstack-utility/cephbackupstorage/cephbackupstorage/cephagent.py /var/lib/zstack/virtualenv/cephb/lib/python2.6/site-packages/cephbackupstorage/cephagent.py; /etc/init.d/zstack-ceph-primarystorage restart;/etc/init.d/zstack-ceph-backupstorage restart
